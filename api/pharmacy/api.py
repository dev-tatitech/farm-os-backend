from ninja import Router
from django.db.models import Q
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from ninja.errors import HttpError

from account.auth import get_current_user
from account.models import User as users
from organization.models import Farm
from common.permission_checker import user_has_permission
from common.permissions import Permissions

from .models import DrugCategory, Drug, DrugBatch
from .seed import seed_drug_master
from .alerts import run_pharmacy_alert_scan, get_animals_in_withdrawal
from .schema import ListResponseSchema, APIResponse, DrugSchemaIn, DrugBatchSchemaIn

router = Router(tags=["Pharmacy"])


@router.post("/drug-master/seed/", response={200: APIResponse, 403: APIResponse})
def seed_pharmacy_master(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    if not user.is_superuser:
        raise HttpError(403, "Permission Denied")

    stats = seed_drug_master()
    return 200, APIResponse(success=True, message="Drug master data seeded successfully", data=stats)


@router.get("/drug-category/", response={200: APIResponse, 403: APIResponse})
def get_drug_categories(request):
    user_id = get_current_user(request)
    try:
        users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    data = list(DrugCategory.objects.filter(is_active=True).values("id", "name", "is_system"))
    return 200, APIResponse(success=True, message="Drug categories", data=data)


@router.get(
    "/drug/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_drugs(request, page: int, page_size: int, farm_id: int, category_id: int = None):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    qs = Drug.objects.filter(Q(farm=None) | Q(farm=farm), is_active=True).select_related("category")
    if category_id:
        qs = qs.filter(category_id=category_id)

    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)
    serialized = [
        {
            "id": d.id, "name": d.name, "category": d.category.name, "category_id": d.category_id,
            "active_ingredient": d.active_ingredient, "brand_name": d.brand_name, "manufacturer": d.manufacturer,
            "dosage_form": d.dosage_form, "strength_concentration": d.strength_concentration,
            "unit_of_measurement": d.unit_of_measurement, "withdrawal_period_days": d.withdrawal_period_days,
            "is_system": d.is_system, "farm_id": d.farm_id,
        }
        for d in page_obj.object_list
    ]
    return 200, ListResponseSchema(
        success=True, message="drugs fetch successfully", data=serialized,
        num_pages=paginator.num_pages, current_page=page_obj.number,
        total_items=paginator.count, has_next=page_obj.has_next, has_previous=page_obj.has_previous,
    )


@router.post("/drug/", response={200: APIResponse, 403: APIResponse})
def create_farm_drug(request, farm_id: int, payload: DrugSchemaIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(403, "Permission denied")
    perm = user_has_permission(user, Permissions.Pharmacy.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    category = get_object_or_404(DrugCategory, id=payload.category_id, is_active=True)

    if Drug.objects.filter(name__iexact=payload.name).filter(Q(farm=None) | Q(farm=farm)).exists():
        raise HttpError(409, "Drug already exists")

    drug = Drug.objects.create(
        farm=farm, name=payload.name, category=category, active_ingredient=payload.active_ingredient,
        brand_name=payload.brand_name, manufacturer=payload.manufacturer, dosage_form=payload.dosage_form,
        strength_concentration=payload.strength_concentration, unit_of_measurement=payload.unit_of_measurement,
        withdrawal_period_days=payload.withdrawal_period_days, is_system=False, created_by=user,
    )
    return 200, APIResponse(
        success=True, message="Custom drug created",
        data={"id": drug.id, "name": drug.name, "category": category.name},
    )


@router.post("/drug-batch/", response={200: APIResponse, 403: APIResponse})
def create_drug_batch(request, payload: DrugBatchSchemaIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Pharmacy.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, "Permission denied")

    farm = get_object_or_404(Farm, id=payload.farm_id, organization=org)
    drug = get_object_or_404(Drug.objects.filter(Q(farm=None) | Q(farm=farm)), id=payload.drug_id, is_active=True)

    if DrugBatch.objects.filter(drug=drug, farm=farm, batch_number=payload.batch_number).exists():
        raise HttpError(409, "This batch number already exists for this drug")

    batch = DrugBatch(
        drug=drug, farm=farm, batch_number=payload.batch_number,
        quantity_received=payload.quantity_received, quantity_available=payload.quantity_received,
        purchase_unit=payload.purchase_unit, purchase_price=payload.purchase_price, supplier=payload.supplier,
        purchase_date=payload.purchase_date, manufacturing_date=payload.manufacturing_date,
        expiry_date=payload.expiry_date, storage_location=payload.storage_location,
        minimum_stock_level=payload.minimum_stock_level, created_by=user,
    )
    try:
        batch.full_clean(exclude=["cost_per_base_unit"])
        batch.save()
    except ValidationError as e:
        return JsonResponse({"errors": e.message_dict}, status=400)

    return 200, APIResponse(
        success=True, message="Drug batch created successfully",
        data={
            "id": batch.id, "drug": drug.name, "batch_number": batch.batch_number,
            "quantity_available": batch.quantity_available, "cost_per_base_unit": batch.cost_per_base_unit,
        },
    )


@router.get(
    "/drug-batch/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_drug_batches(request, page: int, page_size: int, farm_id: int, drug_id: int = None, status: str = None):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    qs = DrugBatch.objects.select_related("drug", "drug__category").filter(farm=farm)
    if drug_id:
        qs = qs.filter(drug_id=drug_id)
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)
    serialized = [
        {
            "id": b.id, "drug": b.drug.name, "drug_id": b.drug_id, "batch_number": b.batch_number,
            "quantity_received": b.quantity_received, "quantity_available": b.quantity_available,
            "cost_per_base_unit": b.cost_per_base_unit, "supplier": b.supplier,
            "expiry_date": b.expiry_date, "storage_location": b.storage_location,
            "minimum_stock_level": b.minimum_stock_level, "status": b.status,
        }
        for b in page_obj.object_list
    ]
    return 200, ListResponseSchema(
        success=True, message="drug batches fetch successfully", data=serialized,
        num_pages=paginator.num_pages, current_page=page_obj.number,
        total_items=paginator.count, has_next=page_obj.has_next, has_previous=page_obj.has_previous,
    )


# ─── Pharmacy Alerts (spec 3.5) ───────────────────────────────────────────────

@router.post("/pharmacy-alert/scan/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def scan_pharmacy_alerts(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    triggered = run_pharmacy_alert_scan(farm)
    data = [
        {
            "id": a.id, "alert_type": a.alert_type, "severity": a.severity,
            "evidence": a.evidence, "recommended_review": a.recommended_review,
        }
        for a in triggered
    ]
    return 200, APIResponse(success=True, message="Pharmacy alert scan complete", data=data)


@router.get(
    "/pharmacy-alert/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_pharmacy_alerts(request, page: int, page_size: int, farm_id: int, status: str = None):
    from health.models import HealthAlert

    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    qs = HealthAlert.objects.select_related("drug_batch", "drug_batch__drug").filter(
        farm=farm, drug_batch__isnull=False
    )
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)
    serialized = [
        {
            "id": a.id,
            "drug_batch_id": a.drug_batch_id,
            "drug": a.drug_batch.drug.name if a.drug_batch else None,
            "batch_number": a.drug_batch.batch_number if a.drug_batch else None,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "detected_date": a.detected_date,
            "evidence": a.evidence,
            "recommended_review": a.recommended_review,
            "status": a.status,
            "created_at": a.created_at,
        }
        for a in page_obj.object_list
    ]
    return 200, ListResponseSchema(
        success=True, message="pharmacy alerts fetch successfully", data=serialized,
        num_pages=paginator.num_pages, current_page=page_obj.number,
        total_items=paginator.count, has_next=page_obj.has_next, has_previous=page_obj.has_previous,
    )


@router.get("/animal-withdrawal/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def get_animals_under_withdrawal(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    records = get_animals_in_withdrawal(farm)
    data = [
        {
            "animal_id": r.animal_id, "animal_tag": r.animal.tag_id, "drug": r.drug.name if r.drug else None,
            "treatment_date": r.treatment_date, "withdrawal_end_date": r.withdrawal_end_date,
        }
        for r in records
    ]
    return 200, APIResponse(success=True, message="Animals under withdrawal restriction", data=data)
