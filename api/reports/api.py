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


# ─── Animal Cost Report / Cost per Animal ────────────────────────────────────

@router.get(
    "/animal-cost/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def animal_cost_report(request, page: int, page_size: int, farm_id: int):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    qs = Animal.objects.filter(farm=farm, is_active=True).select_related("financial_profile")
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

@router.get("/cost-by-group/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def cost_by_group_report(request, farm_id: int):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    data = []
    for group in AnimalGroup.objects.filter(farm=farm):
        total = Transaction.objects.filter(farm=farm, group=group, type="expense").aggregate(t=Sum("amount"))["t"] or 0
        income = Transaction.objects.filter(farm=farm, group=group, type="income").aggregate(t=Sum("amount"))["t"] or 0
        data.append({"group_id": group.id, "group_name": group.name, "total_cost": float(total), "income_generated": float(income)})
    return 200, APIResponse(success=True, message="Cost by group report", data=data)


# ─── Feed Cost Report ─────────────────────────────────────────────────────────

@router.get("/feed-cost/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def feed_cost_report(request, farm_id: int, start_date: str = None, end_date: str = None):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    qs = Transaction.objects.filter(farm=farm, type="expense", category__name="Feed")
    if start_date:
        qs = qs.filter(transaction_date__gte=start_date)
    if end_date:
        qs = qs.filter(transaction_date__lte=end_date)
    total = qs.aggregate(t=Sum("amount"))["t"] or 0
    by_animal = list(qs.values("animal_id", "animal__tag_id").annotate(total=Sum("amount")).order_by("-total"))
    return 200, APIResponse(
        success=True, message="Feed cost report",
        data={"total_feed_cost": float(total), "by_animal": by_animal},
    )


# ─── Treatment Cost Report ────────────────────────────────────────────────────

@router.get("/treatment-cost/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def treatment_cost_report(request, farm_id: int, start_date: str = None, end_date: str = None):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    qs = Transaction.objects.filter(farm=farm, type="expense", category__name="Treatment")
    if start_date:
        qs = qs.filter(transaction_date__gte=start_date)
    if end_date:
        qs = qs.filter(transaction_date__lte=end_date)
    total = qs.aggregate(t=Sum("amount"))["t"] or 0
    by_animal = list(qs.values("animal_id", "animal__tag_id").annotate(total=Sum("amount")).order_by("-total"))
    return 200, APIResponse(
        success=True, message="Treatment cost report",
        data={"total_treatment_cost": float(total), "by_animal": by_animal},
    )


# ─── Growth Performance ───────────────────────────────────────────────────────

@router.get(
    "/growth-performance/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def growth_performance_report(request, page: int, page_size: int, farm_id: int):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    qs = Animal.objects.filter(farm=farm, is_active=True)
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

@router.get("/weight-exceptions/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def weight_exceptions_report(request, farm_id: int):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    alerts = HealthAlert.objects.filter(
        farm=farm, status="open",
        alert_type__in=["low_weight_for_age", "high_weight_for_age", "sudden_weight_loss", "no_weight_recorded"],
    ).select_related("animal")
    data = [
        {"animal_id": a.animal_id, "tag_id": a.animal.tag_id if a.animal else None,
         "alert_type": a.alert_type, "severity": a.severity, "evidence": a.evidence}
        for a in alerts
    ]
    return 200, APIResponse(success=True, message="Weight exceptions report", data=data)


# ─── Reproductive Eligibility ─────────────────────────────────────────────────

@router.get("/reproductive-eligibility/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def reproductive_eligibility_report(request, farm_id: int):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    animals = Animal.objects.filter(farm=farm, gender="female", is_active=True, status="active")
    data = []
    for a in animals:
        is_eligible, reasons = check_breeding_eligibility(a, farm=farm)
        data.append({"animal_id": a.id, "tag_id": a.tag_id, "is_eligible": is_eligible, "reasons": reasons})
    return 200, APIResponse(success=True, message="Reproductive eligibility report", data=data)


# ─── Sale-Ready / Sale-Restricted Animals ─────────────────────────────────────

@router.get("/sale-ready-animals/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def sale_ready_animals_report(request, farm_id: int):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    data = []
    for a in Animal.objects.filter(farm=farm, is_active=True, status="active"):
        result = evaluate_sale_readiness(a, farm=farm)
        if result["status"] in ("ready_for_sale", "sale_recommended"):
            data.append({"animal_id": a.id, "tag_id": a.tag_id, "status": result["status"], "factors": result["factors"]})
    return 200, APIResponse(success=True, message="Sale-ready animals report", data=data)


@router.get("/sale-restricted-animals/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def sale_restricted_animals_report(request, farm_id: int):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    data = []
    for a in Animal.objects.filter(farm=farm, is_active=True, status="active"):
        result = evaluate_sale_readiness(a, farm=farm)
        if result["status"] == "sale_restricted":
            data.append({"animal_id": a.id, "tag_id": a.tag_id, "restrictions": result["restrictions"]})
    return 200, APIResponse(success=True, message="Sale-restricted animals report", data=data)


# ─── Profitability by Animal ──────────────────────────────────────────────────

@router.get(
    "/profitability/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def profitability_by_animal_report(request, page: int, page_size: int, farm_id: int):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    qs = Animal.objects.filter(farm=farm, is_active=True)
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

@router.get("/low-performance-animals/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def low_performance_animals_report(request, farm_id: int):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    alerts = HealthAlert.objects.filter(
        farm=farm, status="open",
        alert_type__in=["poor_feed_conversion", "production_decline", "reproductive_concern"],
    ).select_related("animal")
    data = [
        {"animal_id": a.animal_id, "tag_id": a.animal.tag_id if a.animal else None,
         "alert_type": a.alert_type, "severity": a.severity, "evidence": a.evidence,
         "recommended_review": a.recommended_review}
        for a in alerts
    ]
    return 200, APIResponse(success=True, message="Low-performance animals report", data=data)


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

@router.get("/expiring-drugs/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def expiring_drugs_report(request, farm_id: int, days_ahead: int = 30):
    user, org = _auth(request)
    farm = _farm(request, farm_id, org)
    today = timezone.localdate()
    qs = DrugBatch.objects.filter(
        farm=farm, expiry_date__lte=today + timedelta(days=days_ahead)
    ).exclude(status="depleted").select_related("drug").order_by("expiry_date")
    data = [
        {"batch_id": b.id, "drug": b.drug.name, "batch_number": b.batch_number,
         "quantity_available": b.quantity_available, "expiry_date": b.expiry_date, "status": b.status}
        for b in qs
    ]
    return 200, APIResponse(success=True, message="Expiring drugs report", data=data)


# ─── Feed and Drug Stock Valuation ─────────────────────────────────────────────

@router.get("/stock-valuation/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def stock_valuation_report(request, farm_id: int):
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

    return 200, APIResponse(
        success=True, message="Stock valuation report",
        data={
            "total_feed_value": feed_value, "total_drug_value": drug_value,
            "total_stock_value": feed_value + drug_value,
            "feed_breakdown": feed_breakdown, "drug_breakdown": drug_breakdown,
        },
    )
