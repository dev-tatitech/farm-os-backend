from ninja import Router
from django.db.models import Q, Sum, Count
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from ninja.errors import HttpError
from datetime import timedelta
from django.utils import timezone

from account.auth import get_current_user
from account.models import User as users
from organization.models import Farm
from animals.models import Animal, AnimalGroup
from animals.growth import weight_gain, average_daily_gain, percentage_weight_change, cost_per_kg_gained
from finance.models import Transaction
from finance.services import compute_total_cost_to_date, compute_income_generated, get_financial_profile
from health.models import HealthAlert
from reproduction.eligibility import check_breeding_eligibility
from movement_records.sale_readiness import evaluate_sale_readiness
from movement_records.profitability import calculate_profitability
from pharmacy.models import DrugBatch
from feed.models import FeedBatch
from core.schema import ListResponseSchema, APIResponse
from common.permission_checker import user_has_permission
from common.permissions import Permissions
router = Router(tags=["Reports"])


def _auth(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
#>>>>>>>>>>>>>>>>>>
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Reports.REPORTS)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    return user, org


def _farm(request, farm_id, org):
    return get_object_or_404(Farm, id=farm_id, organization=org)


def _apply_animal_filters(qs, status=None, gender=None, livestock_species_id=None, livestock_breed_id=None, search=None):
    if status:
        qs = qs.filter(status=status)
    if gender:
        qs = qs.filter(gender=gender)
    if livestock_species_id:
        qs = qs.filter(livestock_species_id=livestock_species_id)
    if livestock_breed_id:
        qs = qs.filter(livestock_breed_id=livestock_breed_id)
    if search:
        qs = qs.filter(tag_id__icontains=search)
    return qs


# ─── Animal Cost Report / Cost per Animal ────────────────────────────────────

@router.get(
    "/animal-cost/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def animal_cost_report(
    request, page: int, page_size: int, farm_id: int,
    status: str = None, gender: str = None,
    livestock_species_id: int = None, livestock_breed_id: int = None,
    search: str = None,
):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    qs = Animal.objects.filter(farm=farm, is_active=True).select_related("financial_profile")
    qs = _apply_animal_filters(qs, status, gender, livestock_species_id, livestock_breed_id, search)
    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)
    serialized = []
    for a in page_obj.object_list:
        cost = compute_total_cost_to_date(a)
        income = compute_income_generated(a)
        profile = get_financial_profile(a)
        current_value = float(profile.current_estimated_value) if profile and profile.current_estimated_value else None
        serialized.append({
            "animal_id": a.id, "tag_id": a.tag_id,
            "acquisition_or_opening_value": float((profile.acquisition_cost or profile.opening_value or 0) if profile else 0),
            "total_cost_to_date": cost, "income_generated": income,
            "current_estimated_value": current_value,
            "estimated_profit_or_loss": (current_value or 0) + income - cost,
        })
    return 200, ListResponseSchema(
        success=True, message="animal cost report fetch successfully", data=serialized,
        num_pages=paginator.num_pages, current_page=page_obj.number,
        total_items=paginator.count, has_next=page_obj.has_next, has_previous=page_obj.has_previous,
    )


# ─── Cost by Herd or Group ────────────────────────────────────────────────────

@router.get(
    "/cost-by-group/{page}/{page_size}/{farm_id}/",
    response={200: ListResponseSchema, 403: APIResponse},
)
def cost_by_group_report(request, page: int, page_size: int, farm_id: int, search: str = None):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    groups = AnimalGroup.objects.filter(farm=farm).order_by("id")
    if search:
        groups = groups.filter(name__icontains=search)

    paginator = Paginator(groups, page_size)
    page_obj = paginator.page(page)
    data = []
    for group in page_obj.object_list:
        total = Transaction.objects.filter(farm=farm, group=group, type="expense").aggregate(t=Sum("amount"))["t"] or 0
        income = Transaction.objects.filter(farm=farm, group=group, type="income").aggregate(t=Sum("amount"))["t"] or 0
        data.append({"group_id": group.id, "group_name": group.name, "total_cost": float(total), "income_generated": float(income)})
    return 200, ListResponseSchema(
        success=True, message="Cost by group report", data=data,
        num_pages=paginator.num_pages, current_page=page_obj.number,
        total_items=paginator.count, has_next=page_obj.has_next, has_previous=page_obj.has_previous,
    )


# ─── Feed Cost Report ─────────────────────────────────────────────────────────

@router.get("/feed-cost/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def feed_cost_report(
    request, farm_id: int, start_date: str = None, end_date: str = None,
    animal_id: int = None, page: int = 1, page_size: int = 50,
):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    qs = Transaction.objects.filter(farm=farm, type="expense", category__name="Feed")
    if start_date:
        qs = qs.filter(transaction_date__gte=start_date)
    if end_date:
        qs = qs.filter(transaction_date__lte=end_date)
    if animal_id:
        qs = qs.filter(animal_id=animal_id)
    total = qs.aggregate(t=Sum("amount"))["t"] or 0
    by_animal_qs = qs.values("animal_id", "animal__tag_id").annotate(total=Sum("amount")).order_by("-total")
    paginator = Paginator(list(by_animal_qs), page_size)
    page_obj = paginator.page(page)
    return 200, APIResponse(
        success=True, message="Feed cost report",
        data={
            "total_feed_cost": float(total), "by_animal": list(page_obj.object_list),
            "num_pages": paginator.num_pages, "current_page": page_obj.number,
            "total_items": paginator.count, "has_next": page_obj.has_next(), "has_previous": page_obj.has_previous(),
        },
    )


# ─── Treatment Cost Report ────────────────────────────────────────────────────

@router.get("/treatment-cost/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def treatment_cost_report(
    request, farm_id: int, start_date: str = None, end_date: str = None,
    animal_id: int = None, page: int = 1, page_size: int = 50,
):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    qs = Transaction.objects.filter(farm=farm, type="expense", category__name="Treatment")
    if start_date:
        qs = qs.filter(transaction_date__gte=start_date)
    if end_date:
        qs = qs.filter(transaction_date__lte=end_date)
    if animal_id:
        qs = qs.filter(animal_id=animal_id)
    total = qs.aggregate(t=Sum("amount"))["t"] or 0
    by_animal_qs = qs.values("animal_id", "animal__tag_id").annotate(total=Sum("amount")).order_by("-total")
    paginator = Paginator(list(by_animal_qs), page_size)
    page_obj = paginator.page(page)
    return 200, APIResponse(
        success=True, message="Treatment cost report",
        data={
            "total_treatment_cost": float(total), "by_animal": list(page_obj.object_list),
            "num_pages": paginator.num_pages, "current_page": page_obj.number,
            "total_items": paginator.count, "has_next": page_obj.has_next(), "has_previous": page_obj.has_previous(),
        },
    )


# ─── Growth Performance ───────────────────────────────────────────────────────

@router.get(
    "/growth-performance/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def growth_performance_report(
    request, page: int, page_size: int, farm_id: int,
    status: str = None, gender: str = None,
    livestock_species_id: int = None, livestock_breed_id: int = None,
    search: str = None,
):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    qs = Animal.objects.filter(farm=farm, is_active=True)
    qs = _apply_animal_filters(qs, status, gender, livestock_species_id, livestock_breed_id, search)
    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)
    serialized = [
        {
            "animal_id": a.id, "tag_id": a.tag_id,
            "weight_gain_kg": weight_gain(a), "average_daily_gain_kg": average_daily_gain(a),
            "percentage_weight_change": percentage_weight_change(a), "cost_per_kg_gained": cost_per_kg_gained(a),
        }
        for a in page_obj.object_list
    ]
    return 200, ListResponseSchema(
        success=True, message="growth performance report fetch successfully", data=serialized,
        num_pages=paginator.num_pages, current_page=page_obj.number,
        total_items=paginator.count, has_next=page_obj.has_next, has_previous=page_obj.has_previous,
    )


# ─── Weight Exceptions ────────────────────────────────────────────────────────

@router.get(
    "/weight-exceptions/{page}/{page_size}/{farm_id}/",
    response={200: ListResponseSchema, 403: APIResponse},
)
def weight_exceptions_report(
    request, page: int, page_size: int, farm_id: int,
    severity: str = None, alert_type: str = None,
):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    alerts = HealthAlert.objects.filter(
        farm=farm, status="open",
        alert_type__in=["low_weight_for_age", "high_weight_for_age", "sudden_weight_loss", "no_weight_recorded"],
    ).select_related("animal")
    if severity:
        alerts = alerts.filter(severity=severity)
    if alert_type:
        alerts = alerts.filter(alert_type=alert_type)

    paginator = Paginator(alerts, page_size)
    page_obj = paginator.page(page)
    data = [
        {"animal_id": a.animal_id, "tag_id": a.animal.tag_id if a.animal else None,
         "alert_type": a.alert_type, "severity": a.severity, "evidence": a.evidence}
        for a in page_obj.object_list
    ]
    return 200, ListResponseSchema(
        success=True, message="Weight exceptions report", data=data,
        num_pages=paginator.num_pages, current_page=page_obj.number,
        total_items=paginator.count, has_next=page_obj.has_next, has_previous=page_obj.has_previous,
    )


# ─── Reproductive Eligibility ─────────────────────────────────────────────────

@router.get(
    "/reproductive-eligibility/{page}/{page_size}/{farm_id}/",
    response={200: ListResponseSchema, 403: APIResponse},
)
def reproductive_eligibility_report(
    request, page: int, page_size: int, farm_id: int,
    is_eligible: bool = None, livestock_species_id: int = None, search: str = None,
):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    animals = Animal.objects.filter(farm=farm, gender="female", is_active=True, status="active")
    if livestock_species_id:
        animals = animals.filter(livestock_species_id=livestock_species_id)
    if search:
        animals = animals.filter(tag_id__icontains=search)

    full_data = []
    for a in animals:
        eligible, reasons = check_breeding_eligibility(a, farm=farm)
        if is_eligible is not None and eligible != is_eligible:
            continue
        full_data.append({"animal_id": a.id, "tag_id": a.tag_id, "is_eligible": eligible, "reasons": reasons})

    paginator = Paginator(full_data, page_size)
    page_obj = paginator.page(page)
    return 200, ListResponseSchema(
        success=True, message="Reproductive eligibility report", data=list(page_obj.object_list),
        num_pages=paginator.num_pages, current_page=page_obj.number,
        total_items=paginator.count, has_next=page_obj.has_next, has_previous=page_obj.has_previous,
    )


# ─── Sale-Ready / Sale-Restricted Animals ─────────────────────────────────────

@router.get(
    "/sale-ready-animals/{page}/{page_size}/{farm_id}/",
    response={200: ListResponseSchema, 403: APIResponse},
)
def sale_ready_animals_report(
    request, page: int, page_size: int, farm_id: int,
    status: str = None, livestock_species_id: int = None, search: str = None,
):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    animals = Animal.objects.filter(farm=farm, is_active=True, status="active")
    if livestock_species_id:
        animals = animals.filter(livestock_species_id=livestock_species_id)
    if search:
        animals = animals.filter(tag_id__icontains=search)

    full_data = []
    for a in animals:
        result = evaluate_sale_readiness(a, farm=farm)
        if result["status"] not in ("ready_for_sale", "sale_recommended"):
            continue
        if status and result["status"] != status:
            continue
        full_data.append({"animal_id": a.id, "tag_id": a.tag_id, "status": result["status"], "factors": result["factors"]})

    paginator = Paginator(full_data, page_size)
    page_obj = paginator.page(page)
    return 200, ListResponseSchema(
        success=True, message="Sale-ready animals report", data=list(page_obj.object_list),
        num_pages=paginator.num_pages, current_page=page_obj.number,
        total_items=paginator.count, has_next=page_obj.has_next, has_previous=page_obj.has_previous,
    )


@router.get(
    "/sale-restricted-animals/{page}/{page_size}/{farm_id}/",
    response={200: ListResponseSchema, 403: APIResponse},
)
def sale_restricted_animals_report(
    request, page: int, page_size: int, farm_id: int,
    livestock_species_id: int = None, search: str = None,
):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    animals = Animal.objects.filter(farm=farm, is_active=True, status="active")
    if livestock_species_id:
        animals = animals.filter(livestock_species_id=livestock_species_id)
    if search:
        animals = animals.filter(tag_id__icontains=search)

    full_data = []
    for a in animals:
        result = evaluate_sale_readiness(a, farm=farm)
        if result["status"] == "sale_restricted":
            full_data.append({"animal_id": a.id, "tag_id": a.tag_id, "restrictions": result["restrictions"]})

    paginator = Paginator(full_data, page_size)
    page_obj = paginator.page(page)
    return 200, ListResponseSchema(
        success=True, message="Sale-restricted animals report", data=list(page_obj.object_list),
        num_pages=paginator.num_pages, current_page=page_obj.number,
        total_items=paginator.count, has_next=page_obj.has_next, has_previous=page_obj.has_previous,
    )


# ─── Profitability by Animal ──────────────────────────────────────────────────

@router.get(
    "/profitability/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def profitability_by_animal_report(
    request, page: int, page_size: int, farm_id: int,
    status: str = None, gender: str = None,
    livestock_species_id: int = None, livestock_breed_id: int = None,
    search: str = None,
):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    qs = Animal.objects.filter(farm=farm, is_active=True)
    qs = _apply_animal_filters(qs, status, gender, livestock_species_id, livestock_breed_id, search)
    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)
    serialized = []
    for a in page_obj.object_list:
        profit_data = calculate_profitability(a, farm=farm)
        serialized.append({"animal_id": a.id, "tag_id": a.tag_id, **profit_data})
    return 200, ListResponseSchema(
        success=True, message="profitability by animal report fetch successfully", data=serialized,
        num_pages=paginator.num_pages, current_page=page_obj.number,
        total_items=paginator.count, has_next=page_obj.has_next, has_previous=page_obj.has_previous,
    )


# ─── Low-Performance Animals ──────────────────────────────────────────────────

@router.get(
    "/low-performance-animals/{page}/{page_size}/{farm_id}/",
    response={200: ListResponseSchema, 403: APIResponse},
)
def low_performance_animals_report(
    request, page: int, page_size: int, farm_id: int,
    severity: str = None, alert_type: str = None,
):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    alerts = HealthAlert.objects.filter(
        farm=farm, status="open",
        alert_type__in=["poor_feed_conversion", "production_decline", "reproductive_concern"],
    ).select_related("animal")
    if severity:
        alerts = alerts.filter(severity=severity)
    if alert_type:
        alerts = alerts.filter(alert_type=alert_type)

    paginator = Paginator(alerts, page_size)
    page_obj = paginator.page(page)
    data = [
        {"animal_id": a.animal_id, "tag_id": a.animal.tag_id if a.animal else None,
         "alert_type": a.alert_type, "severity": a.severity, "evidence": a.evidence,
         "recommended_review": a.recommended_review}
        for a in page_obj.object_list
    ]
    return 200, ListResponseSchema(
        success=True, message="Low-performance animals report", data=data,
        num_pages=paginator.num_pages, current_page=page_obj.number,
        total_items=paginator.count, has_next=page_obj.has_next, has_previous=page_obj.has_previous,
    )


# ─── Health Alert Summary ─────────────────────────────────────────────────────

@router.get("/health-alert-summary/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def health_alert_summary_report(request, farm_id: int):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    open_alerts = HealthAlert.objects.filter(farm=farm, status="open")
    by_severity = list(open_alerts.values("severity").annotate(count=Count("id")).order_by("-count"))
    by_type = list(open_alerts.values("alert_type").annotate(count=Count("id")).order_by("-count"))
    return 200, APIResponse(
        success=True, message="Health alert summary",
        data={"total_open": open_alerts.count(), "by_severity": by_severity, "by_type": by_type},
    )


# ─── Expiring Drugs ────────────────────────────────────────────────────────────

@router.get(
    "/expiring-drugs/{page}/{page_size}/{farm_id}/",
    response={200: ListResponseSchema, 403: APIResponse},
)
def expiring_drugs_report(
    request, page: int, page_size: int, farm_id: int,
    days_ahead: int = 30, status: str = None, search: str = None,
):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    today = timezone.localdate()
    qs = DrugBatch.objects.filter(
        farm=farm, expiry_date__lte=today + timedelta(days=days_ahead)
    ).exclude(status="depleted").select_related("drug").order_by("expiry_date")
    if status:
        qs = qs.filter(status=status)
    if search:
        qs = qs.filter(drug__name__icontains=search)

    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)
    data = [
        {"batch_id": b.id, "drug": b.drug.name, "batch_number": b.batch_number,
         "quantity_available": b.quantity_available, "expiry_date": b.expiry_date, "status": b.status}
        for b in page_obj.object_list
    ]
    return 200, ListResponseSchema(
        success=True, message="Expiring drugs report", data=data,
        num_pages=paginator.num_pages, current_page=page_obj.number,
        total_items=paginator.count, has_next=page_obj.has_next, has_previous=page_obj.has_previous,
    )


# ─── Feed and Drug Stock Valuation ─────────────────────────────────────────────

@router.get("/stock-valuation/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def stock_valuation_report(
    request, farm_id: int,
    feed_page: int = 1, feed_page_size: int = 50,
    drug_page: int = 1, drug_page_size: int = 50,
):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)

    feed_value = 0.0
    feed_breakdown = []
    for b in FeedBatch.objects.filter(farm=farm).exclude(status="depleted").select_related("feed_type"):
        value = float(b.quantity_available or 0) * float(b.cost_per_base_unit or 0)
        feed_value += value
        feed_breakdown.append({"feed_type": b.feed_type.name, "batch_number": b.batch_number, "value": value})

    drug_value = 0.0
    drug_breakdown = []
    for b in DrugBatch.objects.filter(farm=farm).exclude(status="depleted").select_related("drug"):
        value = float(b.quantity_available or 0) * float(b.cost_per_base_unit or 0)
        drug_value += value
        drug_breakdown.append({"drug": b.drug.name, "batch_number": b.batch_number, "value": value})

    feed_paginator = Paginator(feed_breakdown, feed_page_size)
    feed_page_obj = feed_paginator.page(feed_page)
    drug_paginator = Paginator(drug_breakdown, drug_page_size)
    drug_page_obj = drug_paginator.page(drug_page)

    return 200, APIResponse(
        success=True, message="Stock valuation report",
        data={
            "total_feed_value": feed_value, "total_drug_value": drug_value,
            "total_stock_value": feed_value + drug_value,
            "feed_breakdown": list(feed_page_obj.object_list),
            "feed_breakdown_pagination": {
                "num_pages": feed_paginator.num_pages, "current_page": feed_page_obj.number,
                "total_items": feed_paginator.count, "has_next": feed_page_obj.has_next(), "has_previous": feed_page_obj.has_previous(),
            },
            "drug_breakdown": list(drug_page_obj.object_list),
            "drug_breakdown_pagination": {
                "num_pages": drug_paginator.num_pages, "current_page": drug_page_obj.number,
                "total_items": drug_paginator.count, "has_next": drug_page_obj.has_next(), "has_previous": drug_page_obj.has_previous(),
            },
        },
    )
