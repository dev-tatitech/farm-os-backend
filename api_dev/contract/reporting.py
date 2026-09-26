"""D02-014 server-authoritative Operations reporting projections."""
from django.db.models import Count, Q
from django.utils import timezone
from ninja import Router

from common.access import authorized_farms
from animals.models import AnimalEvent
from operations.models import Task, TaskSchedule
from operations.services import serialize_event, serialize_task

from .authz import require_farm, require_permission, require_user, resolve_organization
from .envelope import V2Error, V2Success, success_body


reporting_router = Router(tags=["Operations reporting"])
TERMINAL = [Task.Status.COMPLETED, Task.Status.CANCELLED, Task.Status.UNABLE_TO_COMPLETE]


@reporting_router.get("/operations/overview/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error})
def operations_overview(request, farm_id: int = None, page: int = 1, page_size: int = 20):
    """Read-only, scope-first D02-014 operational control projection."""
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, "view_operation")
    farms = authorized_farms(user, org, "view_operation")
    farm = require_farm(org, farm_id, user) if farm_id is not None else None
    if farm:
        farms = farms.filter(pk=farm.pk)
    evaluation_time = timezone.now()
    tasks = Task.objects.filter(organization=org, farm__in=farms)
    counts = {row["status"]: row["count"] for row in tasks.values("status").annotate(count=Count("id"))}
    actionable = tasks.exclude(status__in=TERMINAL)
    overdue = actionable.filter(due_at__lt=evaluation_time)
    exceptions = tasks.filter(status=Task.Status.UNABLE_TO_COMPLETE)
    schedules = TaskSchedule.objects.filter(organization=org, farm__in=farms)
    workload = list(actionable.exclude(assigned_to=None).values("assigned_to_id").annotate(count=Count("id")).order_by("-count", "assigned_to_id"))
    event_qs = AnimalEvent.objects.filter(farm__in=farms).select_related("event_type", "animal", "farm", "created_by").order_by("-event_date", "-id")
    page = max(1, page or 1); page_size = min(100, max(1, page_size or 20))
    start = (page - 1) * page_size
    history = [serialize_event(event) for event in event_qs[start:start + page_size]]
    return 200, success_body(
        data={
            "task_status_summary": counts,
            "overdue": {"count": overdue.count(), "tasks": [serialize_task(task) for task in overdue.order_by("due_at")[:page_size]]},
            "operational_exceptions": {"count": exceptions.count(), "tasks": [serialize_task(task) for task in exceptions.order_by("-unable_to_complete_at")[:page_size]]},
            "workload_by_assignee": workload,
            "schedule_execution": {"active": schedules.filter(is_active=True).count(), "inactive": schedules.filter(is_active=False).count()},
            "task_history": history,
        },
        message="Operations reporting overview fetched successfully.",
        meta={"evaluation_time": evaluation_time.isoformat(), "farm_scope": farm.id if farm else "authorized", "history_page": page, "history_page_size": page_size},
    )
