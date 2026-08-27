from django.utils import timezone
from ninja import Router

from common.permissions import Permissions
from operations.models import Task, TaskSchedule
from operations.services import (
    accept_task,
    assign_task,
    cancel_task,
    complete_task,
    create_task,
    get_task,
    run_schedule,
    serialize_schedule,
    serialize_task,
    start_task,
)

from .authz import require_farm, require_permission, require_user, resolve_organization
from .codes import ErrorCode
from .envelope import V2Error, V2Success, success_body
from .exceptions import ContractError
from .helpers import begin_idempotency, paginated, store_idempotency
from .schemas import ScheduleCreateIn, TaskAssignIn, TaskCancelIn, TaskCompleteIn, TaskCreateIn

ops_router = Router(tags=["Operations"])


def _task_perm(user, org, *codes):
    require_permission(user, org, *codes)


def _open_qs(org, user, farm_id=None):
    qs = Task.objects.filter(organization=org).select_related(
        "animal", "assigned_to", "created_by", "farm", "group"
    )
    if farm_id is not None:
        farm = require_farm(org, farm_id, user)
        qs = qs.filter(farm=farm)
    return qs


def _payload_dict(payload: TaskCompleteIn) -> dict:
    raw = payload.dict(exclude_none=True)
    nested = raw.pop("payload", None) or {}
    raw.pop("client_request_id", None)
    raw.pop("evidence", None)
    if isinstance(nested, dict):
        nested.update(raw)
        return nested
    return raw


@ops_router.post(
    "/tasks/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 422: V2Error},
    summary="Create an operations task",
)
def create_operations_task(request, payload: TaskCreateIn):
    user = require_user(request)
    org = resolve_organization(user)
    _task_perm(user, org, Permissions.Health.CREATE, Permissions.Feed.CREATE, Permissions.Animal.CREATE)
    key, cached = begin_idempotency(user, request, payload)
    if cached:
        return cached
    farm = require_farm(org, payload.farm_id, user)
    task = create_task(
        org=org,
        farm=farm,
        user=user,
        task_type=payload.task_type,
        title=payload.title,
        description=payload.description,
        animal_id=payload.animal_id,
        group_id=payload.group_id,
        due_at=payload.due_at,
        priority=payload.priority,
        assignee_id=payload.assignee_id,
    )
    body = success_body(data=serialize_task(task), message="Task created successfully.")
    store_idempotency(user, key, 200, body)
    return 200, body


@ops_router.get(
    "/tasks/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="List operations tasks",
)
def list_tasks(
    request,
    page: int = 1,
    page_size: int = 20,
    farm_id: int = None,
    status: str = None,
    task_type: str = None,
    assigned_to_me: bool = False,
):
    user = require_user(request)
    org = resolve_organization(user)
    _task_perm(user, org, Permissions.Health.VIEW, Permissions.Feed.VIEW, Permissions.Animal.VIEW)
    qs = _open_qs(org, user, farm_id)
    if assigned_to_me:
        qs = qs.filter(assigned_to=user)
    if task_type:
        qs = qs.filter(task_type=task_type)
    if status == "open":
        qs = qs.exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
    elif status == "overdue":
        qs = qs.exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED]).filter(
            due_at__lt=timezone.now()
        )
    elif status:
        qs = qs.filter(status=status)
    return 200, paginated(qs.order_by("due_at", "-id"), page, page_size, serialize_task, "Tasks fetched successfully.")


@ops_router.get(
    "/tasks/{task_id}/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Task detail",
)
def task_detail(request, task_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    _task_perm(user, org, Permissions.Health.VIEW, Permissions.Feed.VIEW, Permissions.Animal.VIEW)
    task = get_task(org, task_id)
    require_farm(org, task.farm_id, user)
    return 200, success_body(data=serialize_task(task), message="Task fetched successfully.")


@ops_router.post(
    "/tasks/{task_id}/assign/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error},
    summary="Assign or reassign a task",
)
def task_assign(request, task_id: int, payload: TaskAssignIn):
    user = require_user(request)
    org = resolve_organization(user)
    _task_perm(user, org, Permissions.Farm.UPDATE)
    task = get_task(org, task_id)
    require_farm(org, task.farm_id, user)
    task = assign_task(task, user, payload.assignee_id)
    return 200, success_body(data=serialize_task(task), message="Task assigned successfully.")


@ops_router.post(
    "/tasks/{task_id}/accept/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error},
    summary="Accept an assigned task",
)
def task_accept(request, task_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    task = get_task(org, task_id)
    require_farm(org, task.farm_id, user)
    task = accept_task(task, user)
    return 200, success_body(data=serialize_task(task), message="Task accepted successfully.")


@ops_router.post(
    "/tasks/{task_id}/start/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error},
    summary="Start a task",
)
def task_start(request, task_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    task = get_task(org, task_id)
    require_farm(org, task.farm_id, user)
    task = start_task(task, user)
    return 200, success_body(data=serialize_task(task), message="Task started successfully.")


@ops_router.post(
    "/tasks/{task_id}/complete/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error, 422: V2Error},
    summary="Complete a task and write the domain record",
)
def task_complete(request, task_id: int, payload: TaskCompleteIn):
    user = require_user(request)
    org = resolve_organization(user)
    _task_perm(
        user,
        org,
        Permissions.Health.CREATE,
        Permissions.Feed.CREATE,
        Permissions.SalesRecord.CREATE,
        Permissions.MovementRecord.CREATE,
    )
    key, cached = begin_idempotency(user, request, payload)
    if cached:
        return cached
    task = get_task(org, task_id)
    require_farm(org, task.farm_id, user)
    task = complete_task(task, user, _payload_dict(payload), evidence=payload.evidence or "")
    body = success_body(data=serialize_task(task), message="Task completed successfully.")
    store_idempotency(user, key, 200, body)
    return 200, body


@ops_router.post(
    "/tasks/{task_id}/cancel/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error},
    summary="Cancel a task",
)
def task_cancel(request, task_id: int, payload: TaskCancelIn):
    user = require_user(request)
    org = resolve_organization(user)
    _task_perm(user, org, Permissions.Farm.UPDATE)
    task = get_task(org, task_id)
    require_farm(org, task.farm_id, user)
    task = cancel_task(task, user, payload.reason)
    return 200, success_body(data=serialize_task(task), message="Task cancelled successfully.")


@ops_router.get(
    "/my-work/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="My Work inbox",
)
def my_work(request, page: int = 1, page_size: int = 20, farm_id: int = None):
    user = require_user(request)
    org = resolve_organization(user)
    qs = _open_qs(org, user, farm_id).filter(assigned_to=user).exclude(
        status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED]
    )
    return 200, paginated(
        qs.order_by("due_at", "-priority"), page, page_size, serialize_task, "My work fetched successfully."
    )


@ops_router.get(
    "/today/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Tasks due today",
)
def today_work(request, page: int = 1, page_size: int = 20, farm_id: int = None):
    user = require_user(request)
    org = resolve_organization(user)
    today = timezone.localdate()
    qs = (
        _open_qs(org, user, farm_id)
        .filter(assigned_to=user, due_at__date=today)
        .exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
    )
    return 200, paginated(qs, page, page_size, serialize_task, "Today's work fetched successfully.")


@ops_router.get(
    "/overdue/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Overdue tasks",
)
def overdue_work(request, page: int = 1, page_size: int = 20, farm_id: int = None):
    user = require_user(request)
    org = resolve_organization(user)
    qs = (
        _open_qs(org, user, farm_id)
        .filter(assigned_to=user, due_at__lt=timezone.now())
        .exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
    )
    return 200, paginated(qs, page, page_size, serialize_task, "Overdue work fetched successfully.")


@ops_router.get(
    "/schedules/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Task schedules",
)
def list_schedules(request, page: int = 1, page_size: int = 20, farm_id: int = None):
    user = require_user(request)
    org = resolve_organization(user)
    _task_perm(user, org, Permissions.Health.VIEW, Permissions.Feed.VIEW)
    qs = TaskSchedule.objects.filter(organization=org)
    if farm_id is not None:
        farm = require_farm(org, farm_id, user)
        qs = qs.filter(farm=farm)
    return 200, paginated(qs, page, page_size, serialize_schedule, "Schedules fetched successfully.")


@ops_router.post(
    "/schedules/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 422: V2Error},
    summary="Create a task schedule",
)
def create_schedule(request, payload: ScheduleCreateIn):
    user = require_user(request)
    org = resolve_organization(user)
    _task_perm(user, org, Permissions.Health.CREATE, Permissions.Feed.CREATE)
    farm = require_farm(org, payload.farm_id, user)
    if payload.recurrence not in TaskSchedule.Recurrence.values:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Invalid recurrence.")
    schedule = TaskSchedule.objects.create(
        organization=org,
        farm=farm,
        animal_id=payload.animal_id,
        group_id=payload.group_id,
        task_type=payload.task_type,
        title=payload.title,
        description=payload.description or "",
        recurrence=payload.recurrence,
        next_run_at=payload.next_run_at,
        assignee_id=payload.assignee_id,
        template_payload=payload.template_payload or {},
        created_by=user,
    )
    data = serialize_schedule(schedule)
    if payload.run_now:
        task = run_schedule(schedule, user)
        data["generated_task"] = serialize_task(task)
    return 200, success_body(data=data, message="Schedule created successfully.")


@ops_router.post(
    "/schedules/{schedule_id}/run/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error},
    summary="Generate a task from a schedule",
)
def run_schedule_endpoint(request, schedule_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    _task_perm(user, org, Permissions.Health.CREATE, Permissions.Feed.CREATE)
    try:
        schedule = TaskSchedule.objects.get(id=schedule_id, organization=org)
    except TaskSchedule.DoesNotExist:
        raise ContractError(404, ErrorCode.SCHEDULE_NOT_FOUND, "Schedule could not be found.")
    require_farm(org, schedule.farm_id, user)
    task = run_schedule(schedule, user)
    return 200, success_body(data=serialize_task(task), message="Schedule run successfully.")
