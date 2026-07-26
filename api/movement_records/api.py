from django.shortcuts import get_object_or_404
from django.db import transaction as db_transaction
from django.core.paginator import Paginator
from django.db.models import Q
from ninja import Router, Query
from ninja.errors import HttpError
from account.auth import get_current_user
from account.models import User as users
from organization.models import Farm
from animals.models import Animal, AnimalGroup
from farms.models import FarmUnit
from admin_panel.models import FarmHousingUnit
from .models import MovementRecord, SalesRecord, SalePolicy
from .schema import MovementRecordSchema, MoveSchemaV2, SalesRecordSchema
from .sale_readiness import evaluate_sale_readiness
from .profitability import calculate_profitability
from .seed import seed_sale_policies
from admin_panel.models import LivestockSpecies, LivestockBreed
from core.schema import APIResponse
from common.permission_checker import user_has_permission
from common.permissions import Permissions
from django.utils import timezone

router = Router(tags=["MovementRecords"])


@router.post("/move/", response={200: APIResponse, 400: APIResponse, 403: APIResponse})
def create_movement(request, payload: MovementRecordSchema):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(id=user_id)
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.MovementRecord.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
        
    farm = get_object_or_404(Farm, id=payload.farm_id, organization=org)
    animal = None
    group = None
    from_unit = None
    to_unit = None

    if payload.animal_id:
        animal = get_object_or_404(Animal, id=payload.animal_id, farm=farm)
        if animal.status in ["sold", "dead"]:
            raise HttpError(400, "Sold or dead animals cannot be moved")

    if payload.group_id:
        group = get_object_or_404(AnimalGroup, id=payload.group_id, farm=farm)

    if payload.from_unit_id:
        from_unit = get_object_or_404(FarmUnit, id=payload.from_unit_id, farm=farm)

    if payload.to_unit_id:
        to_unit = get_object_or_404(FarmUnit, id=payload.to_unit_id, farm=farm)

    if animal and from_unit and animal.unit_id != from_unit.id:
        raise HttpError(400, "Animal is not assigned to the declared from_unit")

    movement = MovementRecord(
        farm=farm,
        animal=animal,
        group=group,
        from_unit=from_unit,
        to_unit=to_unit,
        move_date=payload.move_date,
        reason=payload.reason,
        created_by=user,
    )

    try:
        with db_transaction.atomic():
            movement.full_clean()
            movement.save()
            if animal and to_unit:
                animal.unit = to_unit
                animal.save(update_fields=["unit"])
    except Exception as exc:
        raise HttpError(400, str(exc))

    return 200, APIResponse(
        success=True,
        message="Movement record created successfully",
        data={"movement_id": movement.id},
    )


@router.get("/moves/{page}/{page_size}/{farm_id}", response={200: APIResponse, 400: APIResponse, 403: APIResponse})
def list_movements(request, page: int, page_size: int, farm_id: int, q: str = Query(None)):
    # permission check
    user_id = get_current_user(request)
    try:
        user = users.objects.get(id=user_id)
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.MovementRecord.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
        
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    qs = MovementRecord.objects.filter(farm=farm)
    if q:
        qs = qs.filter(
            Q(reason__icontains=q)
            | Q(animal__tag_id__icontains=q)
            | Q(from_unit__name__icontains=q)
            | Q(to_unit__name__icontains=q)
        )

    paginator = Paginator(qs.order_by("-created_at"), page_size)
    page_obj = paginator.get_page(page)
    items = []
    for m in page_obj.object_list:
        items.append(
            {
                "id": m.id,
                "farm_id": m.farm_id,
                "animal": {"id": m.animal_id, "tag_id": getattr(m.animal, "tag_id", None)} if m.animal_id else None,
                "group_id": m.group_id,
                "from_unit_id": m.from_unit_id,
                "to_unit_id": m.to_unit_id,
                "move_date": m.move_date,
                "reason": m.reason,
                "created_by": m.created_by_id,
                "created_at": m.created_at,
            }
        )

    return 200, APIResponse(
        success=True,
        message="Movement records",
        data={
            "items": items,
            "num_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "total_items": paginator.count,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        },
    )


@router.get("/move/{movement_id}", response={200: APIResponse, 404: APIResponse, 403: APIResponse})
def get_movement(request, movement_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(id=user_id)
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.MovementRecord.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied") 
    m = get_object_or_404(MovementRecord, id=movement_id)
    data = {
        "id": m.id,
        "farm_id": m.farm_id,
        "animal": {"id": m.animal_id, "tag_id": getattr(m.animal, "tag_id", None)} if m.animal_id else None,
        "group_id": m.group_id,
        "from_unit_id": m.from_unit_id,
        "to_unit_id": m.to_unit_id,
        "move_date": m.move_date,
        "reason": m.reason,
        "created_by": m.created_by_id,
        "created_at": m.created_at,
    }

    return 200, APIResponse(success=True, message="Movement record", data=data)


@router.post("/sale/", response={200: APIResponse, 400: APIResponse, 403: APIResponse})
def create_sale(request, payload: SalesRecordSchema):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(id=user_id)
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.SalesRecord.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")

    farm = get_object_or_404(Farm, id=payload.farm_id, organization=org)
    animal = get_object_or_404(Animal, id=payload.animal_id, farm=farm)
    if animal.status in ["sold", "dead"]:
        raise HttpError(400, "Only active animals can be sold")

    is_override = bool(payload.override_reason)
    if is_override:
        override_perm = user_has_permission(user, Permissions.SalesRecord.RESTRICTION_OVERRIDE)
        if not user.organizations.first():
            if not override_perm:
                raise HttpError(403, "Permission denied: overriding sale restrictions requires explicit authorization")

    sale = SalesRecord(
        farm=farm,
        animal=animal,
        buyer_name=payload.buyer_name,
        price=payload.price,
        sale_date=payload.sale_date,
        reason=payload.reason,
        notes=payload.notes,
        created_by=user,
    )
    if is_override:
        sale._override_restriction = True

    try:
        with db_transaction.atomic():
            sale.save()
    except Exception as exc:
        raise HttpError(400, str(exc))

    if is_override:
        from common.audit import log_audit
        log_audit(
            user=user, action="override_sale_restriction", source_module="movement_records",
            object_type="SalesRecord", object_id=sale.id,
            previous_value="blocked by sale restriction check", new_value="created via authorized override",
            reason=payload.override_reason,
        )

    return 200, APIResponse(
        success=True,
        message="Sales record created successfully",
        data={"sale_id": sale.id},
    )


@router.get("/sales/{page}/{page_size}/{farm_id}", response={200: APIResponse, 400: APIResponse, 403: APIResponse})
def list_sales(request, page: int, page_size: int, farm_id: int, q: str = Query(None)):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(id=user_id)
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.SalesRecord.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    qs = SalesRecord.objects.filter(farm=farm)
    if q:
        qs = qs.filter(
            Q(buyer_name__icontains=q)
            | Q(notes__icontains=q)
            | Q(reason__icontains=q)
            | Q(animal__tag_id__icontains=q)
        )

    paginator = Paginator(qs.order_by("-created_at"), page_size)
    page_obj = paginator.get_page(page)
    items = []
    for s in page_obj.object_list:
        items.append(
            {
                "id": s.id,
                "farm_id": s.farm_id,
                "animal": {"id": s.animal_id, "tag_id": getattr(s.animal, "tag_id", None)},
                "buyer_name": s.buyer_name,
                "price": s.price,
                "sale_date": s.sale_date,
                "reason": s.reason,
                "notes": s.notes,
                "created_by": s.created_by_id,
                "created_at": s.created_at,
            }
        )

    return 200, APIResponse(
        success=True,
        message="Sales records",
        data={
            "items": items,
            "num_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "total_items": paginator.count,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        },
    )


@router.get("/sale/{sale_id}", response={200: APIResponse, 404: APIResponse, 403: APIResponse})
def get_sale(request, sale_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(id=user_id)
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.SalesRecord.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")

    s = get_object_or_404(SalesRecord, id=sale_id, farm__organization=org)
    data = {
        "id": s.id,
        "farm_id": s.farm_id,
        "animal": {"id": s.animal_id, "tag_id": getattr(s.animal, "tag_id", None)},
        "buyer_name": s.buyer_name,
        "price": s.price,
        "sale_date": s.sale_date,
        "reason": s.reason,
        "notes": s.notes,
        "created_by": s.created_by_id,
        "created_at": s.created_at,
    }

    return 200, APIResponse(success=True, message="Sales record", data=data)


# ---------------------------------------------------------------------------
# v2 endpoints
# ---------------------------------------------------------------------------

@router.post("/move/v2/", response={200: APIResponse, 400: APIResponse, 403: APIResponse})
def create_movement_v2(request, payload: MoveSchemaV2):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(id=user_id)
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.MovementRecord.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, "Permission denied")

    farm = get_object_or_404(Farm, id=payload.farm_id, organization=org)
    animal = None
    group = None

    if payload.animal_id:
        animal = get_object_or_404(Animal, id=payload.animal_id, farm=farm)
        if animal.status in ["sold", "dead"]:
            raise HttpError(400, "Sold or dead animals cannot be moved")

    if payload.group_id:
        group = get_object_or_404(AnimalGroup, id=payload.group_id, farm=farm)

    from_housing_unit = get_object_or_404(FarmHousingUnit, id=payload.from_housing_unit_id, farm=farm)
    to_housing_unit = get_object_or_404(FarmHousingUnit, id=payload.to_housing_unit_id, farm=farm)

    movement = MovementRecord(
        farm=farm,
        animal=animal,
        group=group,
        from_housing_unit=from_housing_unit,
        to_housing_unit=to_housing_unit,
        move_date=payload.move_date,
        reason=payload.reason,
        created_by=user,
    )

    try:
        with db_transaction.atomic():
            movement.full_clean()
            movement.save()
            if animal:
                animal.housing_unit = to_housing_unit
                animal.save(update_fields=["housing_unit"])
    except Exception as exc:
        raise HttpError(400, str(exc))

    return 200, APIResponse(
        success=True,
        message="Movement record created successfully",
        data={"movement_id": movement.id},
    )


@router.get("/moves/v2/{page}/{page_size}/{farm_id}", response={200: APIResponse, 400: APIResponse, 403: APIResponse})
def list_movements_v2(request, page: int, page_size: int, farm_id: int, q: str = Query(None)):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(id=user_id)
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.MovementRecord.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, "Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    qs = MovementRecord.objects.select_related(
        "from_housing_unit__unit_type",
        "to_housing_unit__unit_type",
        "from_unit",
        "to_unit",
        "animal",
    ).filter(farm=farm)

    if q:
        qs = qs.filter(
            Q(reason__icontains=q)
            | Q(animal__tag_id__icontains=q)
            | Q(from_housing_unit__name__icontains=q)
            | Q(to_housing_unit__name__icontains=q)
            | Q(from_unit__name__icontains=q)
            | Q(to_unit__name__icontains=q)
        )

    paginator = Paginator(qs.order_by("-created_at"), page_size)
    page_obj = paginator.get_page(page)
    items = []
    for m in page_obj.object_list:
        fhu = m.from_housing_unit
        thu = m.to_housing_unit
        items.append(
            {
                "id": m.id,
                "farm_id": m.farm_id,
                "animal": {"id": m.animal_id, "tag_id": getattr(m.animal, "tag_id", None)} if m.animal_id else None,
                "group_id": m.group_id,
                "from_unit": fhu.name if fhu else (m.from_unit.name if m.from_unit else None),
                "to_unit": thu.name if thu else (m.to_unit.name if m.to_unit else None),
                "from_unit_id": m.from_housing_unit_id or m.from_unit_id,
                "to_unit_id": m.to_housing_unit_id or m.to_unit_id,
                "unit_type": fhu.unit_type.name if fhu and fhu.unit_type else None,
                "move_date": m.move_date,
                "reason": m.reason,
                "created_by": m.created_by_id,
                "created_at": m.created_at,
            }
        )

    return 200, APIResponse(
        success=True,
        message="Movement records",
        data={
            "items": items,
            "num_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "total_items": paginator.count,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        },
    )


@router.get("/move/v2/{movement_id}", response={200: APIResponse, 404: APIResponse, 403: APIResponse})
def get_movement_v2(request, movement_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(id=user_id)
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.MovementRecord.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, "Permission denied")

    m = get_object_or_404(
        MovementRecord.objects.select_related(
            "from_housing_unit__unit_type",
            "to_housing_unit__unit_type",
            "from_unit",
            "to_unit",
            "animal",
        ),
        id=movement_id,
    )
    fhu = m.from_housing_unit
    thu = m.to_housing_unit
    data = {
        "id": m.id,
        "farm_id": m.farm_id,
        "animal": {"id": m.animal_id, "tag_id": getattr(m.animal, "tag_id", None)} if m.animal_id else None,
        "group_id": m.group_id,
        "from_unit": fhu.name if fhu else (m.from_unit.name if m.from_unit else None),
        "to_unit": thu.name if thu else (m.to_unit.name if m.to_unit else None),
        "from_unit_id": m.from_housing_unit_id or m.from_unit_id,
        "to_unit_id": m.to_housing_unit_id or m.to_unit_id,
        "unit_type": fhu.unit_type.name if fhu and fhu.unit_type else None,
        "move_date": m.move_date,
        "reason": m.reason,
        "created_by": m.created_by_id,
        "created_at": m.created_at,
    }

    return 200, APIResponse(success=True, message="Movement record", data=data)


# ─── Sale Readiness & Profitability (Phase 4) ─────────────────────────────────

@router.post("/sale-policy/seed/", response={200: APIResponse, 403: APIResponse})
def seed_sale_policy(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    if not user.is_superuser:
        raise HttpError(403, "Permission Denied")

    created = seed_sale_policies()
    return 200, APIResponse(success=True, message="Sale policies seeded successfully", data={"created": created})


@router.get("/sale-policy/{species_id}/", response={200: APIResponse, 403: APIResponse})
def get_sale_policy(request, species_id: int, farm_id: int = None):
    user_id = get_current_user(request)
    try:
        users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    species = get_object_or_404(LivestockSpecies, id=species_id, is_active=True)
    qs = SalePolicy.objects.filter(species=species, is_active=True)
    qs = qs.filter(Q(farm_id=farm_id) | Q(farm=None)) if farm_id else qs.filter(farm=None)
    data = list(qs.values(
        "id", "breed_id", "farm_id", "target_sale_weight_kg", "min_sale_age_months",
        "allow_pregnant_sale", "require_sale_approval", "expected_sale_expenses_pct",
        "approaching_ready_threshold_pct", "sale_recommended_margin_pct", "is_system",
    ))
    return 200, APIResponse(success=True, message="Sale policies", data=data)


@router.post("/sale-policy/", response={200: APIResponse, 403: APIResponse})
def create_farm_sale_policy(
    request, farm_id: int, species_id: int, breed_id: int = None,
    target_sale_weight_kg: float = None, min_sale_age_months: float = None,
    allow_pregnant_sale: bool = False, require_sale_approval: bool = False,
    expected_sale_expenses_pct: float = 0, approaching_ready_threshold_pct: float = 85,
    sale_recommended_margin_pct: float = 15,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(403, "Permission denied")
    perm = user_has_permission(user, Permissions.SalesRecord.UPDATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied: configuring species sale policy requires explicit authorization")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    species = get_object_or_404(LivestockSpecies, id=species_id, is_active=True)
    breed = get_object_or_404(LivestockBreed, id=breed_id) if breed_id else None

    previous_policy = SalePolicy.objects.filter(species=species, breed=breed, farm=farm).first()
    previous_value = (
        f"target_weight={previous_policy.target_sale_weight_kg}, allow_pregnant_sale={previous_policy.allow_pregnant_sale}"
        if previous_policy else None
    )

    policy, created = SalePolicy.objects.update_or_create(
        species=species, breed=breed, farm=farm,
        defaults=dict(
            target_sale_weight_kg=target_sale_weight_kg,
            min_sale_age_months=min_sale_age_months,
            allow_pregnant_sale=allow_pregnant_sale,
            require_sale_approval=require_sale_approval,
            expected_sale_expenses_pct=expected_sale_expenses_pct,
            approaching_ready_threshold_pct=approaching_ready_threshold_pct,
            sale_recommended_margin_pct=sale_recommended_margin_pct,
            is_system=False,
        ),
    )

    from common.audit import log_audit
    log_audit(
        user=user, action="configure_species_rule", source_module="movement_records",
        object_type="SalePolicy", object_id=policy.id,
        previous_value=previous_value,
        new_value=f"target_weight={target_sale_weight_kg}, allow_pregnant_sale={allow_pregnant_sale}",
    )

    return 200, APIResponse(
        success=True,
        message="Farm sale policy saved" if created else "Farm sale policy updated",
        data={"id": policy.id},
    )


@router.get("/sale-readiness/{animal_id}/", response={200: APIResponse, 403: APIResponse})
def get_sale_readiness(request, animal_id: int, expected_sale_price: float = None):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    animal = get_object_or_404(Animal, id=animal_id, farm__organization=org)
    result = evaluate_sale_readiness(animal, farm=animal.farm, expected_sale_price=expected_sale_price)
    return 200, APIResponse(success=True, message="Sale readiness", data=result)


@router.get("/animal-profitability/{animal_id}/", response={200: APIResponse, 403: APIResponse})
def get_animal_profitability(request, animal_id: int, expected_sale_price: float = None, price_per_kg: float = None):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    animal = get_object_or_404(Animal, id=animal_id, farm__organization=org)
    result = calculate_profitability(
        animal, expected_sale_price=expected_sale_price, price_per_kg=price_per_kg, farm=animal.farm
    )
    return 200, APIResponse(success=True, message="Animal profitability", data=result)


@router.post("/sale-approval/{animal_id}/", response={200: APIResponse, 403: APIResponse})
def approve_animal_sale(request, animal_id: int, reason: str = ""):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(403, "Permission denied")
    perm = user_has_permission(user, Permissions.SalesRecord.UPDATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")

    animal = get_object_or_404(Animal, id=animal_id, farm__organization=org)
    previous = animal.sale_approved
    animal.sale_approved = True
    animal.sale_approved_by = user
    animal.sale_approved_at = timezone.now()
    animal.save(update_fields=["sale_approved", "sale_approved_by", "sale_approved_at"])

    from common.audit import log_audit
    log_audit(
        user=user, action="approve_animal_sale", source_module="movement_records",
        object_type="Animal", object_id=animal.id,
        previous_value=f"sale_approved={previous}", new_value="sale_approved=True", reason=reason,
    )

    return 200, APIResponse(
        success=True, message="Sale approved",
        data={"animal_id": animal.id, "sale_approved": True, "sale_approved_by": user.email},
    )
