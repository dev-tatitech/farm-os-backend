from datetime import timedelta

from django.utils import timezone
from ninja import Router

from animals.models import Animal
from common.permissions import Permissions
from health.models import HealthAlert, HealthCase, HealthObservation, MortalityRecord, TreatmentRecord
from operations.models import Task
from operations.services import serialize_event, serialize_task, work_summary_for
from organization.models import Farm
from reproduction.models import PregnancyRecord

from .authz import require_farm, require_permission, require_user, resolve_organization
from .envelope import V2Error, V2Success, success_body
from .identity import display_name

dash_router = Router(tags=["Dashboard"])


def _open_tasks(org, farm=None):
    qs = Task.objects.filter(organization=org).exclude(
        status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED, Task.Status.UNABLE_TO_COMPLETE]
    )
    if farm:
        qs = qs.filter(farm=farm)
    return qs


@dash_router.get(
    "/organization/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Organization operational dashboard",
)
def org_dashboard(request):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Reports.LIVESTOCK_DASHBOARD, Permissions.Animal.VIEW)
    animals = Animal.objects.filter(farm__organization=org)
    farms = Farm.objects.filter(organization=org)
    open_tasks = _open_tasks(org)
    now = timezone.now()
    today = timezone.localdate()
    upcoming_vacc = Task.objects.filter(
        organization=org,
        task_type=Task.Type.VACCINATION,
        due_at__date__gte=today,
        due_at__date__lte=today + timedelta(days=7),
    ).exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED]).count()
    expected_births = PregnancyRecord.objects.filter(
        farm__organization=org,
        result="pregnant",
        expected_delivery_date__gte=today,
        expected_delivery_date__lte=today + timedelta(days=14),
    ).count()
    from animals.models import AnimalEvent

    recent = (
        AnimalEvent.objects.filter(farm__organization=org)
        .select_related("event_type", "animal", "farm", "created_by")
        .order_by("-event_date", "-id")[:10]
    )
    farm_breakdown = []
    for farm in farms:
        farm_open = _open_tasks(org, farm)
        farm_today = farm_open.filter(due_at__date=today)
        completed_today = Task.objects.filter(
            farm=farm, status=Task.Status.COMPLETED, completed_at__date=today
        ).count()
        scheduled = farm_today.count() + completed_today
        farm_breakdown.append(
            {
                "farm_id": farm.id,
                "name": farm.name,
                "active_animals": Animal.objects.filter(farm=farm, status="active").count(),
                "open_alerts": HealthAlert.objects.filter(farm=farm, status="open").count(),
                "overdue_tasks": farm_open.filter(due_at__lt=now).count(),
                "work_completion_percent": int((completed_today / scheduled) * 100) if scheduled else 100,
            }
        )
    data = {
        "organization": {
            "id": str(org.id),
            "name": org.name,
            "status": org.status,
            "timezone": "Africa/Lagos",
        },
        "livestock": {
            "total": animals.count(),
            "active": animals.filter(status="active").count(),
            "sold": animals.filter(status="sold").count(),
            "dead": animals.filter(status="dead").count(),
        },
        "operations": {
            "scheduled_today": open_tasks.filter(due_at__date=today).count(),
            "completed_today": Task.objects.filter(
                organization=org, status=Task.Status.COMPLETED, completed_at__date=today
            ).count(),
            "in_progress": open_tasks.filter(status=Task.Status.IN_PROGRESS).count(),
            "overdue": open_tasks.filter(due_at__lt=now).count(),
        },
        "attention": {
            "critical_health": animals.filter(health_status="sick").count(),
            "feed_risk": HealthAlert.objects.filter(
                farm__organization=org, status="open", alert_type__icontains="feed"
            ).count(),
            "quarantine": animals.filter(is_quarantine=True).count(),
            "overdue_operations": open_tasks.filter(due_at__lt=now).count(),
        },
        "upcoming": {
            "vaccinations_7_days": upcoming_vacc,
            "followups_7_days": Task.objects.filter(
                organization=org,
                parent__isnull=False,
                due_at__date__gte=today,
                due_at__date__lte=today + timedelta(days=7),
            )
            .exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
            .count(),
            "expected_births_14_days": expected_births,
        },
        "farm_breakdown": farm_breakdown,
        "recent_activity": [serialize_event(event) for event in recent],
        "formulas": {
            "work_completion_percent": "completed_today / scheduled_today * 100; 100 when scheduled_today = 0",
            "active_animals": "lifecycle_status = active",
            "critical_health": "count of animals with health_status = sick",
            "feed_risk": "open HealthAlert whose alert_type contains 'feed'",
            "expected_births": "PregnancyRecord result=pregnant and expected_delivery_date within 14 days",
        },
    }
    return 200, success_body(data=data, message="Organization dashboard fetched successfully.")


@dash_router.get(
    "/farm/{farm_id}/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Farm manager dashboard",
)
def farm_dashboard(request, farm_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Reports.LIVESTOCK_DASHBOARD, Permissions.Animal.VIEW)
    farm = require_farm(org, farm_id, user)
    animals = Animal.objects.filter(farm=farm)
    open_tasks = _open_tasks(org, farm)
    now = timezone.now()
    today = timezone.localdate()
    from animals.models import AnimalEvent
    from account.models import User

    team = []
    assignee_ids = open_tasks.exclude(assigned_to=None).values_list("assigned_to_id", flat=True).distinct()
    for assignee in User.objects.filter(id__in=assignee_ids):
        assigned_today = open_tasks.filter(assigned_to=assignee, due_at__date=today).count()
        team.append(
            {
                "user_id": str(assignee.id),
                "display_name": display_name(assignee),
                "assigned_today": assigned_today,
                "completed_today": Task.objects.filter(
                    farm=farm,
                    assigned_to=assignee,
                    status=Task.Status.COMPLETED,
                    completed_at__date=today,
                ).count(),
                "overdue": open_tasks.filter(assigned_to=assignee, due_at__lt=now).count(),
            }
        )
    recent = (
        AnimalEvent.objects.filter(farm=farm)
        .select_related("event_type", "animal", "farm", "created_by")
        .order_by("-event_date", "-id")[:10]
    )
    alerts = HealthAlert.objects.filter(farm=farm, status="open").select_related("animal")[:10]
    data = {
        "farm": {"id": farm.id, "name": farm.name, "status": farm.status, "timezone": "Africa/Lagos"},
        "livestock": {
            "total": animals.count(),
            "active": animals.filter(status="active").count(),
            "sold": animals.filter(status="sold").count(),
            "dead": animals.filter(status="dead").count(),
            "quarantine": animals.filter(is_quarantine=True).count(),
        },
        "today": {
            "scheduled": open_tasks.filter(due_at__date=today).count(),
            "completed": Task.objects.filter(
                farm=farm, status=Task.Status.COMPLETED, completed_at__date=today
            ).count(),
            "in_progress": open_tasks.filter(status=Task.Status.IN_PROGRESS).count(),
            "pending": open_tasks.filter(status__in=[Task.Status.ASSIGNED, Task.Status.ACCEPTED]).count(),
            "overdue": open_tasks.filter(due_at__lt=now).count(),
        },
        "attention": [
            {
                "type": "alert",
                "id": row.id,
                "title": row.alert_type.replace("_", " ").title(),
                "priority": row.severity,
                "subject": {
                    "type": "animal",
                    "id": row.animal_id,
                    "label": row.animal.tag_id if row.animal_id else None,
                },
                "available_actions": ["view_subject", "create_task"],
            }
            for row in alerts
        ],
        "upcoming": [
            serialize_task(task)
            for task in open_tasks.filter(due_at__date__gt=today).order_by("due_at")[:10]
        ],
        "team_work": team,
        "recent_activity": [serialize_event(event) for event in recent],
        "formulas": {
            "today.scheduled": "open tasks with due_at date = today",
            "today.completed": "tasks completed today",
            "active_animals": "lifecycle_status = active",
        },
    }
    return 200, success_body(data=data, message="Farm dashboard fetched successfully.")


@dash_router.get(
    "/my-work/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="My Work dashboard aggregate",
)
def my_work_dashboard(request, farm_id: int = None):
    user = require_user(request)
    org = resolve_organization(user)
    qs = Task.objects.filter(organization=org, assigned_to=user).select_related(
        "animal", "assigned_to", "created_by", "farm"
    )
    if farm_id is not None:
        farm = require_farm(org, farm_id, user)
        qs = qs.filter(farm=farm)
    open_qs = qs.exclude(
        status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED, Task.Status.UNABLE_TO_COMPLETE]
    )
    today = timezone.localdate()
    data = {
        "summary": work_summary_for(user, org),
        "today": [serialize_task(t) for t in open_qs.filter(due_at__date=today)[:20]],
        "overdue": [serialize_task(t) for t in open_qs.filter(due_at__lt=timezone.now())[:20]],
        "upcoming": [
            serialize_task(t)
            for t in open_qs.filter(due_at__date__gt=today).order_by("due_at")[:20]
        ],
    }
    return 200, success_body(data=data, message="My work dashboard fetched successfully.")


@dash_router.get(
    "/health/",
    response={200: V2Success, 401: V2Error, 403: V2Error},
    summary="Veterinarian / health workspace",
)
def health_dashboard(request, farm_id: int = None):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Health.VIEW)
    farm = require_farm(org, farm_id, user) if farm_id is not None else None
    cases = HealthCase.objects.filter(farm__organization=org, status=HealthCase.Status.OPEN)
    animals = Animal.objects.filter(farm__organization=org)
    tasks = Task.objects.filter(organization=org)
    if farm:
        cases = cases.filter(farm=farm)
        animals = animals.filter(farm=farm)
        tasks = tasks.filter(farm=farm)
    today = timezone.localdate()
    data = {
        "active_health_cases": cases.count(),
        "critical_cases": TreatmentRecord.objects.filter(
            farm__in=animals.values("farm"), severity="severe"
        ).count(),
        "new_observations": HealthObservation.objects.filter(
            farm__in=animals.values("farm"), observed_at__date=today
        ).count(),
        "treatments_due": tasks.filter(task_type=Task.Type.TREATMENT)
        .exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
        .count(),
        "followups_due": tasks.filter(parent__isnull=False, due_at__date__lte=today)
        .exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
        .count(),
        "vaccinations_due": tasks.filter(task_type=Task.Type.VACCINATION)
        .exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
        .count(),
        "quarantined_animals": animals.filter(is_quarantine=True).count(),
        "mortality_cases": MortalityRecord.objects.filter(farm__organization=org).count()
        if not farm
        else MortalityRecord.objects.filter(farm=farm).count(),
        "withdrawal_animals": animals.filter(is_quarantine=True).count(),
        "my_tasks": [serialize_task(t) for t in tasks.filter(assigned_to=user).exclude(
            status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED]
        )[:15]],
    }
    return 200, success_body(data=data, message="Health dashboard fetched successfully.")
