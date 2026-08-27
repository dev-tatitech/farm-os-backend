from django.utils import timezone
from ninja import Router

from animals.models import Animal
from common.permissions import Permissions
from operations.models import Task
from operations.services import serialize_task, work_summary_for
from organization.models import Farm

from .authz import require_farm, require_permission, require_user, resolve_organization
from .envelope import V2Error, V2Success, success_body

dash_router = Router(tags=["Dashboard"])


@dash_router.get(
    "/organization/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Organization home aggregate",
)
def org_dashboard(request):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Reports.LIVESTOCK_DASHBOARD, Permissions.Animal.VIEW)
    animals = Animal.objects.filter(farm__organization=org)
    farms = Farm.objects.filter(organization=org)
    open_tasks = Task.objects.filter(organization=org).exclude(
        status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED]
    )
    data = {
        "organization": {"id": str(org.id), "name": org.name, "status": org.status},
        "farms": farms.count(),
        "animals": {
            "total": animals.count(),
            "active": animals.filter(status="active").count(),
            "sold": animals.filter(status="sold").count(),
            "dead": animals.filter(status="dead").count(),
            "sick": animals.filter(health_status="sick").count(),
            "quarantine": animals.filter(is_quarantine=True).count(),
        },
        "tasks": {
            "open": open_tasks.count(),
            "overdue": open_tasks.filter(due_at__lt=timezone.now()).count(),
        },
        "my_work": work_summary_for(user, org),
        "farm_breakdown": [
            {
                "id": farm.id,
                "name": farm.name,
                "status": farm.status,
                "animal_count": Animal.objects.filter(farm=farm).count(),
            }
            for farm in farms
        ],
    }
    return 200, success_body(data=data, message="Organization dashboard fetched successfully.")


@dash_router.get(
    "/farm/{farm_id}/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Farm home aggregate",
)
def farm_dashboard(request, farm_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Reports.LIVESTOCK_DASHBOARD, Permissions.Animal.VIEW)
    farm = require_farm(org, farm_id, user)
    animals = Animal.objects.filter(farm=farm)
    open_tasks = Task.objects.filter(farm=farm).exclude(
        status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED]
    )
    data = {
        "farm": {"id": farm.id, "name": farm.name, "status": farm.status},
        "animals": {
            "total": animals.count(),
            "active": animals.filter(status="active").count(),
            "sold": animals.filter(status="sold").count(),
            "dead": animals.filter(status="dead").count(),
            "sick": animals.filter(health_status="sick").count(),
            "quarantine": animals.filter(is_quarantine=True).count(),
            "pregnant": animals.filter(is_pregnant=True).count(),
            "lactating": animals.filter(is_lactating=True).count(),
        },
        "tasks": {
            "open": open_tasks.count(),
            "overdue": open_tasks.filter(due_at__lt=timezone.now()).count(),
            "mine": open_tasks.filter(assigned_to=user).count(),
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
    open_qs = qs.exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
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
