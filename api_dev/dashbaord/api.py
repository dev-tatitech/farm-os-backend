from ninja import Router, Query
from django.conf import settings
from ninja import File
from account.auth import get_current_user, validate_crftoken
from account.models import User as users
from django.db.models import Q
from ninja.files import UploadedFile
from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from uuid import UUID
from django.forms.models import model_to_dict
from datetime import date, time
import calendar
from django.db.models import Sum
from common.permission_checker import user_has_permission
from common.permissions import Permissions
from dateutil.relativedelta import relativedelta
from decimal import Decimal,ROUND_HALF_UP, ROUND_DOWN
from dateutil.parser import parse as parse_datetime
from django.core.mail import send_mail
from ninja import Router, Query
from ninja.errors import HttpError
from pydantic import EmailStr
from django.utils.timezone import now
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
import random
from datetime import datetime
from dateutil.relativedelta import relativedelta
from organization.models import Farm
from farms.models import FarmUnit
import hmac
import hashlib
import json
import os
from django.db.models.functions import Round
from django.db.models import Value
from django.http import HttpResponse
from account.models import (
    Country,
    AdminLevel1
)
from django.db import IntegrityError
import uuid
from admin_panel.models import UnitType, Species, Breed
from admin_panel.models import LivestockSpecies, LivestockBreed, FarmHousingUnit, AnimalClassification
from subcriptions.models import SubscriptionPlan, Subscription
from common.utils import generate_ref, resolve_trend_start, daily_trend_range, monthly_trend_range
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.http import JsonResponse
from animals.models import (
    Animal, 
    )
from core.models import GroupType
from django.core.exceptions import ValidationError
from .schema import (
    APIResponse,
)
from .schema import (
    APIResponse,
)
router = Router(tags=["Dashboard"])
@router.get("/main-dashboard/{farm_id}", response={200: APIResponse, 403: APIResponse})
def main_dashboard(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Reports.LIVESTOCK_DASHBOARD)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    # lazy import to avoid cycles
    from animals.models import AnimalDashboard, DailyMilkSummary, AnimalWeight
    from animals.signals import recalc_dashboard_for_farm
    from health.models import VaccinationRecord, TreatmentRecord

    dashboard = AnimalDashboard.objects.filter(farm_id=farm_id).first()
    if not dashboard:
        # create and calculate on demand
        recalc_dashboard_for_farm(farm_id)
        dashboard = AnimalDashboard.objects.get(farm_id=farm_id)

    upcoming_records = VaccinationRecord.objects.select_related("animal", "group").filter(
        farm_id=farm_id,
        next_due_date__isnull=False,
        next_due_date__gte=timezone.localdate(),
    ).order_by("next_due_date")[:5]

    vaccination_upcoming_records = [
        {
            "id": record.id,
            "animal_id": record.animal.id if record.animal else None,
            "animal_tag": record.animal.tag_id if record.animal else None,
            "group_id": record.group.id if record.group else None,
            "group_name": record.group.name if record.group else None,
            "vaccine_name": record.vaccine_name,
            "date_given": record.date_given,
            "next_due_date": record.next_due_date,
            "notes": record.notes,
        }
        for record in upcoming_records
    ]

    # Treatment follow-ups
    treatment_followups_qs = TreatmentRecord.objects.select_related("animal", "group").filter(
        farm_id=farm_id,
        next_follow_up_date__isnull=False,
    ).order_by("-next_follow_up_date")[:3]

    treatment_followups = [
        {
            "id": record.id,
            "animal_id": record.animal.id if record.animal else None,
            "animal_tag": record.animal.tag_id if record.animal else None,
            "group_id": record.group.id if record.group else None,
            "group_name": record.group.name if record.group else None,
            "diagnosis": record.diagnosis,
            "treatment": record.treatment,
            "severity": record.severity,
            "treatment_date": record.treatment_date,
            "next_follow_up_date": record.next_follow_up_date,
            "notes": record.notes,
        }
        for record in treatment_followups_qs
    ]

    # Species distribution
    from django.db.models import Count
    species_dist = Animal.objects.filter(
        farm_id=farm_id
    ).values('species__id', 'species__name').annotate(count=Count('id')).order_by('-count')

    species_distribution = [
        {
            "species_id": item['species__id'],
            "species_name": item['species__name'],
            "count": item['count'],
        }
        for item in species_dist
    ]

    today = timezone.localdate()
    milk_summary = DailyMilkSummary.objects.filter(farm_id=farm_id, date=today).first()
    milk_today = milk_summary.total_litres if milk_summary else 0

    nominal_seven_days_ago = today - timedelta(days=6)
    seven_days_ago = resolve_trend_start(
        DailyMilkSummary.objects.filter(farm_id=farm_id), "date", nominal_seven_days_ago, today
    )
    summaries = {
        s.date: s.total_litres
        for s in DailyMilkSummary.objects.filter(
            farm_id=farm_id,
            date__gte=seven_days_ago,
            date__lte=today,
        )
    }
    production_trend = [
        {
            "date": d.isoformat(),
            "total_litres": float(summaries.get(d, 0)),
        }
        for d in daily_trend_range(seven_days_ago, today)
    ]

    from feed.models import FeedInventory, FeedIssuanceRecord, FeedConfirmationRecord

    feed_qs = FeedInventory.objects.filter(farm_id=farm_id)
    total_stock = feed_qs.aggregate(total=Sum("quantity_available"))["total"] or 0
    low_stock_items = list(
        feed_qs.filter(status="low_stock").values("id", "feed_name", "quantity_available", "unit", "reorder_level")
    )

    total_issued = (
        FeedIssuanceRecord.objects.filter(farm_id=farm_id)
        .aggregate(total=Sum("quantity_issued"))["total"] or 0
    )
    total_used = (
        FeedConfirmationRecord.objects.filter(farm__id=farm_id)
        .aggregate(total=Sum("actual_used_quantity"))["total"] or 0
    )
    variance_alerts = list(
        FeedConfirmationRecord.objects.select_related("issuance__feed_inventory")
        .filter(farm__id=farm_id, status="variance_detected")
        .order_by("-confirmation_date")[:5]
        .values(
            "id",
            "issuance__feed_inventory__feed_name",
            "issuance__quantity_issued",
            "actual_used_quantity",
            "variance_quantity",
            "confirmation_date",
        )
    )

    recent_weights_qs = AnimalWeight.objects.select_related("animal").filter(
        farm_id=farm_id
    ).order_by("-date", "-created_at")[:5]
    recent_weights = [
        {
            "id": w.id,
            "animal_id": w.animal.id,
            "animal_tag": w.animal.tag_id,
            "date": w.date,
            "weight": w.weight,
        }
        for w in recent_weights_qs
    ]

    data = {
        "milk_today": milk_today,
        "production_trend": production_trend,
        "recent_weights": recent_weights,
        "feed": {
            "total_stock": total_stock,
            "low_stock_items": low_stock_items,
            "total_issued": total_issued,
            "total_used": total_used,
            "variance_alerts": variance_alerts,
        },
        "total": dashboard.total_animals,
        "active": dashboard.active,
        "healthy": dashboard.healthy,
        "lactating": dashboard.lactating,
        "pregnant": dashboard.pregnant,
        "sick": dashboard.sick,
        "quarantine": dashboard.quarantine,
        "deaths": dashboard.deaths,
        "sales": dashboard.sales,
        "species_distribution": species_distribution,
        "treatment_followups": treatment_followups,
        "vaccination_upcoming_records": vaccination_upcoming_records,
        "updated_at": dashboard.updated_at,
    }
    return 200, APIResponse(success=True, message="Animal dashboard", data=data)


@router.get("/livestock-dashboard/{farm_id}", response={200: APIResponse, 403: APIResponse})
def livestock_dashboard(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Reports.LIVESTOCK_DASHBOARD)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from health.models import MortalityRecord

    base_qs = Animal.objects.filter(farm_id=farm_id)

    # ── Summary stats ──────────────────────────────────────────────────────────
    summary = base_qs.aggregate(
        total=Count("id"),
        male=Count("id", filter=Q(gender="male")),
        female=Count("id", filter=Q(gender="female")),
        pregnant=Count("id", filter=Q(is_pregnant=True)),
        lactating=Count("id", filter=Q(is_lactating=True)),
        sick=Count("id", filter=Q(health_status="sick")),
        active=Count("id", filter=Q(is_active=True)),
    )

    # ── Recent added animals (last 5) ──────────────────────────────────────────
    recent_animals = list(
        base_qs.select_related("species")
        .order_by("-created_at")[:5]
        .values("id", "tag_id", "gender", "species__name", "created_at")
    )

    # ── 4 Health risks ─────────────────────────────────────────────────────────
    health_risk_qs = (
        base_qs.select_related("species")
        .filter(health_status__in=["sick", "at_risk"])
        .order_by("-updated_at")[:4]
    )
    health_risks = [
        {
            "id": a.id,
            "tag_id": a.tag_id,
            "species": a.species.name if a.species else None,
            "health_status": a.health_status,
            "is_quarantine": a.is_quarantine,
        }
        for a in health_risk_qs
    ]

    # ── Ready for sale (4) ─────────────────────────────────────────────────────
    ready_for_sale_qs = (
        base_qs.select_related("species", "breed")
        .filter(
            status="active",
            is_active=True,
            health_status="healthy",
            is_pregnant=False,
            is_lactating=False,
        )
        .order_by("-created_at")[:4]
    )
    ready_for_sale = [
        {
            "id": a.id,
            "tag_id": a.tag_id,
            "species": a.species.name if a.species else None,
            "breed": a.breed.name if a.breed else None,
            "gender": a.gender,
            "dob": a.dob,
        }
        for a in ready_for_sale_qs
    ]

    # ── Livestock population trend (last 12 months) ────────────────────────────
    today = timezone.localdate()
    nominal_month_start = today.replace(day=1) - relativedelta(months=11)
    current_month_start = today.replace(day=1)
    population_window_start = resolve_trend_start(base_qs, "created_at", nominal_month_start, current_month_start)
    population_trend = []
    for month_start in monthly_trend_range(population_window_start, current_month_start):
        month_end = month_start + relativedelta(months=1)
        count = base_qs.filter(created_at__date__gte=month_start, created_at__date__lt=month_end).count()
        population_trend.append({
            "month": month_start.strftime("%Y-%m"),
            "count": count,
        })

    # ── Birth trend Mon–Sun this week ──────────────────────────────────────────
    week_monday = today - timedelta(days=today.weekday())
    week_sunday = week_monday + timedelta(days=6)
    births_base_qs = base_qs.filter(source_type="born")
    birth_week_start = resolve_trend_start(births_base_qs, "dob", week_monday, week_sunday)
    birth_by_day = {d: 0 for d in daily_trend_range(birth_week_start, week_sunday)}
    births_qs = births_base_qs.filter(
        dob__gte=birth_week_start,
        dob__lte=week_sunday,
    ).values("dob").annotate(count=Count("id"))
    for row in births_qs:
        if row["dob"] in birth_by_day:
            birth_by_day[row["dob"]] = row["count"]
    birth_trend = [
        {"day": d.strftime("%A"), "date": d.isoformat(), "count": birth_by_day[d]}
        for d in sorted(birth_by_day)
    ]

    # ── Mortality trend Mon–Sun this week ──────────────────────────────────────
    mortality_base_qs = MortalityRecord.objects.filter(farm_id=farm_id)
    mortality_week_start = resolve_trend_start(mortality_base_qs, "death_date", week_monday, week_sunday)
    mortality_by_day = {d: 0 for d in daily_trend_range(mortality_week_start, week_sunday)}
    mortality_qs = mortality_base_qs.filter(
        death_date__gte=mortality_week_start,
        death_date__lte=week_sunday,
    ).values("death_date").annotate(count=Count("id"))
    for row in mortality_qs:
        if row["death_date"] in mortality_by_day:
            mortality_by_day[row["death_date"]] = row["count"]
    mortality_trend = [
        {"day": d.strftime("%A"), "date": d.isoformat(), "count": mortality_by_day[d]}
        for d in sorted(mortality_by_day)
    ]

    # ── Exceptions (quarantine + at_risk) ──────────────────────────────────────
    exceptions_qs = (
        base_qs.select_related("species")
        .filter(Q(is_quarantine=True) | Q(health_status="at_risk"))
        .order_by("-updated_at")
    )
    exceptions = [
        {
            "id": a.id,
            "tag_id": a.tag_id,
            "species": a.species.name if a.species else None,
            "health_status": a.health_status,
            "is_quarantine": a.is_quarantine,
            "status": a.status,
        }
        for a in exceptions_qs
    ]

    data = {
        "summary": summary,
        "recent_animals": recent_animals,
        "health_risks": health_risks,
        "ready_for_sale": ready_for_sale,
        "population_trend": population_trend,
        "birth_trend": birth_trend,
        "mortality_trend": mortality_trend,
        "exceptions": exceptions,
    }
    return 200, APIResponse(success=True, message="Livestock dashboard", data=data)


@router.get("/animal-dashboard/{farm_id}", response={200: APIResponse, 403: APIResponse})
def animal_dashboard(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Animal.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    base_qs = Animal.objects.filter(farm_id=farm_id)

    stats = base_qs.aggregate(
        total_animals=Count("id"),
        pregnant=Count("id", filter=Q(is_pregnant=True)),
        sick=Count("id", filter=Q(health_status="sick")),
        quarantine=Count("id", filter=Q(is_quarantine=True)),
    )

    today = timezone.localdate()

    def calc_age(animal):
        if animal.dob:
            delta = today - animal.dob
            months = delta.days // 30
            if months < 12:
                return f"{months}m"
            return f"{months // 12}y {months % 12}m"
        if animal.estimated_age_months:
            m = animal.estimated_age_months
            if m < 12:
                return f"{m}m"
            return f"{m // 12}y {m % 12}m"
        return None

    recent_qs = (
        base_qs.select_related("species", "breed")
        .order_by("-created_at")[:10]
    )
    recent_animals = [
        {
            "animal_id":a.id,
            "tag_id": a.tag_id,
            "species": a.species.name,
            "breed": a.breed.name,
            "gender": a.gender,
            "age": calc_age(a),
            "status": a.status,
        }
        for a in recent_qs
    ]

    data = {
        "total_animals": stats["total_animals"],
        "pregnant": stats["pregnant"],
        "sick": stats["sick"],
        "quarantine": stats["quarantine"],
        "recent_animals": recent_animals,
    }
    return 200, APIResponse(success=True, message="Animal dashboard", data=data)


@router.get("/reproduction-dashboard/{farm_id}", response={200: APIResponse, 403: APIResponse})
def reproduction_dashboard(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Reproduction.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from reproduction.models import InseminationRecord, PregnancyRecord, BirthRecord

    today = timezone.localdate()
    thirty_days_ago = today - timedelta(days=30)

    # ── Top stats ──────────────────────────────────────────────────────────────
    total_female = Animal.objects.filter(farm_id=farm_id, gender="female").count()

    inseminated_recent = InseminationRecord.objects.filter(
        farm_id=farm_id,
        service_date__gte=thirty_days_ago,
    ).count()

    pregnant_count = Animal.objects.filter(farm_id=farm_id, is_pregnant=True).count()

    due_for_delivery = PregnancyRecord.objects.filter(
        farm_id=farm_id,
        result="pregnant",
        expected_delivery_date__gte=today,
        expected_delivery_date__lte=today + timedelta(days=30),
    ).count()

    failed_insemination = PregnancyRecord.objects.filter(
        farm_id=farm_id,
        result="not_pregnant",
    ).count()

    # ── Pregnancy due soon (5) ─────────────────────────────────────────────────
    due_soon_qs = (
        PregnancyRecord.objects.select_related("animal")
        .filter(farm_id=farm_id, result="pregnant", expected_delivery_date__gte=today)
        .order_by("expected_delivery_date")[:5]
    )
    pregnancy_due_soon = [
        {
            "animal_id": r.animal.id,
            "tag_id": r.animal.tag_id,
            "expected_delivery_date": r.expected_delivery_date,
            "status": "Pregnant",
        }
        for r in due_soon_qs
    ]

    # ── Pregnancy trend (monthly, current year) ────────────────────────────────
    pregnancy_trend = []
    for month in range(1, today.month + 1):
        month_start = today.replace(month=month, day=1)
        month_end = today.replace(month=month + 1, day=1) if month < 12 else today.replace(year=today.year + 1, month=1, day=1)
        count = PregnancyRecord.objects.filter(
            farm_id=farm_id,
            result="pregnant",
            check_date__gte=month_start,
            check_date__lt=month_end,
        ).count()
        pregnancy_trend.append({
            "month": month_start.strftime("%b"),
            "year_month": month_start.strftime("%Y-%m"),
            "count": count,
        })

    # ── Birth trend (monthly, full year Jan–Dec) ───────────────────────────────
    birth_trend = []
    for month in range(1, 13):
        month_start = today.replace(month=month, day=1)
        month_end = today.replace(month=month + 1, day=1) if month < 12 else today.replace(year=today.year + 1, month=1, day=1)
        total = BirthRecord.objects.filter(
            farm_id=farm_id,
            birth_date__gte=month_start,
            birth_date__lt=month_end,
        ).aggregate(total=Sum("number_alive"))["total"] or 0
        birth_trend.append({
            "month": month_start.strftime("%b"),
            "year_month": month_start.strftime("%Y-%m"),
            "count": total,
        })

    # ── Failed cases ───────────────────────────────────────────────────────────
    failed_qs = (
        PregnancyRecord.objects.select_related("animal", "animal__species", "insemination")
        .filter(farm_id=farm_id, result="not_pregnant")
        .order_by("-check_date")[:5]
    )
    failed_cases = [
        {
            "animal_id": r.animal.id,
            "tag_id": r.animal.tag_id,
            "species": r.animal.species.name,
            "service_date": r.insemination.service_date if r.insemination else None,
            "check_date": r.check_date,
            "status": "Failed",
        }
        for r in failed_qs
    ]

    # ── Recently inseminated ───────────────────────────────────────────────────
    recent_insem_qs = (
        InseminationRecord.objects.select_related("animal")
        .prefetch_related("pregnancy_records")
        .filter(farm_id=farm_id)
        .order_by("-service_date")[:10]
    )
    recently_inseminated = []
    for rec in recent_insem_qs:
        pregnancy = rec.pregnancy_records.order_by("-check_date").first()
        if pregnancy is None:
            status = "Pending"
        elif pregnancy.result == "pregnant":
            status = "Success"
        else:
            status = "Failed"
        recently_inseminated.append({
            "animal_id": rec.animal.id,
            "tag_id": rec.animal.tag_id,
            "service_date": rec.service_date,
            "method": rec.method,
            "status": status,
        })

    data = {
        "stats": {
            "total_female": total_female,
            "inseminated_recent": inseminated_recent,
            "pregnant": pregnant_count,
            "due_for_delivery": due_for_delivery,
            "failed_insemination": failed_insemination,
        },
        "pregnancy_due_soon": pregnancy_due_soon,
        "pregnancy_trend": pregnancy_trend,
        "birth_trend": birth_trend,
        "failed_cases": failed_cases,
        "recently_inseminated": recently_inseminated,
    }
    return 200, APIResponse(success=True, message="Reproduction dashboard", data=data)


@router.get("/health-dashboard/{farm_id}", response={200: APIResponse, 403: APIResponse})
def health_dashboard(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Health.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from health.models import TreatmentRecord, VaccinationRecord, QuarantineRecord

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())
    week_sunday = week_monday + timedelta(days=6)

    # ── Top stats ──────────────────────────────────────────────────────────────
    sick_animals = Animal.objects.filter(farm_id=farm_id, health_status="sick").count()

    under_treatment = TreatmentRecord.objects.filter(
        farm_id=farm_id,
        next_follow_up_date__gte=today,
        animal__isnull=False,
    ).values("animal_id").distinct().count()

    vaccination_due = VaccinationRecord.objects.filter(
        farm_id=farm_id,
        next_due_date__gte=today,
        animal__isnull=False,
    ).count()

    quarantine_count = QuarantineRecord.objects.filter(
        farm_id=farm_id,
        status="active",
    ).count()

    recovered = Animal.objects.filter(farm_id=farm_id, health_status="recovering").count()

    # ── Disease trend Mon–Sun this week ────────────────────────────────────────
    disease_base_qs = TreatmentRecord.objects.filter(farm_id=farm_id)
    disease_week_start = resolve_trend_start(disease_base_qs, "treatment_date", week_monday, week_sunday)
    disease_by_day = {d: 0 for d in daily_trend_range(disease_week_start, week_sunday)}
    disease_qs = (
        disease_base_qs.filter(
            treatment_date__gte=disease_week_start,
            treatment_date__lte=week_sunday,
        )
        .values("treatment_date")
        .annotate(count=Count("id"))
    )
    for row in disease_qs:
        if row["treatment_date"] in disease_by_day:
            disease_by_day[row["treatment_date"]] = row["count"]
    disease_trend = [
        {"day": d.strftime("%a")[0], "date": d.isoformat(), "count": disease_by_day[d]}
        for d in sorted(disease_by_day)
    ]

    # ── Active treatments ──────────────────────────────────────────────────────
    active_treatments_qs = (
        TreatmentRecord.objects.select_related("animal")
        .filter(farm_id=farm_id, next_follow_up_date__gte=today, animal__isnull=False)
        .order_by("next_follow_up_date")[:6]
    )
    active_treatments = [
        {
            "id": t.id,
            "animal_id": t.animal.id,
            "tag_id": t.animal.tag_id,
            "diagnosis": t.diagnosis,
            "treatment_date": t.treatment_date,
            "next_follow_up_date": t.next_follow_up_date,
            "severity": t.severity,
        }
        for t in active_treatments_qs
    ]

    # ── Treatment success rate (last 7 days) ───────────────────────────────────
    seven_days_ago = today - timedelta(days=6)
    recent_treatments = TreatmentRecord.objects.filter(
        farm_id=farm_id,
        treatment_date__gte=seven_days_ago,
    )
    total_recorded = recent_treatments.count()
    rate_recovered = recent_treatments.filter(
        animal__health_status="recovering"
    ).count()
    rate_ongoing = recent_treatments.filter(
        next_follow_up_date__gte=today
    ).count()
    rate_severe = recent_treatments.filter(severity="severe").count()

    treatment_success_rate = {
        "total_recorded": total_recorded,
        "recovered": rate_recovered,
        "ongoing_treatment": rate_ongoing,
        "severe": rate_severe,
    }

    # ── Vaccination due ────────────────────────────────────────────────────────
    vaccination_due_qs = (
        VaccinationRecord.objects.select_related("animal")
        .filter(farm_id=farm_id, next_due_date__gte=today, animal__isnull=False)
        .order_by("next_due_date")[:5]
    )
    vaccination_due_list = [
        {
            "id": v.id,
            "animal_id": v.animal.id,
            "tag_id": v.animal.tag_id,
            "vaccine_name": v.vaccine_name,
            "next_due_date": v.next_due_date,
        }
        for v in vaccination_due_qs
    ]

    # ── High risk alert ────────────────────────────────────────────────────────
    high_risk_qs = (
        TreatmentRecord.objects.select_related("animal", "animal__species")
        .filter(
            farm_id=farm_id,
            severity="severe",
            animal__isnull=False,
        )
        .order_by("next_follow_up_date")[:5]
    )
    high_risk_alerts = []
    for t in high_risk_qs:
        if t.next_follow_up_date and t.next_follow_up_date < today:
            overdue_days = (today - t.next_follow_up_date).days
            follow_up_status = f"Follow-up overdue by {overdue_days} day{'s' if overdue_days != 1 else ''}"
        elif t.next_follow_up_date:
            follow_up_status = f"Follow-up due {t.next_follow_up_date.isoformat()}"
        else:
            follow_up_status = "No follow-up scheduled"
        high_risk_alerts.append({
            "id": t.id,
            "animal_id": t.animal.id,
            "tag_id": t.animal.tag_id,
            "species": t.animal.species.name,
            "diagnosis": t.diagnosis,
            "severity": t.severity,
            "follow_up_status": follow_up_status,
            "next_follow_up_date": t.next_follow_up_date,
        })

    # ── Quarantine animals ─────────────────────────────────────────────────────
    quarantine_qs = (
        QuarantineRecord.objects.select_related("animal")
        .filter(farm_id=farm_id)
        .order_by("-start_date")[:6]
    )
    quarantine_animals = [
        {
            "id": q.id,
            "animal_id": q.animal.id,
            "tag_id": q.animal.tag_id,
            "reason": q.reason,
            "start_date": q.start_date,
            "end_date": q.end_date,
            "status": "Recovered" if q.status == "released" else "Quarantine",
        }
        for q in quarantine_qs
    ]

    data = {
        "stats": {
            "sick_animals": sick_animals,
            "under_treatment": under_treatment,
            "vaccination_due": vaccination_due,
            "quarantine_count": quarantine_count,
            "recovered": recovered,
        },
        "disease_trend": disease_trend,
        "active_treatments": active_treatments,
        "treatment_success_rate": treatment_success_rate,
        "vaccination_due_list": vaccination_due_list,
        "high_risk_alerts": high_risk_alerts,
        "quarantine_animals": quarantine_animals,
    }
    return 200, APIResponse(success=True, message="Health dashboard", data=data)


@router.get("/mortality-dashboard/{farm_id}", response={200: APIResponse, 403: APIResponse})
def mortality_dashboard(request, farm_id: int, page: int = 1, page_size: int = 10):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.MovementRecord.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from health.models import MortalityRecord

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    # ── Stats ──────────────────────────────────────────────────────────────────
    base_qs = MortalityRecord.objects.filter(farm_id=farm_id)

    deaths_today = base_qs.filter(death_date=today).count()
    deaths_this_week = base_qs.filter(death_date__gte=week_monday, death_date__lte=today).count()
    deaths_this_month = base_qs.filter(death_date__gte=month_start, death_date__lte=today).count()

    total_animals = Animal.objects.filter(farm_id=farm_id).count()
    mortality_rate = (
        round((deaths_this_month / total_animals) * 100, 1) if total_animals else 0
    )

    # ── Paginated mortality records ────────────────────────────────────────────
    records_qs = (
        base_qs.select_related("animal", "animal__species", "animal__breed", "created_by")
        .order_by("-death_date")
    )
    paginator = Paginator(records_qs, page_size)
    page_obj = paginator.page(page)

    records = [
        {
            "id": r.id,
            "animal_id": r.animal.id,
            "animal_tag": r.animal.tag_id,
            "species": r.animal.species.name,
            "breed": r.animal.breed.name,
            "cause": r.cause,
            "death_date": r.death_date,
            "recorded_by": (
                f"{r.created_by.first_name} {r.created_by.last_name}".strip()
                or r.created_by.email
            ) if r.created_by else None,
            "status": r.status.title(),
            "notes": r.notes,
        }
        for r in page_obj.object_list
    ]

    data = {
        "stats": {
            "deaths_today": deaths_today,
            "deaths_this_week": deaths_this_week,
            "deaths_this_month": deaths_this_month,
            "mortality_rate": mortality_rate,
        },
        "records": records,
        "num_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "total_items": paginator.count,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }
    return 200, APIResponse(success=True, message="Mortality dashboard", data=data)


@router.get("/transaction-dashboard/{farm_id}", response={200: APIResponse, 403: APIResponse})
def transaction_dashboard(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.SalesRecord.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from movement_records.models import SalesRecord
    from health.models import MortalityRecord

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())
    week_sunday = week_monday + timedelta(days=6)
    month_start = today.replace(day=1)

    # ── Top stats ──────────────────────────────────────────────────────────────
    sales_this_period = SalesRecord.objects.filter(
        farm_id=farm_id,
        sale_date__date__gte=month_start,
    ).count()

    total_sales_value = (
        SalesRecord.objects.filter(farm_id=farm_id, sale_date__date__gte=month_start)
        .aggregate(total=Sum("price"))["total"] or 0
    )

    mortality_this_period = MortalityRecord.objects.filter(
        farm_id=farm_id,
        death_date__gte=month_start,
    ).count()

    animals_exited = sales_this_period + mortality_this_period

    pending_corrections = MortalityRecord.objects.filter(
        farm_id=farm_id,
        status="recorded",
    ).count()

    # ── Exit summary by species ────────────────────────────────────────────────
    from django.db.models import Count as _Count
    species_sales = (
        SalesRecord.objects.filter(farm_id=farm_id, sale_date__date__gte=month_start)
        .values("animal__species__id", "animal__species__name")
        .annotate(sold=_Count("id"))
    )
    species_deaths = (
        MortalityRecord.objects.filter(farm_id=farm_id, death_date__gte=month_start)
        .values("animal__species__id", "animal__species__name")
        .annotate(deaths=_Count("id"))
    )

    species_sales_map = {r["animal__species__id"]: r for r in species_sales}
    species_deaths_map = {r["animal__species__id"]: r for r in species_deaths}
    all_species_ids = set(species_sales_map) | set(species_deaths_map)

    exit_summary = []
    for sid in all_species_ids:
        sold = species_sales_map.get(sid, {}).get("sold", 0)
        deaths = species_deaths_map.get(sid, {}).get("deaths", 0)
        name = (
            species_sales_map.get(sid) or species_deaths_map.get(sid)
        ).get("animal__species__name")
        exit_summary.append({
            "species_id": sid,
            "species": name,
            "sold": sold,
            "deaths": deaths,
            "total_exited": sold + deaths,
        })

    # ── Sales trend Mon–Sun this week ──────────────────────────────────────────
    sales_base_qs = SalesRecord.objects.filter(farm_id=farm_id)
    sales_week_start = resolve_trend_start(sales_base_qs, "sale_date", week_monday, week_sunday)
    sales_by_day = {d: 0 for d in daily_trend_range(sales_week_start, week_sunday)}
    sales_trend_qs = (
        sales_base_qs.filter(
            sale_date__date__gte=sales_week_start,
            sale_date__date__lte=week_sunday,
        )
        .values("sale_date__date")
        .annotate(count=_Count("id"))
    )
    for row in sales_trend_qs:
        d = row["sale_date__date"]
        if d in sales_by_day:
            sales_by_day[d] = row["count"]
    sales_trend = [
        {"day": d.strftime("%a")[0], "date": d.isoformat(), "count": sales_by_day[d]}
        for d in sorted(sales_by_day)
    ]

    # ── Mortality trend Mon–Sun this week ──────────────────────────────────────
    mortality_base_qs = MortalityRecord.objects.filter(farm_id=farm_id)
    mortality_week_start = resolve_trend_start(mortality_base_qs, "death_date", week_monday, week_sunday)
    mortality_by_day = {d: 0 for d in daily_trend_range(mortality_week_start, week_sunday)}
    mortality_trend_qs = (
        mortality_base_qs.filter(
            death_date__gte=mortality_week_start,
            death_date__lte=week_sunday,
        )
        .values("death_date")
        .annotate(count=_Count("id"))
    )
    for row in mortality_trend_qs:
        d = row["death_date"]
        if d in mortality_by_day:
            mortality_by_day[d] = row["count"]
    mortality_trend = [
        {"day": d.strftime("%a")[0], "date": d.isoformat(), "count": mortality_by_day[d]}
        for d in sorted(mortality_by_day)
    ]

    # ── High mortality alert ───────────────────────────────────────────────────
    last_30_days = today - timedelta(days=30)
    disease_deaths = (
        MortalityRecord.objects.filter(farm_id=farm_id, death_date__gte=last_30_days)
        .count()
    )
    alert_message = None
    if disease_deaths >= 2:
        month_name = today.strftime("%B")
        alert_message = (
            f"Abnormal pattern detected: {disease_deaths} disease-linked deaths in "
            f"{month_name}. Review herd health status and check vaccination schedules."
        )

    alert_animals = list(
        Animal.objects.select_related("species")
        .filter(farm_id=farm_id, health_status="at_risk")
        .values("id", "tag_id", "species__name")[:5]
    )
    high_mortality_alert = {
        "message": alert_message,
        "animals": [
            {
                "animal_id": a["id"],
                "tag_id": a["tag_id"],
                "species": a["species__name"],
                "level": "Alert",
            }
            for a in alert_animals
        ],
    }

    # ── Recent sales ───────────────────────────────────────────────────────────
    recent_sales_qs = (
        SalesRecord.objects.select_related("animal", "animal__species")
        .filter(farm_id=farm_id)
        .order_by("-sale_date")[:5]
    )
    recent_sales = [
        {
            "id": s.id,
            "animal_id": s.animal.id,
            "animal_tag": s.animal.tag_id,
            "species": s.animal.species.name,
            "buyer_name": s.buyer_name,
            "price": s.price,
            "sale_date": s.sale_date.date(),
        }
        for s in recent_sales_qs
    ]

    # ── Recent mortality ───────────────────────────────────────────────────────
    recent_mortality_qs = (
        MortalityRecord.objects.select_related("animal", "animal__species")
        .filter(farm_id=farm_id)
        .order_by("-death_date")[:5]
    )
    recent_mortality = [
        {
            "id": m.id,
            "animal_id": m.animal.id,
            "animal_tag": m.animal.tag_id,
            "species": m.animal.species.name,
            "cause": m.cause,
            "death_date": m.death_date,
            "status": m.status,
        }
        for m in recent_mortality_qs
    ]

    data = {
        "stats": {
            "sales_this_period": sales_this_period,
            "total_sales_value": total_sales_value,
            "mortality_this_period": mortality_this_period,
            "animals_exited": animals_exited,
            "pending_corrections": pending_corrections,
        },
        "exit_summary": exit_summary,
        "sales_trend": sales_trend,
        "mortality_trend": mortality_trend,
        "high_mortality_alert": high_mortality_alert,
        "recent_sales": recent_sales,
        "recent_mortality": recent_mortality,
    }
    return 200, APIResponse(success=True, message="Transaction dashboard", data=data)


@router.get("/sales-dashboard/{farm_id}", response={200: APIResponse, 403: APIResponse})
def sales_dashboard(
    request,
    farm_id: int,
    page: int = 1,
    page_size: int = 10,
    status: str = None,
    species_id: int = None,
    date_from: str = None,
    date_to: str = None,
    search: str = None,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.SalesRecord.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from movement_records.models import SalesRecord

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    # ── Top stats (always unfiltered) ──────────────────────────────────────────
    base_stats = SalesRecord.objects.filter(farm_id=farm_id)

    sales_today = base_stats.filter(sale_date__date=today).count()
    sales_this_week = base_stats.filter(sale_date__date__gte=week_monday).count()
    sales_this_month = base_stats.filter(sale_date__date__gte=month_start).count()
    total_sales_value = (
        base_stats.filter(sale_date__date__gte=month_start)
        .aggregate(total=Sum("price"))["total"] or 0
    )

    # ── Filtered records ───────────────────────────────────────────────────────
    qs = (
        SalesRecord.objects.select_related(
            "animal", "animal__species", "animal__breed", "created_by"
        )
        .filter(farm_id=farm_id)
        .order_by("-sale_date")
    )

    if status:
        qs = qs.filter(status=status)
    if species_id:
        qs = qs.filter(animal__species_id=species_id)
    if date_from:
        qs = qs.filter(sale_date__date__gte=date_from)
    if date_to:
        qs = qs.filter(sale_date__date__lte=date_to)
    if search:
        qs = qs.filter(
            Q(animal__tag_id__icontains=search) | Q(buyer_name__icontains=search)
        )

    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)

    records = [
        {
            "id": s.id,
            "animal_id": s.animal.id,
            "animal_tag": s.animal.tag_id,
            "species": s.animal.species.name,
            "breed": s.animal.breed.name,
            "buyer": s.buyer_name,
            "price": s.price,
            "sale_date": s.sale_date.date(),
            "recorded_by": (
                f"{s.created_by.first_name} {s.created_by.last_name}".strip()
                or s.created_by.email
            ) if s.created_by else None,
            "status": s.status.title(),
        }
        for s in page_obj.object_list
    ]

    data = {
        "stats": {
            "sales_today": sales_today,
            "sales_this_week": sales_this_week,
            "sales_this_month": sales_this_month,
            "total_sales_value": total_sales_value,
        },
        "records": records,
        "num_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "total_items": paginator.count,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }
    return 200, APIResponse(success=True, message="Sales dashboard", data=data)


@router.get("/feed-inventory-dashboard/{farm_id}", response={200: APIResponse, 403: APIResponse})
def feed_inventory_dashboard(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Feed.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from feed.models import FeedInventory, FeedIssuanceRecord, FeedConfirmationRecord, FeedPlan

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())
    week_sunday = week_monday + timedelta(days=6)

    # ── Top stats ──────────────────────────────────────────────────────────────
    inventory_qs = FeedInventory.objects.filter(farm_id=farm_id)

    total_stock_agg = inventory_qs.aggregate(total=Sum("quantity_available"))
    total_stock = total_stock_agg["total"] or 0
    top_stock_item = inventory_qs.order_by("-quantity_available").values("feed_name").first()
    top_stock_name = top_stock_item["feed_name"] if top_stock_item else None

    low_stock_qs = inventory_qs.filter(status="low_stock")
    low_stock_count = low_stock_qs.count()
    low_stock_names = ", ".join(low_stock_qs.values_list("feed_name", flat=True)[:3])

    issuance_today_qs = FeedIssuanceRecord.objects.filter(farm_id=farm_id, issue_date=today)
    feed_issued_today = issuance_today_qs.aggregate(total=Sum("quantity_issued"))["total"] or 0
    top_issued_item = (
        issuance_today_qs.values("feed_inventory__feed_name")
        .annotate(total=Sum("quantity_issued"))
        .order_by("-total")
        .first()
    )
    top_issued_name = top_issued_item["feed_inventory__feed_name"] if top_issued_item else None

    confirmed_today_qs = FeedConfirmationRecord.objects.filter(
        farm__id=farm_id, confirmation_date=today
    )
    feed_confirmed_today = confirmed_today_qs.aggregate(total=Sum("actual_used_quantity"))["total"] or 0
    top_confirmed_item = (
        confirmed_today_qs.values("issuance__feed_inventory__feed_name")
        .annotate(total=Sum("actual_used_quantity"))
        .order_by("-total")
        .first()
    )
    top_confirmed_name = (
        top_confirmed_item["issuance__feed_inventory__feed_name"] if top_confirmed_item else None
    )

    variance_alerts = (
        FeedConfirmationRecord.objects.filter(farm__id=farm_id, status="variance_detected")
        .aggregate(total=Sum("variance_quantity"))["total"] or 0
    )

    # Pending = issuances without a confirmation record
    pending_issuance_ids = FeedConfirmationRecord.objects.filter(
        farm__id=farm_id
    ).values_list("issuance_id", flat=True)
    pending_qty = (
        FeedIssuanceRecord.objects.filter(farm_id=farm_id)
        .exclude(id__in=pending_issuance_ids)
        .aggregate(total=Sum("quantity_issued"))["total"] or 0
    )

    # ── Stock trend Mon–Sun this week ──────────────────────────────────────────
    issuance_base_qs = FeedIssuanceRecord.objects.filter(farm_id=farm_id)
    feed_week_start = resolve_trend_start(issuance_base_qs, "issue_date", week_monday, week_sunday)
    stock_by_day = {d: 0 for d in daily_trend_range(feed_week_start, week_sunday)}
    stock_trend_qs = (
        issuance_base_qs.filter(
            issue_date__gte=feed_week_start,
            issue_date__lte=week_sunday,
        )
        .values("issue_date")
        .annotate(total=Sum("quantity_issued"))
    )
    for row in stock_trend_qs:
        if row["issue_date"] in stock_by_day:
            stock_by_day[row["issue_date"]] = float(row["total"])
    stock_trend = [
        {"day": d.strftime("%a")[0], "date": d.isoformat(), "total_issued": stock_by_day[d]}
        for d in sorted(stock_by_day)
    ]

    # ── Pending confirmations list ─────────────────────────────────────────────
    pending_conf_qs = (
        FeedIssuanceRecord.objects.select_related("feed_inventory", "group", "animal")
        .filter(farm_id=farm_id)
        .exclude(id__in=pending_issuance_ids)
        .order_by("-issue_date")[:5]
    )
    pending_confirmations = [
        {
            "id": r.id,
            "target": r.group.name if r.group else (r.animal.tag_id if r.animal else None),
            "target_type": r.target_type,
            "feed_name": r.feed_inventory.feed_name,
            "quantity_issued": r.quantity_issued,
            "issue_date": r.issue_date,
            "status": "Pending",
        }
        for r in pending_conf_qs
    ]

    # ── Issued vs Used Feed Mon–Sun this week ──────────────────────────────────
    # shares feed_week_start with the stock trend above so both series cover the
    # same days (used_by_day must have every key issued_by_day has)
    issued_by_day = {d: 0 for d in daily_trend_range(feed_week_start, week_sunday)}
    used_by_day = {d: 0 for d in daily_trend_range(feed_week_start, week_sunday)}

    for row in stock_trend_qs:
        if row["issue_date"] in issued_by_day:
            issued_by_day[row["issue_date"]] = float(row["total"])

    used_qs = (
        FeedConfirmationRecord.objects.filter(
            farm__id=farm_id,
            confirmation_date__gte=feed_week_start,
            confirmation_date__lte=week_sunday,
        )
        .values("confirmation_date")
        .annotate(total=Sum("actual_used_quantity"))
    )
    for row in used_qs:
        if row["confirmation_date"] in used_by_day:
            used_by_day[row["confirmation_date"]] = float(row["total"])

    issued_vs_used = [
        {
            "day": d.strftime("%a")[0],
            "date": d.isoformat(),
            "issued": issued_by_day[d],
            "used": used_by_day[d],
            "usage_pct": (
                round((used_by_day[d] / issued_by_day[d]) * 100, 1)
                if issued_by_day[d] else 0
            ),
        }
        for d in sorted(issued_by_day)
    ]

    # ── Issuance vs Confirmation today ────────────────────────────────────────
    today_issued = float(feed_issued_today)
    today_confirmed = float(feed_confirmed_today)
    issuance_vs_confirmation = {
        "issued": today_issued,
        "confirmed": today_confirmed,
        "difference": round(today_issued - today_confirmed, 2),
    }

    # ── Low stock levels ──────────────────────────────────────────────────────
    low_stock_levels = [
        {
            "id": item.id,
            "feed_name": item.feed_name,
            "quantity_available": item.quantity_available,
            "unit": item.unit,
            "reorder_level": item.reorder_level,
            "status": item.status,
        }
        for item in low_stock_qs.order_by("quantity_available")[:5]
    ]

    # ── Feed plan summary ─────────────────────────────────────────────────────
    feed_plan_qs = (
        FeedPlan.objects.select_related("feed_inventory", "species", "group")
        .filter(farm_id=farm_id, status="active")
        .order_by("-start_date")[:5]
    )
    feed_plan_summary = [
        {
            "id": p.id,
            "plan_type": p.plan_type,
            "target": p.species.name if p.species else (p.group.name if p.group else None),
            "feed_name": p.feed_inventory.feed_name,
            "daily_feed_quantity": p.daily_feed_quantity,
            "unit": p.unit,
            "start_date": p.start_date,
            "end_date": p.end_date,
            "status": p.status,
        }
        for p in feed_plan_qs
    ]

    data = {
        "stats": {
            "total_stock": total_stock,
            "top_stock_feed": top_stock_name,
            "low_stock_count": low_stock_count,
            "low_stock_names": low_stock_names,
            "feed_issued_today": feed_issued_today,
            "top_issued_feed": top_issued_name,
            "feed_confirmed_today": feed_confirmed_today,
            "top_confirmed_feed": top_confirmed_name,
            "variance_alerts": variance_alerts,
            "pending_feed_confirmation": pending_qty,
        },
        "stock_trend": stock_trend,
        "pending_confirmations": pending_confirmations,
        "issued_vs_used": issued_vs_used,
        "issuance_vs_confirmation_today": issuance_vs_confirmation,
        "low_stock_levels": low_stock_levels,
        "feed_plan_summary": feed_plan_summary,
    }
    return 200, APIResponse(success=True, message="Feed & inventory dashboard", data=data)


@router.get("/inventory-dashboard/{farm_id}", response={200: APIResponse, 403: APIResponse})
def inventory_dashboard(
    request,
    farm_id: int,
    page: int = 1,
    page_size: int = 10,
    status: str = None,
    search: str = None,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Feed.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from feed.models import FeedInventory

    base_qs = FeedInventory.objects.filter(farm_id=farm_id)

    # ── Stats (always unfiltered) ──────────────────────────────────────────────
    total_quantity = base_qs.aggregate(total=Sum("quantity_available"))["total"] or 0
    total_feed_types = base_qs.count()
    low_stock_count = base_qs.filter(status="low_stock").count()

    # ── Filtered + paginated table ─────────────────────────────────────────────
    qs = base_qs.order_by("feed_name")

    if status:
        qs = qs.filter(status=status)
    if search:
        qs = qs.filter(feed_name__icontains=search)

    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)

    records = [
        {
            "id": item.id,
            "feed_name": item.feed_name,
            "quantity": item.quantity_available,
            "unit": item.unit,
            "reorder_level": item.reorder_level,
            "status": item.status.replace("_", " ").title(),
            "last_updated": item.updated_at.date(),
            "last_restocked_at": item.last_restocked_at,
        }
        for item in page_obj.object_list
    ]

    data = {
        "stats": {
            "total_quantity": total_quantity,
            "total_feed_types": total_feed_types,
            "low_stock_count": low_stock_count,
        },
        "records": records,
        "num_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "total_items": paginator.count,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }
    return 200, APIResponse(success=True, message="Inventory dashboard", data=data)


@router.get("/feed-plan-dashboard/{farm_id}", response={200: APIResponse, 403: APIResponse})
def feed_plan_dashboard(
    request,
    farm_id: int,
    page: int = 1,
    page_size: int = 10,
    plan_type: str = None,
    status: str = None,
    search: str = None,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Feed.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from feed.models import FeedPlan

    base_qs = FeedPlan.objects.filter(farm_id=farm_id)

    # ── Stats (always unfiltered) ──────────────────────────────────────────────
    active_plans = base_qs.filter(status="active").count()
    species_based_plans = base_qs.filter(plan_type="species").count()
    group_based_plans = base_qs.filter(plan_type="group").count()

    # ── Filtered + paginated table ─────────────────────────────────────────────
    qs = (
        base_qs
        .select_related("feed_inventory", "species", "group")
        .order_by("-start_date")
    )

    if plan_type:
        qs = qs.filter(plan_type=plan_type)
    if status:
        qs = qs.filter(status=status)
    if search:
        qs = qs.filter(
            Q(feed_inventory__feed_name__icontains=search)
            | Q(species__name__icontains=search)
            | Q(group__name__icontains=search)
        )

    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)

    records = []
    for p in page_obj.object_list:
        if p.plan_type == "species":
            target_name = p.species.name if p.species else None
            target_count = (
                Animal.objects.filter(farm_id=farm_id, species=p.species, is_active=True).count()
                if p.species else 0
            )
        else:
            target_name = p.group.name if p.group else None
            target_count = (
                p.group.members.filter(status="active").count()
                if p.group else 0
            )

        records.append({
            "id": p.id,
            "plan_name": p.feed_inventory.feed_name,
            "plan_type": p.plan_type,
            "target_type": target_name,
            "target_count": target_count,
            "daily_feed_quantity": p.daily_feed_quantity,
            "unit": p.unit,
            "feed_inventory_status": p.feed_inventory.status.replace("_", " ").title(),
            "plan_status": p.status,
            "start_date": p.start_date,
            "end_date": p.end_date,
        })

    data = {
        "stats": {
            "active_plans": active_plans,
            "species_based_plans": species_based_plans,
            "group_based_plans": group_based_plans,
        },
        "records": records,
        "num_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "total_items": paginator.count,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }
    return 200, APIResponse(success=True, message="Feed plan dashboard", data=data)


@router.get("/feed-issuance-dashboard/{farm_id}", response={200: APIResponse, 403: APIResponse})
def feed_issuance_dashboard(
    request,
    farm_id: int,
    page: int = 1,
    page_size: int = 10,
    status: str = None,
    search: str = None,
    date_from: str = None,
    date_to: str = None,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Feed.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from feed.models import FeedIssuanceRecord, FeedConfirmationRecord

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())

    base_qs = FeedIssuanceRecord.objects.filter(farm_id=farm_id)

    # ── Stats (always unfiltered) ──────────────────────────────────────────────
    issued_today = base_qs.filter(issue_date=today).count()
    issued_this_week = base_qs.filter(issue_date__gte=week_monday).count()

    confirmed_ids = FeedConfirmationRecord.objects.filter(
        farm__id=farm_id
    ).values_list("issuance_id", flat=True)
    pending_confirmation = base_qs.exclude(id__in=confirmed_ids).count()

    # ── Filtered + paginated table ─────────────────────────────────────────────
    qs = (
        base_qs
        .select_related(
            "feed_inventory", "animal", "group", "issued_by"
        )
        .order_by("-issue_date", "-created_at")
    )

    if date_from:
        qs = qs.filter(issue_date__gte=date_from)
    if date_to:
        qs = qs.filter(issue_date__lte=date_to)
    if search:
        qs = qs.filter(
            Q(feed_inventory__feed_name__icontains=search)
            | Q(animal__tag_id__icontains=search)
            | Q(group__name__icontains=search)
        )

    # status filter: confirmed / pending
    if status == "confirmed":
        qs = qs.filter(id__in=confirmed_ids)
    elif status == "pending":
        qs = qs.exclude(id__in=confirmed_ids)

    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)

    confirmed_set = set(confirmed_ids)
    records = []
    for r in page_obj.object_list:
        if r.target_type == "group":
            target = r.group.name if r.group else None
        else:
            target = r.animal.tag_id if r.animal else None

        issued_by_name = None
        if r.issued_by:
            full = f"{r.issued_by.first_name} {r.issued_by.last_name}".strip()
            issued_by_name = full or r.issued_by.email

        records.append({
            "id": r.id,
            "feed_type": r.feed_inventory.feed_name,
            "target_type": target,
            "target_kind": r.target_type,
            "quantity_issued": r.quantity_issued,
            "unit": r.feed_inventory.unit,
            "issue_date": r.issue_date,
            "issued_by": issued_by_name,
            "status": "Confirmed" if r.id in confirmed_set else "Pending",
        })

    data = {
        "stats": {
            "issued_today": issued_today,
            "issued_this_week": issued_this_week,
            "issuances_pending_confirmation": pending_confirmation,
        },
        "records": records,
        "num_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "total_items": paginator.count,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }
    return 200, APIResponse(success=True, message="Feed issuance dashboard", data=data)


@router.get("/feed-confirmation-dashboard/{farm_id}", response={200: APIResponse, 403: APIResponse})
def feed_confirmation_dashboard(
    request,
    farm_id: int,
    page: int = 1,
    page_size: int = 10,
    status: str = None,
    search: str = None,
    date_from: str = None,
    date_to: str = None,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Feed.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from feed.models import FeedIssuanceRecord, FeedConfirmationRecord

    today = timezone.localdate()

    confirmed_ids = FeedConfirmationRecord.objects.filter(
        farm__id=farm_id
    ).values_list("issuance_id", flat=True)

    # ── Stats (always unfiltered) ──────────────────────────────────────────────
    pending_confirmation = FeedIssuanceRecord.objects.filter(
        farm_id=farm_id
    ).exclude(id__in=confirmed_ids).count()

    confirmed_today = FeedConfirmationRecord.objects.filter(
        farm__id=farm_id,
        confirmation_date=today,
    ).count()

    total_confirmations = FeedConfirmationRecord.objects.filter(farm__id=farm_id).count()
    variance_count = FeedConfirmationRecord.objects.filter(
        farm__id=farm_id, status="variance_detected"
    ).count()
    variance_pct = (
        round((variance_count / total_confirmations) * 100, 1)
        if total_confirmations else 0
    )

    # ── Unified list: confirmed records + pending issuances ────────────────────
    # Build confirmed rows from FeedConfirmationRecord
    conf_qs = (
        FeedConfirmationRecord.objects.select_related(
            "issuance__feed_inventory",
            "issuance__animal",
            "issuance__group",
            "confirmed_by",
        )
        .filter(farm__id=farm_id)
        .order_by("-confirmation_date")
    )

    # Build pending rows from issuances without confirmation
    pend_qs = (
        FeedIssuanceRecord.objects.select_related(
            "feed_inventory", "animal", "group", "issued_by"
        )
        .filter(farm_id=farm_id)
        .exclude(id__in=confirmed_ids)
        .order_by("-issue_date")
    )

    # Apply shared filters
    if date_from:
        conf_qs = conf_qs.filter(confirmation_date__gte=date_from)
        pend_qs = pend_qs.filter(issue_date__gte=date_from)
    if date_to:
        conf_qs = conf_qs.filter(confirmation_date__lte=date_to)
        pend_qs = pend_qs.filter(issue_date__lte=date_to)
    if search:
        conf_qs = conf_qs.filter(
            Q(issuance__feed_inventory__feed_name__icontains=search)
            | Q(issuance__animal__tag_id__icontains=search)
            | Q(issuance__group__name__icontains=search)
        )
        pend_qs = pend_qs.filter(
            Q(feed_inventory__feed_name__icontains=search)
            | Q(animal__tag_id__icontains=search)
            | Q(group__name__icontains=search)
        )

    # Build unified row list based on status filter
    rows = []

    if status != "pending":
        for c in conf_qs:
            iss = c.issuance
            if iss.target_type == "group":
                target = iss.group.name if iss.group else None
            else:
                target = iss.animal.tag_id if iss.animal else None

            confirmed_by_name = None
            if c.confirmed_by:
                full = f"{c.confirmed_by.first_name} {c.confirmed_by.last_name}".strip()
                confirmed_by_name = full or c.confirmed_by.email

            row_status = "Variance" if c.status == "variance_detected" else "Confirmed"
            rows.append({
                "id": c.id,
                "issuance_id": iss.id,
                "feed_type": iss.feed_inventory.feed_name,
                "target": target,
                "target_kind": iss.target_type,
                "issued_quantity": iss.quantity_issued,
                "confirmed_used": c.actual_used_quantity,
                "variance": float(c.actual_used_quantity) - float(iss.quantity_issued),
                "status": row_status,
                "confirmed_by": confirmed_by_name,
                "confirmation_date": c.confirmation_date,
            })

    if status != "confirmed" and status != "variance":
        for r in pend_qs:
            if r.target_type == "group":
                target = r.group.name if r.group else None
            else:
                target = r.animal.tag_id if r.animal else None

            issued_by_name = None
            if r.issued_by:
                full = f"{r.issued_by.first_name} {r.issued_by.last_name}".strip()
                issued_by_name = full or r.issued_by.email

            rows.append({
                "id": None,
                "issuance_id": r.id,
                "feed_type": r.feed_inventory.feed_name,
                "target": target,
                "target_kind": r.target_type,
                "issued_quantity": r.quantity_issued,
                "confirmed_used": None,
                "variance": None,
                "status": "Pending",
                "confirmed_by": issued_by_name,
                "confirmation_date": r.issue_date,
            })

    if status == "variance":
        rows = [r for r in rows if r["status"] == "Variance"]

    # paginate in-memory
    total_items = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = rows[start:end]
    num_pages = max(1, (total_items + page_size - 1) // page_size)

    data = {
        "stats": {
            "pending_confirmation": pending_confirmation,
            "confirmed_today": confirmed_today,
            "variance_count_pct": f"{variance_pct}%",
        },
        "records": page_rows,
        "num_pages": num_pages,
        "current_page": page,
        "total_items": total_items,
        "has_next": end < total_items,
        "has_previous": page > 1,
    }
    return 200, APIResponse(success=True, message="Feed confirmation dashboard", data=data)


@router.get("/livestock-report-dashboard/{farm_id}", response={200: APIResponse, 403: APIResponse})
def livestock_report_dashboard(
    request,
    farm_id: int,
    page: int = 1,
    page_size: int = 10,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Reports.LIVESTOCK_DASHBOARD)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from health.models import MortalityRecord
    from reproduction.models import BirthRecord

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())
    week_sunday = week_monday + timedelta(days=6)
    month_start = today.replace(day=1)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_end = month_start

    base_qs = Animal.objects.filter(farm_id=farm_id)

    # ── Top stats ──────────────────────────────────────────────────────────────
    total_animals = base_qs.count()
    active = base_qs.filter(is_active=True).count()
    pregnant = base_qs.filter(is_pregnant=True).count()
    lactating = base_qs.filter(is_lactating=True).count()
    sick = base_qs.filter(health_status="sick").count()

    deaths_this_month = MortalityRecord.objects.filter(
        farm_id=farm_id, death_date__gte=month_start
    ).count()
    mortality_rate = (
        round((deaths_this_month / total_animals) * 100, 1) if total_animals else 0
    )

    # ── Population by species ──────────────────────────────────────────────────
    species_pop = list(
        base_qs.values("species__id", "species__name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    population_by_species = [
        {"species_id": s["species__id"], "species": s["species__name"], "count": s["count"]}
        for s in species_pop
    ]

    # ── Lifecycle distribution Mon–Sun this week ───────────────────────────────
    def get_lifecycle_stage(months):
        if months is None:
            return 0
        if months < 3:
            return 1
        if months < 6:
            return 2
        if months < 12:
            return 3
        if months < 24:
            return 4
        return 5

    lifecycle_week_start = resolve_trend_start(base_qs, "created_at", week_monday, week_sunday)
    lifecycle_by_day = {d: 0 for d in daily_trend_range(lifecycle_week_start, week_sunday)}
    new_animals_qs = base_qs.filter(
        created_at__date__gte=lifecycle_week_start,
        created_at__date__lte=week_sunday,
    ).values("created_at__date").annotate(count=Count("id"))
    for row in new_animals_qs:
        d = row["created_at__date"]
        if d in lifecycle_by_day:
            lifecycle_by_day[d] = row["count"]
    lifecycle_distribution = [
        {"day": d.strftime("%a")[0], "date": d.isoformat(), "count": lifecycle_by_day[d]}
        for d in sorted(lifecycle_by_day)
    ]

    # ── Birth vs Death trend ───────────────────────────────────────────────────
    births_this_month = BirthRecord.objects.filter(
        farm_id=farm_id, birth_date__gte=month_start
    ).aggregate(total=Sum("number_alive"))["total"] or 0

    total_bd = births_this_month + deaths_this_month
    birth_pct = round((births_this_month / total_bd) * 100, 1) if total_bd else 0
    death_pct = round((deaths_this_month / total_bd) * 100, 1) if total_bd else 0

    birth_vs_death = {
        "births": births_this_month,
        "deaths": deaths_this_month,
        "birth_pct": birth_pct,
        "death_pct": death_pct,
    }

    # ── Species breakdown table with growth rate (paginated) ───────────────────
    all_species = (
        base_qs.values("species__id", "species__name")
        .annotate(
            count=Count("id"),
            male=Count("id", filter=Q(gender="male")),
            female=Count("id", filter=Q(gender="female")),
        )
        .order_by("species__name")
    )

    last_month_counts = {
        row["species__id"]: row["count"]
        for row in Animal.objects.filter(
            farm_id=farm_id,
            created_at__date__lt=last_month_end,
        )
        .values("species__id")
        .annotate(count=Count("id"))
    }

    rows = []
    for s in all_species:
        sid = s["species__id"]
        current = s["count"]
        previous = last_month_counts.get(sid, 0)
        if previous:
            growth = round(((current - previous) / previous) * 100, 1)
        else:
            growth = None
        rows.append({
            "species_id": sid,
            "species": s["species__name"],
            "count": current,
            "male": s["male"],
            "female": s["female"],
            "growth_rate": growth,
        })

    total_items = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start: start + page_size]
    num_pages = max(1, (total_items + page_size - 1) // page_size)

    data = {
        "stats": {
            "total_animals": total_animals,
            "active": active,
            "pregnant": pregnant,
            "lactating": lactating,
            "sick": sick,
            "mortality_rate": f"{mortality_rate}%",
        },
        "population_by_species": population_by_species,
        "lifecycle_distribution": lifecycle_distribution,
        "birth_vs_death": birth_vs_death,
        "species_breakdown": page_rows,
        "num_pages": num_pages,
        "current_page": page,
        "total_items": total_items,
        "has_next": (start + page_size) < total_items,
        "has_previous": page > 1,
    }
    return 200, APIResponse(success=True, message="Livestock report dashboard", data=data)


@router.get("/production-report/{farm_id}", response={200: APIResponse, 403: APIResponse})
def production_report(
    request,
    farm_id: int,
    page: int = 1,
    page_size: int = 10,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Production.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from animals.models import MilkRecord, DailyMilkSummary

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())
    week_sunday = week_monday + timedelta(days=6)
    month_start = today.replace(day=1)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_end = month_start

    # ── Top stats ──────────────────────────────────────────────────────────────
    total_milk = (
        DailyMilkSummary.objects.filter(farm_id=farm_id, date=today)
        .aggregate(total=Sum("total_litres"))["total"] or 0
    )

    lactating_count = Animal.objects.filter(farm_id=farm_id, is_lactating=True).count()

    # avg yield: avg litres per lactating animal today vs farm's daily max per animal
    if lactating_count:
        avg_per_animal = float(total_milk) / lactating_count
        all_time_max = (
            MilkRecord.objects.filter(farm_id=farm_id)
            .values("animal_id", "record_date")
            .annotate(daily=Sum("quantity"))
            .aggregate(max_daily=Sum("daily"))
        )
        farm_max = float(
            MilkRecord.objects.filter(farm_id=farm_id, record_date=today)
            .values("animal_id").annotate(daily=Sum("quantity"))
            .aggregate(mx=Sum("daily"))["mx"] or 1
        )
        max_per_animal = farm_max / lactating_count if lactating_count else 1
        avg_yield_pct = round((avg_per_animal / max_per_animal) * 100, 1) if max_per_animal else 0
    else:
        avg_yield_pct = 0

    production_trend_count = DailyMilkSummary.objects.filter(
        farm_id=farm_id,
        date__gte=month_start,
        total_litres__gt=0,
    ).count()

    # ── Milk trend Mon–Sun this week ───────────────────────────────────────────
    milk_base_qs = DailyMilkSummary.objects.filter(farm_id=farm_id)
    milk_week_start = resolve_trend_start(milk_base_qs, "date", week_monday, week_sunday)
    milk_by_day = {d: 0.0 for d in daily_trend_range(milk_week_start, week_sunday)}
    milk_trend_qs = milk_base_qs.filter(
        date__gte=milk_week_start,
        date__lte=week_sunday,
    ).values("date", "total_litres")
    for row in milk_trend_qs:
        if row["date"] in milk_by_day:
            milk_by_day[row["date"]] = float(row["total_litres"])
    milk_trend = [
        {"day": d.strftime("%a")[0], "date": d.isoformat(), "total_litres": milk_by_day[d]}
        for d in sorted(milk_by_day)
    ]

    # ── Monthly totals helper (Jan → current month) ────────────────────────────
    def monthly_milk_series(farm_id, year):
        months = []
        for m in range(1, today.month + 1):
            ms = today.replace(month=m, day=1)
            me = today.replace(month=m + 1, day=1) if m < 12 else today.replace(year=year + 1, month=1, day=1)
            total = (
                DailyMilkSummary.objects.filter(
                    farm_id=farm_id, date__gte=ms, date__lt=me
                ).aggregate(t=Sum("total_litres"))["t"] or 0
            )
            months.append({"month": ms.strftime("%b"), "year_month": ms.strftime("%Y-%m"), "total_litres": float(total)})
        return months

    monthly_series = monthly_milk_series(farm_id, today.year)
    values = [m["total_litres"] for m in monthly_series]
    max_val = max(values) if values else 1
    avg_val = (sum(values) / len(values)) if values else 0

    top_producers_chart = [
        {**m, "is_top": m["total_litres"] >= avg_val}
        for m in monthly_series
    ]
    low_producers_chart = [
        {**m, "is_low": m["total_litres"] < avg_val and m["total_litres"] > 0}
        for m in monthly_series
    ]

    # ── Per-species table ──────────────────────────────────────────────────────
    species_this_month = (
        MilkRecord.objects.filter(farm_id=farm_id, record_date__gte=month_start)
        .values("animal__species__id", "animal__species__name")
        .annotate(total=Sum("quantity"), records=Count("id"))
    )
    species_last_month = {
        row["animal__species__id"]: float(row["total"] or 0)
        for row in MilkRecord.objects.filter(
            farm_id=farm_id,
            record_date__gte=last_month_start,
            record_date__lt=last_month_end,
        )
        .values("animal__species__id")
        .annotate(total=Sum("quantity"))
    }

    all_rows = []
    for s in species_this_month:
        sid = s["animal__species__id"]
        current_total = float(s["total"] or 0)
        prev_total = species_last_month.get(sid, 0)
        lact_count = Animal.objects.filter(
            farm_id=farm_id, species_id=sid, is_lactating=True
        ).count()
        records = s["records"] or 1
        avg_yield = round((current_total / records), 2) if records else 0
        avg_yield_species_pct = round((avg_yield / (max_val / (len(monthly_series) or 1))) * 100, 1) if max_val else 0

        if prev_total:
            growth = round(((current_total - prev_total) / prev_total) * 100, 1)
        else:
            growth = None

        all_rows.append({
            "species_id": sid,
            "species": s["animal__species__name"],
            "lactating_count": lact_count,
            "avg_yield_pct": avg_yield_species_pct,
            "total_production": current_total,
            "growth_rate": growth,
        })

    total_items = len(all_rows)
    start = (page - 1) * page_size
    page_rows = all_rows[start: start + page_size]
    num_pages = max(1, (total_items + page_size - 1) // page_size)

    data = {
        "stats": {
            "total_milk_today": float(total_milk),
            "avg_yield_pct": f"{avg_yield_pct}%",
            "lactating_animals": lactating_count,
            "production_trend_days": production_trend_count,
        },
        "milk_trend": milk_trend,
        "top_producers_chart": top_producers_chart,
        "low_producers_chart": low_producers_chart,
        "species_breakdown": page_rows,
        "num_pages": num_pages,
        "current_page": page,
        "total_items": total_items,
        "has_next": (start + page_size) < total_items,
        "has_previous": page > 1,
    }
    return 200, APIResponse(success=True, message="Production report", data=data)


@router.get("/health-report/{farm_id}", response={200: APIResponse, 403: APIResponse})
def health_report(
    request,
    farm_id: int,
    page: int = 1,
    page_size: int = 10,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Health.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from health.models import TreatmentRecord, VaccinationRecord, MortalityRecord

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())
    week_sunday = week_monday + timedelta(days=6)
    seven_days_ago = today - timedelta(days=6)
    month_start = today.replace(day=1)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_end = month_start

    # ── Top stats ──────────────────────────────────────────────────────────────
    sick_animals = Animal.objects.filter(farm_id=farm_id, health_status="sick").count()

    treatments = TreatmentRecord.objects.filter(farm_id=farm_id).count()

    total_animals = Animal.objects.filter(farm_id=farm_id).count()
    vaccinated_animals = (
        VaccinationRecord.objects.filter(farm_id=farm_id, animal__isnull=False)
        .values("animal_id")
        .distinct()
        .count()
    )
    vaccination_coverage_pct = (
        round((vaccinated_animals / total_animals) * 100, 1) if total_animals else 0
    )

    mortality = MortalityRecord.objects.filter(farm_id=farm_id).count()

    # ── Disease trend Mon–Sun this week ────────────────────────────────────────
    disease_base_qs = TreatmentRecord.objects.filter(farm_id=farm_id)
    disease_week_start = resolve_trend_start(disease_base_qs, "treatment_date", week_monday, week_sunday)
    disease_by_day = {d: 0 for d in daily_trend_range(disease_week_start, week_sunday)}
    disease_qs = (
        disease_base_qs.filter(
            treatment_date__gte=disease_week_start,
            treatment_date__lte=week_sunday,
        )
        .values("treatment_date")
        .annotate(count=Count("id"))
    )
    for row in disease_qs:
        if row["treatment_date"] in disease_by_day:
            disease_by_day[row["treatment_date"]] = row["count"]
    disease_trend = [
        {"day": d.strftime("%a")[0], "date": d.isoformat(), "count": disease_by_day[d]}
        for d in sorted(disease_by_day)
    ]

    # ── Treatment success rate (last 7 days) ───────────────────────────────────
    recent_qs = TreatmentRecord.objects.filter(
        farm_id=farm_id, treatment_date__gte=seven_days_ago
    )
    total_recorded = recent_qs.count()
    recovered = recent_qs.filter(animal__health_status="recovering").count()
    ongoing = recent_qs.filter(next_follow_up_date__gte=today).count()
    severe = recent_qs.filter(severity="severe").count()

    treatment_success_rate = {
        "total_recorded": total_recorded,
        "recovered": recovered,
        "ongoing_treatment": ongoing,
        "severe": severe,
        "recovered_pct": round((recovered / total_recorded) * 100, 1) if total_recorded else 0,
        "ongoing_pct": round((ongoing / total_recorded) * 100, 1) if total_recorded else 0,
        "severe_pct": round((severe / total_recorded) * 100, 1) if total_recorded else 0,
    }

    # ── Disease breakdown table: group by diagnosis ────────────────────────────
    this_month_cases = (
        TreatmentRecord.objects.filter(farm_id=farm_id, treatment_date__gte=month_start)
        .values("diagnosis")
        .annotate(cases=Count("id"))
        .order_by("-cases")
    )
    last_month_cases = {
        row["diagnosis"]: row["cases"]
        for row in TreatmentRecord.objects.filter(
            farm_id=farm_id,
            treatment_date__gte=last_month_start,
            treatment_date__lt=last_month_end,
        )
        .values("diagnosis")
        .annotate(cases=Count("id"))
    }

    all_rows = []
    for row in this_month_cases:
        diagnosis = row["diagnosis"]
        current_cases = row["cases"]
        prev_cases = last_month_cases.get(diagnosis, 0)

        # Recovery rate: cases where the linked animal is now recovering/healthy
        recovered_cases = TreatmentRecord.objects.filter(
            farm_id=farm_id,
            treatment_date__gte=month_start,
            diagnosis=diagnosis,
            animal__health_status__in=["recovering", "healthy"],
        ).count()
        recovery_rate = (
            round((recovered_cases / current_cases) * 100, 1) if current_cases else 0
        )

        if prev_cases:
            growth = round(((current_cases - prev_cases) / prev_cases) * 100, 1)
        else:
            growth = None

        all_rows.append({
            "diagnosis": diagnosis,
            "cases": current_cases,
            "recovered_cases": recovered_cases,
            "recovery_rate_pct": recovery_rate,
            "growth_rate": growth,
        })

    total_items = len(all_rows)
    start = (page - 1) * page_size
    page_rows = all_rows[start: start + page_size]
    num_pages = max(1, (total_items + page_size - 1) // page_size)

    data = {
        "stats": {
            "sick_animals": sick_animals,
            "treatments": treatments,
            "vaccination_coverage": f"{vaccination_coverage_pct}%",
            "mortality": mortality,
        },
        "disease_trend": disease_trend,
        "treatment_success_rate": treatment_success_rate,
        "disease_breakdown": page_rows,
        "num_pages": num_pages,
        "current_page": page,
        "total_items": total_items,
        "has_next": (start + page_size) < total_items,
        "has_previous": page > 1,
    }
    return 200, APIResponse(success=True, message="Health report", data=data)


@router.get("/feed-report/{farm_id}", response={200: APIResponse, 403: APIResponse})
def feed_report(
    request,
    farm_id: int,
    page: int = 1,
    page_size: int = 10,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Feed.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from feed.models import FeedInventory, FeedIssuanceRecord, FeedConfirmationRecord

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())
    week_sunday = week_monday + timedelta(days=6)
    month_start = today.replace(day=1)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_end = month_start

    # ── Top stats ──────────────────────────────────────────────────────────────
    total_feed_used = (
        FeedConfirmationRecord.objects.filter(farm__id=farm_id, confirmation_date__gte=month_start)
        .aggregate(total=Sum("actual_used_quantity"))["total"] or 0
    )

    confirmed_records = FeedConfirmationRecord.objects.filter(
        farm__id=farm_id, confirmation_date__gte=month_start
    ).count()
    avg_consumption = (
        round(float(total_feed_used) / confirmed_records, 2) if confirmed_records else 0
    )

    total_issued_month = (
        FeedIssuanceRecord.objects.filter(farm_id=farm_id, issue_date__gte=month_start)
        .aggregate(total=Sum("quantity_issued"))["total"] or 0
    )
    total_variance = (
        FeedConfirmationRecord.objects.filter(farm__id=farm_id, confirmation_date__gte=month_start)
        .aggregate(total=Sum("variance_quantity"))["total"] or 0
    )
    variance_rate_pct = (
        round((float(total_variance) / float(total_issued_month)) * 100, 1)
        if total_issued_month else 0
    )

    low_stock = FeedInventory.objects.filter(farm_id=farm_id, status="low_stock").count()

    # ── Feed consumption trend Mon–Sun this week ───────────────────────────────
    confirmation_base_qs = FeedConfirmationRecord.objects.filter(farm__id=farm_id)
    consumption_week_start = resolve_trend_start(
        confirmation_base_qs, "confirmation_date", week_monday, week_sunday
    )
    consumption_by_day = {d: 0.0 for d in daily_trend_range(consumption_week_start, week_sunday)}
    consumption_qs = (
        confirmation_base_qs.filter(
            confirmation_date__gte=consumption_week_start,
            confirmation_date__lte=week_sunday,
        )
        .values("confirmation_date")
        .annotate(total=Sum("actual_used_quantity"))
    )
    for row in consumption_qs:
        if row["confirmation_date"] in consumption_by_day:
            consumption_by_day[row["confirmation_date"]] = float(row["total"])
    consumption_trend = [
        {"day": d.strftime("%a")[0], "date": d.isoformat(), "total_used": consumption_by_day[d]}
        for d in sorted(consumption_by_day)
    ]

    # ── Issued vs Used Feed Mon–Sun this week ──────────────────────────────────
    # issued_by_day/used_by_day share one window (based on issuance data) since
    # issued_vs_used below indexes both dicts by the same day
    issuance_base_qs = FeedIssuanceRecord.objects.filter(farm_id=farm_id)
    feed_week_start = resolve_trend_start(issuance_base_qs, "issue_date", week_monday, week_sunday)
    issued_by_day = {d: 0.0 for d in daily_trend_range(feed_week_start, week_sunday)}
    used_by_day = {d: 0.0 for d in daily_trend_range(feed_week_start, week_sunday)}

    issued_qs = (
        issuance_base_qs.filter(
            issue_date__gte=feed_week_start,
            issue_date__lte=week_sunday,
        )
        .values("issue_date")
        .annotate(total=Sum("quantity_issued"))
    )
    for row in issued_qs:
        if row["issue_date"] in issued_by_day:
            issued_by_day[row["issue_date"]] = float(row["total"])

    used_qs = (
        confirmation_base_qs.filter(
            confirmation_date__gte=feed_week_start,
            confirmation_date__lte=week_sunday,
        )
        .values("confirmation_date")
        .annotate(total=Sum("actual_used_quantity"))
    )
    for row in used_qs:
        if row["confirmation_date"] in used_by_day:
            used_by_day[row["confirmation_date"]] = float(row["total"])

    issued_vs_used = [
        {
            "day": d.strftime("%a")[0],
            "date": d.isoformat(),
            "issued": issued_by_day[d],
            "used": used_by_day[d],
            "usage_pct": (
                round((used_by_day[d] / issued_by_day[d]) * 100, 1)
                if issued_by_day[d] else 0
            ),
        }
        for d in sorted(issued_by_day)
    ]

    # ── Per feed type table (issued, used, variance, growth) ───────────────────
    this_month_by_feed = (
        FeedIssuanceRecord.objects.filter(farm_id=farm_id, issue_date__gte=month_start)
        .values("feed_inventory__id", "feed_inventory__feed_name", "feed_inventory__unit")
        .annotate(issued=Sum("quantity_issued"))
    )
    last_month_issued = {
        row["feed_inventory__id"]: float(row["issued"] or 0)
        for row in FeedIssuanceRecord.objects.filter(
            farm_id=farm_id,
            issue_date__gte=last_month_start,
            issue_date__lt=last_month_end,
        )
        .values("feed_inventory__id")
        .annotate(issued=Sum("quantity_issued"))
    }
    confirmed_by_feed = {
        row["issuance__feed_inventory__id"]: float(row["used"] or 0)
        for row in FeedConfirmationRecord.objects.filter(
            farm__id=farm_id, confirmation_date__gte=month_start
        )
        .values("issuance__feed_inventory__id")
        .annotate(used=Sum("actual_used_quantity"))
    }

    all_rows = []
    for row in this_month_by_feed:
        fid = row["feed_inventory__id"]
        issued = float(row["issued"] or 0)
        used = confirmed_by_feed.get(fid, 0)
        variance = round(issued - used, 2)
        prev_issued = last_month_issued.get(fid, 0)
        growth = (
            round(((issued - prev_issued) / prev_issued) * 100, 1) if prev_issued else None
        )
        all_rows.append({
            "feed_id": fid,
            "feed_type": row["feed_inventory__feed_name"],
            "unit": row["feed_inventory__unit"],
            "issued": issued,
            "used": used,
            "variance": variance,
            "growth_rate": growth,
        })

    total_items = len(all_rows)
    start = (page - 1) * page_size
    page_rows = all_rows[start: start + page_size]
    num_pages = max(1, (total_items + page_size - 1) // page_size)

    data = {
        "stats": {
            "total_feed_used": float(total_feed_used),
            "avg_consumption": avg_consumption,
            "variance_rate": f"{variance_rate_pct}%",
            "low_stock": low_stock,
        },
        "consumption_trend": consumption_trend,
        "issued_vs_used": issued_vs_used,
        "feed_breakdown": page_rows,
        "num_pages": num_pages,
        "current_page": page,
        "total_items": total_items,
        "has_next": (start + page_size) < total_items,
        "has_previous": page > 1,
    }
    return 200, APIResponse(success=True, message="Feed report", data=data)


# ══════════════════════════════════════════════════════════════════════════════
# V2 ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════


@router.get("/main-dashboard/v2/{farm_id}", response={200: APIResponse, 403: APIResponse})
def main_dashboard_v2(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Reports.LIVESTOCK_DASHBOARD)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
            
    from animals.models import AnimalDashboard, DailyMilkSummary, AnimalWeight
    from animals.signals import recalc_dashboard_for_farm
    from health.models import VaccinationRecord, TreatmentRecord

    dashboard = AnimalDashboard.objects.filter(farm_id=farm_id).first()
    if not dashboard:
        recalc_dashboard_for_farm(farm_id)
        dashboard = AnimalDashboard.objects.get(farm_id=farm_id)

    upcoming_records = VaccinationRecord.objects.select_related("animal", "group").filter(
        farm_id=farm_id,
        next_due_date__isnull=False,
        next_due_date__gte=timezone.localdate(),
    ).order_by("next_due_date")[:5]

    vaccination_upcoming_records = [
        {
            "id": record.id,
            "animal_id": record.animal.id if record.animal else None,
            "animal_tag": record.animal.tag_id if record.animal else None,
            "group_id": record.group.id if record.group else None,
            "group_name": record.group.name if record.group else None,
            "vaccine_name": record.vaccine_name,
            "date_given": record.date_given,
            "next_due_date": record.next_due_date,
            "notes": record.notes,
        }
        for record in upcoming_records
    ]

    treatment_followups_qs = TreatmentRecord.objects.select_related("animal", "group").filter(
        farm_id=farm_id,
        next_follow_up_date__isnull=False,
    ).order_by("-next_follow_up_date")[:3]

    treatment_followups = [
        {
            "id": record.id,
            "animal_id": record.animal.id if record.animal else None,
            "animal_tag": record.animal.tag_id if record.animal else None,
            "group_id": record.group.id if record.group else None,
            "group_name": record.group.name if record.group else None,
            "diagnosis": record.diagnosis,
            "treatment": record.treatment,
            "severity": record.severity,
            "treatment_date": record.treatment_date,
            "next_follow_up_date": record.next_follow_up_date,
            "notes": record.notes,
        }
        for record in treatment_followups_qs
    ]

    # Species distribution — v2: group by livestock_species
    from django.db.models import Count
    species_dist = Animal.objects.filter(
        farm_id=farm_id
    ).values("livestock_species__id", "livestock_species__name").annotate(count=Count("id")).order_by("-count")

    species_distribution = [
        {
            "species_id": item["livestock_species__id"],
            "species_name": item["livestock_species__name"],
            "count": item["count"],
        }
        for item in species_dist
    ]

    today = timezone.localdate()
    milk_summary = DailyMilkSummary.objects.filter(farm_id=farm_id, date=today).first()
    milk_today = milk_summary.total_litres if milk_summary else 0

    nominal_seven_days_ago = today - timedelta(days=6)
    seven_days_ago = resolve_trend_start(
        DailyMilkSummary.objects.filter(farm_id=farm_id), "date", nominal_seven_days_ago, today
    )
    summaries = {
        s.date: s.total_litres
        for s in DailyMilkSummary.objects.filter(
            farm_id=farm_id,
            date__gte=seven_days_ago,
            date__lte=today,
        )
    }
    production_trend = [
        {
            "date": d.isoformat(),
            "total_litres": float(summaries.get(d, 0)),
        }
        for d in daily_trend_range(seven_days_ago, today)
    ]

    from feed.models import FeedInventory, FeedIssuanceRecord, FeedConfirmationRecord

    feed_qs = FeedInventory.objects.filter(farm_id=farm_id)
    total_stock = feed_qs.aggregate(total=Sum("quantity_available"))["total"] or 0
    low_stock_items = list(
        feed_qs.filter(status="low_stock").values("id", "feed_name", "quantity_available", "unit", "reorder_level")
    )

    total_issued = (
        FeedIssuanceRecord.objects.filter(farm_id=farm_id)
        .aggregate(total=Sum("quantity_issued"))["total"] or 0
    )
    total_used = (
        FeedConfirmationRecord.objects.filter(farm__id=farm_id)
        .aggregate(total=Sum("actual_used_quantity"))["total"] or 0
    )
    variance_alerts = list(
        FeedConfirmationRecord.objects.select_related("issuance__feed_inventory")
        .filter(farm__id=farm_id, status="variance_detected")
        .order_by("-confirmation_date")[:5]
        .values(
            "id",
            "issuance__feed_inventory__feed_name",
            "issuance__quantity_issued",
            "actual_used_quantity",
            "variance_quantity",
            "confirmation_date",
        )
    )

    recent_weights_qs = AnimalWeight.objects.select_related("animal").filter(
        farm_id=farm_id
    ).order_by("-date", "-created_at")[:5]
    recent_weights = [
        {
            "id": w.id,
            "animal_id": w.animal.id,
            "animal_tag": w.animal.tag_id,
            "date": w.date,
            "weight": w.weight,
        }
        for w in recent_weights_qs
    ]

    data = {
        "milk_today": milk_today,
        "production_trend": production_trend,
        "recent_weights": recent_weights,
        "feed": {
            "total_stock": total_stock,
            "low_stock_items": low_stock_items,
            "total_issued": total_issued,
            "total_used": total_used,
            "variance_alerts": variance_alerts,
        },
        "total": dashboard.total_animals,
        "active": dashboard.active,
        "healthy": dashboard.healthy,
        "lactating": dashboard.lactating,
        "pregnant": dashboard.pregnant,
        "sick": dashboard.sick,
        "quarantine": dashboard.quarantine,
        "deaths": dashboard.deaths,
        "sales": dashboard.sales,
        "species_distribution": species_distribution,
        "treatment_followups": treatment_followups,
        "vaccination_upcoming_records": vaccination_upcoming_records,
        "updated_at": dashboard.updated_at,
    }
    return 200, APIResponse(success=True, message="Animal dashboard", data=data)


@router.get("/livestock-dashboard/v2/{farm_id}", response={200: APIResponse, 403: APIResponse})
def livestock_dashboard_v2(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Reports.LIVESTOCK_DASHBOARD)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from health.models import MortalityRecord

    base_qs = Animal.objects.filter(farm_id=farm_id)

    # ── Summary stats ──────────────────────────────────────────────────────────
    summary = base_qs.aggregate(
        total=Count("id"),
        male=Count("id", filter=Q(gender="male")),
        female=Count("id", filter=Q(gender="female")),
        pregnant=Count("id", filter=Q(is_pregnant=True)),
        lactating=Count("id", filter=Q(is_lactating=True)),
        sick=Count("id", filter=Q(health_status="sick")),
        active=Count("id", filter=Q(is_active=True)),
    )

    # ── Recent added animals (last 5) — v2: livestock_species fallback ─────────
    recent_qs = (
        base_qs.select_related("livestock_species", "species")
        .order_by("-created_at")[:5]
    )
    recent_animals = [
        {
            "id": a.id,
            "tag_id": a.tag_id,
            "gender": a.gender,
            "species": a.livestock_species.name if a.livestock_species else (a.species.name if a.species else None),
            "created_at": a.created_at,
        }
        for a in recent_qs
    ]

    # ── 4 Health risks — v2: livestock_species fallback ────────────────────────
    health_risk_qs = (
        base_qs.select_related("livestock_species", "species")
        .filter(health_status__in=["sick", "at_risk"])
        .order_by("-updated_at")[:4]
    )
    health_risks = [
        {
            "id": a.id,
            "tag_id": a.tag_id,
            "species": a.livestock_species.name if a.livestock_species else (a.species.name if a.species else None),
            "health_status": a.health_status,
            "is_quarantine": a.is_quarantine,
        }
        for a in health_risk_qs
    ]

    # ── Ready for sale (4) — v2: livestock_species/breed fallback ─────────────
    ready_for_sale_qs = (
        base_qs.select_related("livestock_species", "species", "livestock_breed", "breed")
        .filter(
            status="active",
            is_active=True,
            health_status="healthy",
            is_pregnant=False,
            is_lactating=False,
        )
        .order_by("-created_at")[:4]
    )
    ready_for_sale = [
        {
            "id": a.id,
            "tag_id": a.tag_id,
            "species": a.livestock_species.name if a.livestock_species else (a.species.name if a.species else None),
            "breed": a.livestock_breed.name if a.livestock_breed else (a.breed.name if a.breed else None),
            "gender": a.gender,
            "dob": a.dob,
        }
        for a in ready_for_sale_qs
    ]

    # ── Livestock population trend (last 12 months) ────────────────────────────
    today = timezone.localdate()
    nominal_month_start = today.replace(day=1) - relativedelta(months=11)
    current_month_start = today.replace(day=1)
    population_window_start = resolve_trend_start(base_qs, "created_at", nominal_month_start, current_month_start)
    population_trend = []
    for month_start in monthly_trend_range(population_window_start, current_month_start):
        month_end = month_start + relativedelta(months=1)
        count = base_qs.filter(created_at__date__gte=month_start, created_at__date__lt=month_end).count()
        population_trend.append({
            "month": month_start.strftime("%Y-%m"),
            "count": count,
        })

    # ── Birth trend Mon–Sun this week ──────────────────────────────────────────
    week_monday = today - timedelta(days=today.weekday())
    week_sunday = week_monday + timedelta(days=6)
    births_base_qs = base_qs.filter(source_type="born")
    birth_week_start = resolve_trend_start(births_base_qs, "dob", week_monday, week_sunday)
    birth_by_day = {d: 0 for d in daily_trend_range(birth_week_start, week_sunday)}
    births_qs = births_base_qs.filter(
        dob__gte=birth_week_start,
        dob__lte=week_sunday,
    ).values("dob").annotate(count=Count("id"))
    for row in births_qs:
        if row["dob"] in birth_by_day:
            birth_by_day[row["dob"]] = row["count"]
    birth_trend = [
        {"day": d.strftime("%A"), "date": d.isoformat(), "count": birth_by_day[d]}
        for d in sorted(birth_by_day)
    ]

    # ── Mortality trend Mon–Sun this week ──────────────────────────────────────
    mortality_base_qs = MortalityRecord.objects.filter(farm_id=farm_id)
    mortality_week_start = resolve_trend_start(mortality_base_qs, "death_date", week_monday, week_sunday)
    mortality_by_day = {d: 0 for d in daily_trend_range(mortality_week_start, week_sunday)}
    mortality_qs = mortality_base_qs.filter(
        death_date__gte=mortality_week_start,
        death_date__lte=week_sunday,
    ).values("death_date").annotate(count=Count("id"))
    for row in mortality_qs:
        if row["death_date"] in mortality_by_day:
            mortality_by_day[row["death_date"]] = row["count"]
    mortality_trend = [
        {"day": d.strftime("%A"), "date": d.isoformat(), "count": mortality_by_day[d]}
        for d in sorted(mortality_by_day)
    ]

    # ── Exceptions (quarantine + at_risk) — v2: livestock_species fallback ─────
    exceptions_qs = (
        base_qs.select_related("livestock_species", "species")
        .filter(Q(is_quarantine=True) | Q(health_status="at_risk"))
        .order_by("-updated_at")
    )
    exceptions = [
        {
            "id": a.id,
            "tag_id": a.tag_id,
            "species": a.livestock_species.name if a.livestock_species else (a.species.name if a.species else None),
            "health_status": a.health_status,
            "is_quarantine": a.is_quarantine,
            "status": a.status,
        }
        for a in exceptions_qs
    ]

    data = {
        "summary": summary,
        "recent_animals": recent_animals,
        "health_risks": health_risks,
        "ready_for_sale": ready_for_sale,
        "population_trend": population_trend,
        "birth_trend": birth_trend,
        "mortality_trend": mortality_trend,
        "exceptions": exceptions,
    }
    return 200, APIResponse(success=True, message="Livestock dashboard", data=data)


@router.get("/animal-dashboard/v2/{farm_id}", response={200: APIResponse, 403: APIResponse})
def animal_dashboard_v2(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Animal.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    base_qs = Animal.objects.filter(farm_id=farm_id)

    stats = base_qs.aggregate(
        total_animals=Count("id"),
        pregnant=Count("id", filter=Q(is_pregnant=True)),
        sick=Count("id", filter=Q(health_status="sick")),
        quarantine=Count("id", filter=Q(is_quarantine=True)),
    )

    today = timezone.localdate()

    def calc_age(animal):
        if animal.dob:
            delta = today - animal.dob
            months = delta.days // 30
            if months < 12:
                return f"{months}m"
            return f"{months // 12}y {months % 12}m"
        if animal.estimated_age_months:
            m = animal.estimated_age_months
            if m < 12:
                return f"{m}m"
            return f"{m // 12}y {m % 12}m"
        return None

    # v2: add livestock_species/breed fallback
    recent_qs = (
        base_qs.select_related("livestock_species", "species", "livestock_breed", "breed")
        .order_by("-created_at")[:10]
    )
    recent_animals = [
        {
            "animal_id": a.id,
            "tag_id": a.tag_id,
            "species": a.livestock_species.name if a.livestock_species else (a.species.name if a.species else None),
            "breed": a.livestock_breed.name if a.livestock_breed else (a.breed.name if a.breed else None),
            "gender": a.gender,
            "age": calc_age(a),
            "status": a.status,
        }
        for a in recent_qs
    ]

    data = {
        "total_animals": stats["total_animals"],
        "pregnant": stats["pregnant"],
        "sick": stats["sick"],
        "quarantine": stats["quarantine"],
        "recent_animals": recent_animals,
    }
    return 200, APIResponse(success=True, message="Animal dashboard", data=data)


@router.get("/reproduction-dashboard/v2/{farm_id}", response={200: APIResponse, 403: APIResponse})
def reproduction_dashboard_v2(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Reproduction.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from reproduction.models import InseminationRecord, PregnancyRecord, BirthRecord

    today = timezone.localdate()
    thirty_days_ago = today - timedelta(days=30)

    # ── Top stats ──────────────────────────────────────────────────────────────
    total_female = Animal.objects.filter(farm_id=farm_id, gender="female").count()

    inseminated_recent = InseminationRecord.objects.filter(
        farm_id=farm_id,
        service_date__gte=thirty_days_ago,
    ).count()

    pregnant_count = Animal.objects.filter(farm_id=farm_id, is_pregnant=True).count()

    due_for_delivery = PregnancyRecord.objects.filter(
        farm_id=farm_id,
        result="pregnant",
        expected_delivery_date__gte=today,
        expected_delivery_date__lte=today + timedelta(days=30),
    ).count()

    failed_insemination = PregnancyRecord.objects.filter(
        farm_id=farm_id,
        result="not_pregnant",
    ).count()

    # ── Pregnancy due soon (5) ─────────────────────────────────────────────────
    due_soon_qs = (
        PregnancyRecord.objects.select_related("animal")
        .filter(farm_id=farm_id, result="pregnant", expected_delivery_date__gte=today)
        .order_by("expected_delivery_date")[:5]
    )
    pregnancy_due_soon = [
        {
            "animal_id": r.animal.id,
            "tag_id": r.animal.tag_id,
            "expected_delivery_date": r.expected_delivery_date,
            "status": "Pregnant",
        }
        for r in due_soon_qs
    ]

    # ── Pregnancy trend (monthly, current year) ────────────────────────────────
    pregnancy_trend = []
    for month in range(1, today.month + 1):
        month_start = today.replace(month=month, day=1)
        month_end = today.replace(month=month + 1, day=1) if month < 12 else today.replace(year=today.year + 1, month=1, day=1)
        count = PregnancyRecord.objects.filter(
            farm_id=farm_id,
            result="pregnant",
            check_date__gte=month_start,
            check_date__lt=month_end,
        ).count()
        pregnancy_trend.append({
            "month": month_start.strftime("%b"),
            "year_month": month_start.strftime("%Y-%m"),
            "count": count,
        })

    # ── Birth trend (monthly, full year Jan–Dec) ───────────────────────────────
    birth_trend = []
    for month in range(1, 13):
        month_start = today.replace(month=month, day=1)
        month_end = today.replace(month=month + 1, day=1) if month < 12 else today.replace(year=today.year + 1, month=1, day=1)
        total = BirthRecord.objects.filter(
            farm_id=farm_id,
            birth_date__gte=month_start,
            birth_date__lt=month_end,
        ).aggregate(total=Sum("number_alive"))["total"] or 0
        birth_trend.append({
            "month": month_start.strftime("%b"),
            "year_month": month_start.strftime("%Y-%m"),
            "count": total,
        })

    # ── Failed cases — v2: livestock_species fallback ─────────────────────────
    failed_qs = (
        PregnancyRecord.objects.select_related(
            "animal", "animal__livestock_species", "animal__species", "insemination"
        )
        .filter(farm_id=farm_id, result="not_pregnant")
        .order_by("-check_date")[:5]
    )
    failed_cases = [
        {
            "animal_id": r.animal.id,
            "tag_id": r.animal.tag_id,
            "species": (
                r.animal.livestock_species.name if r.animal.livestock_species
                else (r.animal.species.name if r.animal.species else None)
            ),
            "service_date": r.insemination.service_date if r.insemination else None,
            "check_date": r.check_date,
            "status": "Failed",
        }
        for r in failed_qs
    ]

    # ── Recently inseminated ───────────────────────────────────────────────────
    recent_insem_qs = (
        InseminationRecord.objects.select_related("animal")
        .prefetch_related("pregnancy_records")
        .filter(farm_id=farm_id)
        .order_by("-service_date")[:10]
    )
    recently_inseminated = []
    for rec in recent_insem_qs:
        pregnancy = rec.pregnancy_records.order_by("-check_date").first()
        if pregnancy is None:
            status = "Pending"
        elif pregnancy.result == "pregnant":
            status = "Success"
        else:
            status = "Failed"
        recently_inseminated.append({
            "animal_id": rec.animal.id,
            "tag_id": rec.animal.tag_id,
            "service_date": rec.service_date,
            "method": rec.method,
            "status": status,
        })

    data = {
        "stats": {
            "total_female": total_female,
            "inseminated_recent": inseminated_recent,
            "pregnant": pregnant_count,
            "due_for_delivery": due_for_delivery,
            "failed_insemination": failed_insemination,
        },
        "pregnancy_due_soon": pregnancy_due_soon,
        "pregnancy_trend": pregnancy_trend,
        "birth_trend": birth_trend,
        "failed_cases": failed_cases,
        "recently_inseminated": recently_inseminated,
    }
    return 200, APIResponse(success=True, message="Reproduction dashboard", data=data)


@router.get("/health-dashboard/v2/{farm_id}", response={200: APIResponse, 403: APIResponse})
def health_dashboard_v2(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Health.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from health.models import TreatmentRecord, VaccinationRecord, QuarantineRecord

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())
    week_sunday = week_monday + timedelta(days=6)

    # ── Top stats ──────────────────────────────────────────────────────────────
    sick_animals = Animal.objects.filter(farm_id=farm_id, health_status="sick").count()

    under_treatment = TreatmentRecord.objects.filter(
        farm_id=farm_id,
        next_follow_up_date__gte=today,
        animal__isnull=False,
    ).values("animal_id").distinct().count()

    vaccination_due = VaccinationRecord.objects.filter(
        farm_id=farm_id,
        next_due_date__gte=today,
        animal__isnull=False,
    ).count()

    quarantine_count = QuarantineRecord.objects.filter(
        farm_id=farm_id,
        status="active",
    ).count()

    recovered = Animal.objects.filter(farm_id=farm_id, health_status="recovering").count()

    # ── Disease trend Mon–Sun this week ────────────────────────────────────────
    disease_base_qs = TreatmentRecord.objects.filter(farm_id=farm_id)
    disease_week_start = resolve_trend_start(disease_base_qs, "treatment_date", week_monday, week_sunday)
    disease_by_day = {d: 0 for d in daily_trend_range(disease_week_start, week_sunday)}
    disease_qs = (
        disease_base_qs.filter(
            treatment_date__gte=disease_week_start,
            treatment_date__lte=week_sunday,
        )
        .values("treatment_date")
        .annotate(count=Count("id"))
    )
    for row in disease_qs:
        if row["treatment_date"] in disease_by_day:
            disease_by_day[row["treatment_date"]] = row["count"]
    disease_trend = [
        {"day": d.strftime("%a")[0], "date": d.isoformat(), "count": disease_by_day[d]}
        for d in sorted(disease_by_day)
    ]

    # ── Active treatments ──────────────────────────────────────────────────────
    active_treatments_qs = (
        TreatmentRecord.objects.select_related("animal")
        .filter(farm_id=farm_id, next_follow_up_date__gte=today, animal__isnull=False)
        .order_by("next_follow_up_date")[:6]
    )
    active_treatments = [
        {
            "id": t.id,
            "animal_id": t.animal.id,
            "tag_id": t.animal.tag_id,
            "diagnosis": t.diagnosis,
            "treatment_date": t.treatment_date,
            "next_follow_up_date": t.next_follow_up_date,
            "severity": t.severity,
        }
        for t in active_treatments_qs
    ]

    # ── Treatment success rate (last 7 days) ───────────────────────────────────
    seven_days_ago = today - timedelta(days=6)
    recent_treatments = TreatmentRecord.objects.filter(
        farm_id=farm_id,
        treatment_date__gte=seven_days_ago,
    )
    total_recorded = recent_treatments.count()
    rate_recovered = recent_treatments.filter(
        animal__health_status="recovering"
    ).count()
    rate_ongoing = recent_treatments.filter(
        next_follow_up_date__gte=today
    ).count()
    rate_severe = recent_treatments.filter(severity="severe").count()

    treatment_success_rate = {
        "total_recorded": total_recorded,
        "recovered": rate_recovered,
        "ongoing_treatment": rate_ongoing,
        "severe": rate_severe,
    }

    # ── Vaccination due ────────────────────────────────────────────────────────
    vaccination_due_qs = (
        VaccinationRecord.objects.select_related("animal")
        .filter(farm_id=farm_id, next_due_date__gte=today, animal__isnull=False)
        .order_by("next_due_date")[:5]
    )
    vaccination_due_list = [
        {
            "id": v.id,
            "animal_id": v.animal.id,
            "tag_id": v.animal.tag_id,
            "vaccine_name": v.vaccine_name,
            "next_due_date": v.next_due_date,
        }
        for v in vaccination_due_qs
    ]

    # ── High risk alert — v2: livestock_species fallback ──────────────────────
    high_risk_qs = (
        TreatmentRecord.objects.select_related(
            "animal", "animal__livestock_species", "animal__species"
        )
        .filter(
            farm_id=farm_id,
            severity="severe",
            animal__isnull=False,
        )
        .order_by("next_follow_up_date")[:5]
    )
    high_risk_alerts = []
    for t in high_risk_qs:
        if t.next_follow_up_date and t.next_follow_up_date < today:
            overdue_days = (today - t.next_follow_up_date).days
            follow_up_status = f"Follow-up overdue by {overdue_days} day{'s' if overdue_days != 1 else ''}"
        elif t.next_follow_up_date:
            follow_up_status = f"Follow-up due {t.next_follow_up_date.isoformat()}"
        else:
            follow_up_status = "No follow-up scheduled"
        high_risk_alerts.append({
            "id": t.id,
            "animal_id": t.animal.id,
            "tag_id": t.animal.tag_id,
            "species": (
                t.animal.livestock_species.name if t.animal.livestock_species
                else (t.animal.species.name if t.animal.species else None)
            ),
            "diagnosis": t.diagnosis,
            "severity": t.severity,
            "follow_up_status": follow_up_status,
            "next_follow_up_date": t.next_follow_up_date,
        })

    # ── Quarantine animals ─────────────────────────────────────────────────────
    quarantine_qs = (
        QuarantineRecord.objects.select_related("animal")
        .filter(farm_id=farm_id)
        .order_by("-start_date")[:6]
    )
    quarantine_animals = [
        {
            "id": q.id,
            "animal_id": q.animal.id,
            "tag_id": q.animal.tag_id,
            "reason": q.reason,
            "start_date": q.start_date,
            "end_date": q.end_date,
            "status": "Recovered" if q.status == "released" else "Quarantine",
        }
        for q in quarantine_qs
    ]

    data = {
        "stats": {
            "sick_animals": sick_animals,
            "under_treatment": under_treatment,
            "vaccination_due": vaccination_due,
            "quarantine_count": quarantine_count,
            "recovered": recovered,
        },
        "disease_trend": disease_trend,
        "active_treatments": active_treatments,
        "treatment_success_rate": treatment_success_rate,
        "vaccination_due_list": vaccination_due_list,
        "high_risk_alerts": high_risk_alerts,
        "quarantine_animals": quarantine_animals,
    }
    return 200, APIResponse(success=True, message="Health dashboard", data=data)


@router.get("/mortality-dashboard/v2/{farm_id}", response={200: APIResponse, 403: APIResponse})
def mortality_dashboard_v2(request, farm_id: int, page: int = 1, page_size: int = 10):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.MovementRecord.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from health.models import MortalityRecord

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    # ── Stats ──────────────────────────────────────────────────────────────────
    base_qs = MortalityRecord.objects.filter(farm_id=farm_id)

    deaths_today = base_qs.filter(death_date=today).count()
    deaths_this_week = base_qs.filter(death_date__gte=week_monday, death_date__lte=today).count()
    deaths_this_month = base_qs.filter(death_date__gte=month_start, death_date__lte=today).count()

    total_animals = Animal.objects.filter(farm_id=farm_id).count()
    mortality_rate = (
        round((deaths_this_month / total_animals) * 100, 1) if total_animals else 0
    )

    # ── Paginated mortality records — v2: livestock_species/breed fallback ─────
    records_qs = (
        base_qs.select_related(
            "animal",
            "animal__livestock_species", "animal__species",
            "animal__livestock_breed", "animal__breed",
            "created_by",
        )
        .order_by("-death_date")
    )
    paginator = Paginator(records_qs, page_size)
    page_obj = paginator.page(page)

    records = [
        {
            "id": r.id,
            "animal_id": r.animal.id,
            "animal_tag": r.animal.tag_id,
            "species": (
                r.animal.livestock_species.name if r.animal.livestock_species
                else (r.animal.species.name if r.animal.species else None)
            ),
            "breed": (
                r.animal.livestock_breed.name if r.animal.livestock_breed
                else (r.animal.breed.name if r.animal.breed else None)
            ),
            "cause": r.cause,
            "death_date": r.death_date,
            "recorded_by": (
                f"{r.created_by.first_name} {r.created_by.last_name}".strip()
                or r.created_by.email
            ) if r.created_by else None,
            "status": r.status.title(),
            "notes": r.notes,
        }
        for r in page_obj.object_list
    ]

    data = {
        "stats": {
            "deaths_today": deaths_today,
            "deaths_this_week": deaths_this_week,
            "deaths_this_month": deaths_this_month,
            "mortality_rate": mortality_rate,
        },
        "records": records,
        "num_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "total_items": paginator.count,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }
    return 200, APIResponse(success=True, message="Mortality dashboard", data=data)


@router.get("/transaction-dashboard/v2/{farm_id}", response={200: APIResponse, 403: APIResponse})
def transaction_dashboard_v2(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.SalesRecord.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from movement_records.models import SalesRecord
    from health.models import MortalityRecord

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())
    week_sunday = week_monday + timedelta(days=6)
    month_start = today.replace(day=1)

    # ── Top stats ──────────────────────────────────────────────────────────────
    sales_this_period = SalesRecord.objects.filter(
        farm_id=farm_id,
        sale_date__date__gte=month_start,
    ).count()

    total_sales_value = (
        SalesRecord.objects.filter(farm_id=farm_id, sale_date__date__gte=month_start)
        .aggregate(total=Sum("price"))["total"] or 0
    )

    mortality_this_period = MortalityRecord.objects.filter(
        farm_id=farm_id,
        death_date__gte=month_start,
    ).count()

    animals_exited = sales_this_period + mortality_this_period

    pending_corrections = MortalityRecord.objects.filter(
        farm_id=farm_id,
        status="recorded",
    ).count()

    # ── Exit summary by species — v2: group by livestock_species ──────────────
    from django.db.models import Count as _Count
    species_sales = (
        SalesRecord.objects.filter(farm_id=farm_id, sale_date__date__gte=month_start)
        .values("animal__livestock_species__id", "animal__livestock_species__name")
        .annotate(sold=_Count("id"))
    )
    species_deaths = (
        MortalityRecord.objects.filter(farm_id=farm_id, death_date__gte=month_start)
        .values("animal__livestock_species__id", "animal__livestock_species__name")
        .annotate(deaths=_Count("id"))
    )

    species_sales_map = {r["animal__livestock_species__id"]: r for r in species_sales}
    species_deaths_map = {r["animal__livestock_species__id"]: r for r in species_deaths}
    all_species_ids = set(species_sales_map) | set(species_deaths_map)

    exit_summary = []
    for sid in all_species_ids:
        sold = species_sales_map.get(sid, {}).get("sold", 0)
        deaths = species_deaths_map.get(sid, {}).get("deaths", 0)
        name = (
            species_sales_map.get(sid) or species_deaths_map.get(sid)
        ).get("animal__livestock_species__name")
        exit_summary.append({
            "species_id": sid,
            "species": name,
            "sold": sold,
            "deaths": deaths,
            "total_exited": sold + deaths,
        })

    # ── Sales trend Mon–Sun this week ──────────────────────────────────────────
    sales_base_qs = SalesRecord.objects.filter(farm_id=farm_id)
    sales_week_start = resolve_trend_start(sales_base_qs, "sale_date", week_monday, week_sunday)
    sales_by_day = {d: 0 for d in daily_trend_range(sales_week_start, week_sunday)}
    sales_trend_qs = (
        sales_base_qs.filter(
            sale_date__date__gte=sales_week_start,
            sale_date__date__lte=week_sunday,
        )
        .values("sale_date__date")
        .annotate(count=_Count("id"))
    )
    for row in sales_trend_qs:
        d = row["sale_date__date"]
        if d in sales_by_day:
            sales_by_day[d] = row["count"]
    sales_trend = [
        {"day": d.strftime("%a")[0], "date": d.isoformat(), "count": sales_by_day[d]}
        for d in sorted(sales_by_day)
    ]

    # ── Mortality trend Mon–Sun this week ──────────────────────────────────────
    mortality_base_qs = MortalityRecord.objects.filter(farm_id=farm_id)
    mortality_week_start = resolve_trend_start(mortality_base_qs, "death_date", week_monday, week_sunday)
    mortality_by_day = {d: 0 for d in daily_trend_range(mortality_week_start, week_sunday)}
    mortality_trend_qs = (
        mortality_base_qs.filter(
            death_date__gte=mortality_week_start,
            death_date__lte=week_sunday,
        )
        .values("death_date")
        .annotate(count=_Count("id"))
    )
    for row in mortality_trend_qs:
        d = row["death_date"]
        if d in mortality_by_day:
            mortality_by_day[d] = row["count"]
    mortality_trend = [
        {"day": d.strftime("%a")[0], "date": d.isoformat(), "count": mortality_by_day[d]}
        for d in sorted(mortality_by_day)
    ]

    # ── High mortality alert ───────────────────────────────────────────────────
    last_30_days = today - timedelta(days=30)
    disease_deaths = (
        MortalityRecord.objects.filter(farm_id=farm_id, death_date__gte=last_30_days)
        .count()
    )
    alert_message = None
    if disease_deaths >= 2:
        month_name = today.strftime("%B")
        alert_message = (
            f"Abnormal pattern detected: {disease_deaths} disease-linked deaths in "
            f"{month_name}. Review herd health status and check vaccination schedules."
        )

    alert_animals_qs = (
        Animal.objects.select_related("livestock_species", "species")
        .filter(farm_id=farm_id, health_status="at_risk")[:5]
    )
    high_mortality_alert = {
        "message": alert_message,
        "animals": [
            {
                "animal_id": a.id,
                "tag_id": a.tag_id,
                "species": (
                    a.livestock_species.name if a.livestock_species
                    else (a.species.name if a.species else None)
                ),
                "level": "Alert",
            }
            for a in alert_animals_qs
        ],
    }

    # ── Recent sales — v2: livestock_species fallback ─────────────────────────
    recent_sales_qs = (
        SalesRecord.objects.select_related("animal", "animal__livestock_species", "animal__species")
        .filter(farm_id=farm_id)
        .order_by("-sale_date")[:5]
    )
    recent_sales = [
        {
            "id": s.id,
            "animal_id": s.animal.id,
            "animal_tag": s.animal.tag_id,
            "species": (
                s.animal.livestock_species.name if s.animal.livestock_species
                else (s.animal.species.name if s.animal.species else None)
            ),
            "buyer_name": s.buyer_name,
            "price": s.price,
            "sale_date": s.sale_date.date(),
        }
        for s in recent_sales_qs
    ]

    # ── Recent mortality — v2: livestock_species fallback ─────────────────────
    recent_mortality_qs = (
        MortalityRecord.objects.select_related("animal", "animal__livestock_species", "animal__species")
        .filter(farm_id=farm_id)
        .order_by("-death_date")[:5]
    )
    recent_mortality = [
        {
            "id": m.id,
            "animal_id": m.animal.id,
            "animal_tag": m.animal.tag_id,
            "species": (
                m.animal.livestock_species.name if m.animal.livestock_species
                else (m.animal.species.name if m.animal.species else None)
            ),
            "cause": m.cause,
            "death_date": m.death_date,
            "status": m.status,
        }
        for m in recent_mortality_qs
    ]

    data = {
        "stats": {
            "sales_this_period": sales_this_period,
            "total_sales_value": total_sales_value,
            "mortality_this_period": mortality_this_period,
            "animals_exited": animals_exited,
            "pending_corrections": pending_corrections,
        },
        "exit_summary": exit_summary,
        "sales_trend": sales_trend,
        "mortality_trend": mortality_trend,
        "high_mortality_alert": high_mortality_alert,
        "recent_sales": recent_sales,
        "recent_mortality": recent_mortality,
    }
    return 200, APIResponse(success=True, message="Transaction dashboard", data=data)


@router.get("/sales-dashboard/v2/{farm_id}", response={200: APIResponse, 403: APIResponse})
def sales_dashboard_v2(
    request,
    farm_id: int,
    page: int = 1,
    page_size: int = 10,
    status: str = None,
    species_id: int = None,
    date_from: str = None,
    date_to: str = None,
    search: str = None,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.SalesRecord.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from movement_records.models import SalesRecord

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    # ── Top stats (always unfiltered) ──────────────────────────────────────────
    base_stats = SalesRecord.objects.filter(farm_id=farm_id)

    sales_today = base_stats.filter(sale_date__date=today).count()
    sales_this_week = base_stats.filter(sale_date__date__gte=week_monday).count()
    sales_this_month = base_stats.filter(sale_date__date__gte=month_start).count()
    total_sales_value = (
        base_stats.filter(sale_date__date__gte=month_start)
        .aggregate(total=Sum("price"))["total"] or 0
    )

    # ── Filtered records — v2: livestock_species filter + fallback output ──────
    qs = (
        SalesRecord.objects.select_related(
            "animal",
            "animal__livestock_species", "animal__species",
            "animal__livestock_breed", "animal__breed",
            "created_by",
        )
        .filter(farm_id=farm_id)
        .order_by("-sale_date")
    )

    if status:
        qs = qs.filter(status=status)
    if species_id:
        qs = qs.filter(animal__livestock_species_id=species_id)
    if date_from:
        qs = qs.filter(sale_date__date__gte=date_from)
    if date_to:
        qs = qs.filter(sale_date__date__lte=date_to)
    if search:
        qs = qs.filter(
            Q(animal__tag_id__icontains=search) | Q(buyer_name__icontains=search)
        )

    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)

    records = [
        {
            "id": s.id,
            "animal_id": s.animal.id,
            "animal_tag": s.animal.tag_id,
            "species": (
                s.animal.livestock_species.name if s.animal.livestock_species
                else (s.animal.species.name if s.animal.species else None)
            ),
            "breed": (
                s.animal.livestock_breed.name if s.animal.livestock_breed
                else (s.animal.breed.name if s.animal.breed else None)
            ),
            "buyer": s.buyer_name,
            "price": s.price,
            "sale_date": s.sale_date.date(),
            "recorded_by": (
                f"{s.created_by.first_name} {s.created_by.last_name}".strip()
                or s.created_by.email
            ) if s.created_by else None,
            "status": s.status.title(),
        }
        for s in page_obj.object_list
    ]

    data = {
        "stats": {
            "sales_today": sales_today,
            "sales_this_week": sales_this_week,
            "sales_this_month": sales_this_month,
            "total_sales_value": total_sales_value,
        },
        "records": records,
        "num_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "total_items": paginator.count,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }
    return 200, APIResponse(success=True, message="Sales dashboard", data=data)


@router.get("/feed-inventory-dashboard/v2/{farm_id}", response={200: APIResponse, 403: APIResponse})
def feed_inventory_dashboard_v2(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Feed.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from feed.models import FeedInventory, FeedIssuanceRecord, FeedConfirmationRecord, FeedPlan

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())
    week_sunday = week_monday + timedelta(days=6)

    # ── Top stats ──────────────────────────────────────────────────────────────
    inventory_qs = FeedInventory.objects.filter(farm_id=farm_id)

    total_stock_agg = inventory_qs.aggregate(total=Sum("quantity_available"))
    total_stock = total_stock_agg["total"] or 0
    top_stock_item = inventory_qs.order_by("-quantity_available").values("feed_name").first()
    top_stock_name = top_stock_item["feed_name"] if top_stock_item else None

    low_stock_qs = inventory_qs.filter(status="low_stock")
    low_stock_count = low_stock_qs.count()
    low_stock_names = ", ".join(low_stock_qs.values_list("feed_name", flat=True)[:3])

    issuance_today_qs = FeedIssuanceRecord.objects.filter(farm_id=farm_id, issue_date=today)
    feed_issued_today = issuance_today_qs.aggregate(total=Sum("quantity_issued"))["total"] or 0
    top_issued_item = (
        issuance_today_qs.values("feed_inventory__feed_name")
        .annotate(total=Sum("quantity_issued"))
        .order_by("-total")
        .first()
    )
    top_issued_name = top_issued_item["feed_inventory__feed_name"] if top_issued_item else None

    confirmed_today_qs = FeedConfirmationRecord.objects.filter(
        farm__id=farm_id, confirmation_date=today
    )
    feed_confirmed_today = confirmed_today_qs.aggregate(total=Sum("actual_used_quantity"))["total"] or 0
    top_confirmed_item = (
        confirmed_today_qs.values("issuance__feed_inventory__feed_name")
        .annotate(total=Sum("actual_used_quantity"))
        .order_by("-total")
        .first()
    )
    top_confirmed_name = (
        top_confirmed_item["issuance__feed_inventory__feed_name"] if top_confirmed_item else None
    )

    variance_alerts = (
        FeedConfirmationRecord.objects.filter(farm__id=farm_id, status="variance_detected")
        .aggregate(total=Sum("variance_quantity"))["total"] or 0
    )

    pending_issuance_ids = FeedConfirmationRecord.objects.filter(
        farm__id=farm_id
    ).values_list("issuance_id", flat=True)
    pending_qty = (
        FeedIssuanceRecord.objects.filter(farm_id=farm_id)
        .exclude(id__in=pending_issuance_ids)
        .aggregate(total=Sum("quantity_issued"))["total"] or 0
    )

    # ── Stock trend Mon–Sun this week ──────────────────────────────────────────
    issuance_base_qs = FeedIssuanceRecord.objects.filter(farm_id=farm_id)
    feed_week_start = resolve_trend_start(issuance_base_qs, "issue_date", week_monday, week_sunday)
    stock_by_day = {d: 0 for d in daily_trend_range(feed_week_start, week_sunday)}
    stock_trend_qs = (
        issuance_base_qs.filter(
            issue_date__gte=feed_week_start,
            issue_date__lte=week_sunday,
        )
        .values("issue_date")
        .annotate(total=Sum("quantity_issued"))
    )
    for row in stock_trend_qs:
        if row["issue_date"] in stock_by_day:
            stock_by_day[row["issue_date"]] = float(row["total"])
    stock_trend = [
        {"day": d.strftime("%a")[0], "date": d.isoformat(), "total_issued": stock_by_day[d]}
        for d in sorted(stock_by_day)
    ]

    # ── Pending confirmations list ─────────────────────────────────────────────
    pending_conf_qs = (
        FeedIssuanceRecord.objects.select_related("feed_inventory", "group", "animal")
        .filter(farm_id=farm_id)
        .exclude(id__in=pending_issuance_ids)
        .order_by("-issue_date")[:5]
    )
    pending_confirmations = [
        {
            "id": r.id,
            "target": r.group.name if r.group else (r.animal.tag_id if r.animal else None),
            "target_type": r.target_type,
            "feed_name": r.feed_inventory.feed_name,
            "quantity_issued": r.quantity_issued,
            "issue_date": r.issue_date,
            "status": "Pending",
        }
        for r in pending_conf_qs
    ]

    # ── Issued vs Used Feed Mon–Sun this week ──────────────────────────────────
    # shares feed_week_start with the stock trend above so both series cover the
    # same days (used_by_day must have every key issued_by_day has)
    issued_by_day = {d: 0 for d in daily_trend_range(feed_week_start, week_sunday)}
    used_by_day = {d: 0 for d in daily_trend_range(feed_week_start, week_sunday)}

    for row in stock_trend_qs:
        if row["issue_date"] in issued_by_day:
            issued_by_day[row["issue_date"]] = float(row["total"])

    used_qs = (
        FeedConfirmationRecord.objects.filter(
            farm__id=farm_id,
            confirmation_date__gte=feed_week_start,
            confirmation_date__lte=week_sunday,
        )
        .values("confirmation_date")
        .annotate(total=Sum("actual_used_quantity"))
    )
    for row in used_qs:
        if row["confirmation_date"] in used_by_day:
            used_by_day[row["confirmation_date"]] = float(row["total"])

    issued_vs_used = [
        {
            "day": d.strftime("%a")[0],
            "date": d.isoformat(),
            "issued": issued_by_day[d],
            "used": used_by_day[d],
            "usage_pct": (
                round((used_by_day[d] / issued_by_day[d]) * 100, 1)
                if issued_by_day[d] else 0
            ),
        }
        for d in sorted(issued_by_day)
    ]

    # ── Issuance vs Confirmation today ────────────────────────────────────────
    today_issued = float(feed_issued_today)
    today_confirmed = float(feed_confirmed_today)
    issuance_vs_confirmation = {
        "issued": today_issued,
        "confirmed": today_confirmed,
        "difference": round(today_issued - today_confirmed, 2),
    }

    # ── Low stock levels ──────────────────────────────────────────────────────
    low_stock_levels = [
        {
            "id": item.id,
            "feed_name": item.feed_name,
            "quantity_available": item.quantity_available,
            "unit": item.unit,
            "reorder_level": item.reorder_level,
            "status": item.status,
        }
        for item in low_stock_qs.order_by("quantity_available")[:5]
    ]

    # ── Feed plan summary — v2: livestock_species fallback + filter ───────────
    feed_plan_qs = (
        FeedPlan.objects.select_related("feed_inventory", "livestock_species", "species", "group")
        .filter(farm_id=farm_id, status="active")
        .order_by("-start_date")[:5]
    )
    feed_plan_summary = [
        {
            "id": p.id,
            "plan_type": p.plan_type,
            "target": (
                p.livestock_species.name if p.livestock_species
                else (p.species.name if p.species else (p.group.name if p.group else None))
            ),
            "feed_name": p.feed_inventory.feed_name,
            "daily_feed_quantity": p.daily_feed_quantity,
            "unit": p.unit,
            "start_date": p.start_date,
            "end_date": p.end_date,
            "status": p.status,
        }
        for p in feed_plan_qs
    ]

    data = {
        "stats": {
            "total_stock": total_stock,
            "top_stock_feed": top_stock_name,
            "low_stock_count": low_stock_count,
            "low_stock_names": low_stock_names,
            "feed_issued_today": feed_issued_today,
            "top_issued_feed": top_issued_name,
            "feed_confirmed_today": feed_confirmed_today,
            "top_confirmed_feed": top_confirmed_name,
            "variance_alerts": variance_alerts,
            "pending_feed_confirmation": pending_qty,
        },
        "stock_trend": stock_trend,
        "pending_confirmations": pending_confirmations,
        "issued_vs_used": issued_vs_used,
        "issuance_vs_confirmation_today": issuance_vs_confirmation,
        "low_stock_levels": low_stock_levels,
        "feed_plan_summary": feed_plan_summary,
    }
    return 200, APIResponse(success=True, message="Feed & inventory dashboard", data=data)


@router.get("/feed-plan-dashboard/v2/{farm_id}", response={200: APIResponse, 403: APIResponse})
def feed_plan_dashboard_v2(
    request,
    farm_id: int,
    page: int = 1,
    page_size: int = 10,
    plan_type: str = None,
    status: str = None,
    search: str = None,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Feed.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from feed.models import FeedPlan

    base_qs = FeedPlan.objects.filter(farm_id=farm_id)

    # ── Stats (always unfiltered) ──────────────────────────────────────────────
    active_plans = base_qs.filter(status="active").count()
    species_based_plans = base_qs.filter(plan_type="species").count()
    group_based_plans = base_qs.filter(plan_type="group").count()

    # ── Filtered + paginated table — v2: livestock_species in select_related/search ──
    qs = (
        base_qs
        .select_related("feed_inventory", "livestock_species", "species", "group")
        .order_by("-start_date")
    )

    if plan_type:
        qs = qs.filter(plan_type=plan_type)
    if status:
        qs = qs.filter(status=status)
    if search:
        qs = qs.filter(
            Q(feed_inventory__feed_name__icontains=search)
            | Q(livestock_species__name__icontains=search)
            | Q(species__name__icontains=search)
            | Q(group__name__icontains=search)
        )

    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)

    records = []
    for p in page_obj.object_list:
        if p.plan_type == "species":
            # v2: prefer livestock_species, fall back to species
            target_name = (
                p.livestock_species.name if p.livestock_species
                else (p.species.name if p.species else None)
            )
            if p.livestock_species:
                target_count = Animal.objects.filter(
                    farm_id=farm_id, livestock_species=p.livestock_species, is_active=True
                ).count()
            elif p.species:
                target_count = Animal.objects.filter(
                    farm_id=farm_id, species=p.species, is_active=True
                ).count()
            else:
                target_count = 0
        else:
            target_name = p.group.name if p.group else None
            target_count = (
                p.group.members.filter(status="active").count()
                if p.group else 0
            )

        records.append({
            "id": p.id,
            "plan_name": p.feed_inventory.feed_name,
            "plan_type": p.plan_type,
            "target_type": target_name,
            "target_count": target_count,
            "daily_feed_quantity": p.daily_feed_quantity,
            "unit": p.unit,
            "feed_inventory_status": p.feed_inventory.status.replace("_", " ").title(),
            "plan_status": p.status,
            "start_date": p.start_date,
            "end_date": p.end_date,
        })

    data = {
        "stats": {
            "active_plans": active_plans,
            "species_based_plans": species_based_plans,
            "group_based_plans": group_based_plans,
        },
        "records": records,
        "num_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "total_items": paginator.count,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }
    return 200, APIResponse(success=True, message="Feed plan dashboard", data=data)


@router.get("/livestock-report-dashboard/v2/{farm_id}", response={200: APIResponse, 403: APIResponse})
def livestock_report_dashboard_v2(
    request,
    farm_id: int,
    page: int = 1,
    page_size: int = 10,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    if not user.organizations.first():
        raise HttpError(403, "Permission denied")

    from health.models import MortalityRecord
    from reproduction.models import BirthRecord

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())
    week_sunday = week_monday + timedelta(days=6)
    month_start = today.replace(day=1)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_end = month_start

    base_qs = Animal.objects.filter(farm_id=farm_id)

    # ── Top stats ──────────────────────────────────────────────────────────────
    total_animals = base_qs.count()
    active = base_qs.filter(is_active=True).count()
    pregnant = base_qs.filter(is_pregnant=True).count()
    lactating = base_qs.filter(is_lactating=True).count()
    sick = base_qs.filter(health_status="sick").count()

    deaths_this_month = MortalityRecord.objects.filter(
        farm_id=farm_id, death_date__gte=month_start
    ).count()
    mortality_rate = (
        round((deaths_this_month / total_animals) * 100, 1) if total_animals else 0
    )

    # ── Population by species — v2: group by livestock_species ────────────────
    species_pop = list(
        base_qs.values("livestock_species__id", "livestock_species__name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    population_by_species = [
        {
            "species_id": s["livestock_species__id"],
            "species": s["livestock_species__name"],
            "count": s["count"],
        }
        for s in species_pop
    ]

    # ── Lifecycle distribution Mon–Sun this week ───────────────────────────────
    lifecycle_week_start = resolve_trend_start(base_qs, "created_at", week_monday, week_sunday)
    lifecycle_by_day = {d: 0 for d in daily_trend_range(lifecycle_week_start, week_sunday)}
    new_animals_qs = base_qs.filter(
        created_at__date__gte=lifecycle_week_start,
        created_at__date__lte=week_sunday,
    ).values("created_at__date").annotate(count=Count("id"))
    for row in new_animals_qs:
        d = row["created_at__date"]
        if d in lifecycle_by_day:
            lifecycle_by_day[d] = row["count"]
    lifecycle_distribution = [
        {"day": d.strftime("%a")[0], "date": d.isoformat(), "count": lifecycle_by_day[d]}
        for d in sorted(lifecycle_by_day)
    ]

    # ── Birth vs Death trend ───────────────────────────────────────────────────
    births_this_month = BirthRecord.objects.filter(
        farm_id=farm_id, birth_date__gte=month_start
    ).aggregate(total=Sum("number_alive"))["total"] or 0

    total_bd = births_this_month + deaths_this_month
    birth_pct = round((births_this_month / total_bd) * 100, 1) if total_bd else 0
    death_pct = round((deaths_this_month / total_bd) * 100, 1) if total_bd else 0

    birth_vs_death = {
        "births": births_this_month,
        "deaths": deaths_this_month,
        "birth_pct": birth_pct,
        "death_pct": death_pct,
    }

    # ── Species breakdown table — v2: group by livestock_species ──────────────
    all_species = (
        base_qs.values("livestock_species__id", "livestock_species__name")
        .annotate(
            count=Count("id"),
            male=Count("id", filter=Q(gender="male")),
            female=Count("id", filter=Q(gender="female")),
        )
        .order_by("livestock_species__name")
    )

    last_month_counts = {
        row["livestock_species__id"]: row["count"]
        for row in Animal.objects.filter(
            farm_id=farm_id,
            created_at__date__lt=last_month_end,
        )
        .values("livestock_species__id")
        .annotate(count=Count("id"))
    }

    rows = []
    for s in all_species:
        sid = s["livestock_species__id"]
        current = s["count"]
        previous = last_month_counts.get(sid, 0)
        if previous:
            growth = round(((current - previous) / previous) * 100, 1)
        else:
            growth = None
        rows.append({
            "species_id": sid,
            "species": s["livestock_species__name"],
            "count": current,
            "male": s["male"],
            "female": s["female"],
            "growth_rate": growth,
        })

    total_items = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start: start + page_size]
    num_pages = max(1, (total_items + page_size - 1) // page_size)

    data = {
        "stats": {
            "total_animals": total_animals,
            "active": active,
            "pregnant": pregnant,
            "lactating": lactating,
            "sick": sick,
            "mortality_rate": f"{mortality_rate}%",
        },
        "population_by_species": population_by_species,
        "lifecycle_distribution": lifecycle_distribution,
        "birth_vs_death": birth_vs_death,
        "species_breakdown": page_rows,
        "num_pages": num_pages,
        "current_page": page,
        "total_items": total_items,
        "has_next": (start + page_size) < total_items,
        "has_previous": page > 1,
    }
    return 200, APIResponse(success=True, message="Livestock report dashboard", data=data)


@router.get("/production-report/v2/{farm_id}", response={200: APIResponse, 403: APIResponse})
def production_report_v2(
    request,
    farm_id: int,
    page: int = 1,
    page_size: int = 10,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Production.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")
       
    from animals.models import MilkRecord, DailyMilkSummary

    today = timezone.localdate()
    week_monday = today - timedelta(days=today.weekday())
    week_sunday = week_monday + timedelta(days=6)
    month_start = today.replace(day=1)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_end = month_start

    # ── Top stats ──────────────────────────────────────────────────────────────
    total_milk = (
        DailyMilkSummary.objects.filter(farm_id=farm_id, date=today)
        .aggregate(total=Sum("total_litres"))["total"] or 0
    )

    lactating_count = Animal.objects.filter(farm_id=farm_id, is_lactating=True).count()

    if lactating_count:
        avg_per_animal = float(total_milk) / lactating_count
        farm_max = float(
            MilkRecord.objects.filter(farm_id=farm_id, record_date=today)
            .values("animal_id").annotate(daily=Sum("quantity"))
            .aggregate(mx=Sum("daily"))["mx"] or 1
        )
        max_per_animal = farm_max / lactating_count if lactating_count else 1
        avg_yield_pct = round((avg_per_animal / max_per_animal) * 100, 1) if max_per_animal else 0
    else:
        avg_yield_pct = 0

    production_trend_count = DailyMilkSummary.objects.filter(
        farm_id=farm_id,
        date__gte=month_start,
        total_litres__gt=0,
    ).count()

    # ── Milk trend Mon–Sun this week ───────────────────────────────────────────
    milk_base_qs = DailyMilkSummary.objects.filter(farm_id=farm_id)
    milk_week_start = resolve_trend_start(milk_base_qs, "date", week_monday, week_sunday)
    milk_by_day = {d: 0.0 for d in daily_trend_range(milk_week_start, week_sunday)}
    milk_trend_qs = milk_base_qs.filter(
        date__gte=milk_week_start,
        date__lte=week_sunday,
    ).values("date", "total_litres")
    for row in milk_trend_qs:
        if row["date"] in milk_by_day:
            milk_by_day[row["date"]] = float(row["total_litres"])
    milk_trend = [
        {"day": d.strftime("%a")[0], "date": d.isoformat(), "total_litres": milk_by_day[d]}
        for d in sorted(milk_by_day)
    ]

    # ── Monthly totals helper (Jan → current month) ────────────────────────────
    def monthly_milk_series(farm_id, year):
        months = []
        for m in range(1, today.month + 1):
            ms = today.replace(month=m, day=1)
            me = today.replace(month=m + 1, day=1) if m < 12 else today.replace(year=year + 1, month=1, day=1)
            total = (
                DailyMilkSummary.objects.filter(
                    farm_id=farm_id, date__gte=ms, date__lt=me
                ).aggregate(t=Sum("total_litres"))["t"] or 0
            )
            months.append({"month": ms.strftime("%b"), "year_month": ms.strftime("%Y-%m"), "total_litres": float(total)})
        return months

    monthly_series = monthly_milk_series(farm_id, today.year)
    values = [m["total_litres"] for m in monthly_series]
    max_val = max(values) if values else 1
    avg_val = (sum(values) / len(values)) if values else 0

    top_producers_chart = [
        {**m, "is_top": m["total_litres"] >= avg_val}
        for m in monthly_series
    ]
    low_producers_chart = [
        {**m, "is_low": m["total_litres"] < avg_val and m["total_litres"] > 0}
        for m in monthly_series
    ]

    # ── Per-species table — v2: group by animal__livestock_species ────────────
    species_this_month = (
        MilkRecord.objects.filter(farm_id=farm_id, record_date__gte=month_start)
        .values("animal__livestock_species__id", "animal__livestock_species__name")
        .annotate(total=Sum("quantity"), records=Count("id"))
    )
    species_last_month = {
        row["animal__livestock_species__id"]: float(row["total"] or 0)
        for row in MilkRecord.objects.filter(
            farm_id=farm_id,
            record_date__gte=last_month_start,
            record_date__lt=last_month_end,
        )
        .values("animal__livestock_species__id")
        .annotate(total=Sum("quantity"))
    }

    all_rows = []
    for s in species_this_month:
        sid = s["animal__livestock_species__id"]
        current_total = float(s["total"] or 0)
        prev_total = species_last_month.get(sid, 0)
        lact_count = Animal.objects.filter(
            farm_id=farm_id, livestock_species_id=sid, is_lactating=True
        ).count()
        records = s["records"] or 1
        avg_yield = round((current_total / records), 2) if records else 0
        avg_yield_species_pct = round((avg_yield / (max_val / (len(monthly_series) or 1))) * 100, 1) if max_val else 0

        if prev_total:
            growth = round(((current_total - prev_total) / prev_total) * 100, 1)
        else:
            growth = None

        all_rows.append({
            "species_id": sid,
            "species": s["animal__livestock_species__name"],
            "lactating_count": lact_count,
            "avg_yield_pct": avg_yield_species_pct,
            "total_production": current_total,
            "growth_rate": growth,
        })

    total_items = len(all_rows)
    start = (page - 1) * page_size
    page_rows = all_rows[start: start + page_size]
    num_pages = max(1, (total_items + page_size - 1) // page_size)

    data = {
        "stats": {
            "total_milk_today": float(total_milk),
            "avg_yield_pct": f"{avg_yield_pct}%",
            "lactating_animals": lactating_count,
            "production_trend_days": production_trend_count,
        },
        "milk_trend": milk_trend,
        "top_producers_chart": top_producers_chart,
        "low_producers_chart": low_producers_chart,
        "species_breakdown": page_rows,
        "num_pages": num_pages,
        "current_page": page,
        "total_items": total_items,
        "has_next": (start + page_size) < total_items,
        "has_previous": page > 1,
    }
    return 200, APIResponse(success=True, message="Production report", data=data)
