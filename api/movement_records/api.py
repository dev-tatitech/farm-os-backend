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
from .models import MovementRecord, SalesRecord
from .schema import MovementRecordSchema, MoveSchemaV2, SalesRecordSchema
from core.schema import APIResponse
from common.permission_checker import user_has_permission
from common.permissions import Permissions

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

    try:
        with db_transaction.atomic():
            sale.save()
    except Exception as exc:
        raise HttpError(400, str(exc))

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
