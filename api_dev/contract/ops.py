from common.mutations import atomic_mutation
from common.access import authorized_farms
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Q
from zoneinfo import ZoneInfo
from ninja import Router

from common.permissions import Permissions
from operations.models import Task, TaskSchedule
from operations.services import (
    accept_task,
    assign_task,
    cancel_task,
    complete_task,
    create_task,
    emit_event,
    get_task,
    mark_unable_to_complete,
    reopen_task,
    reactivate_schedule,
    run_schedule,
    serialize_schedule,
    serialize_task,
    start_task,
    validate_schedule_template,
)
from animals.models import Animal, AnimalGroup, AnimalGroupMember
from account.models import User
from common.access import has_capability

from .authz import require_farm, require_permission, require_user, resolve_organization
from .codes import ErrorCode
from .envelope import V2Error, V2Success, success_body
from .exceptions import ContractError
from .helpers import begin_idempotency, paginated, store_idempotency
from .capabilities import build_capabilities, permission_codes_for_user
from .schemas import (
    ScheduleCreateIn,
    SchedulePatchIn,
    TaskAssignIn,
    TaskCancelIn,
    TaskCompleteIn,
    TaskCreateIn,
    TaskReopenIn,
    TaskUnableIn,
)

ops_router = Router(tags=["Operations"])


# This is deliberately metadata, not another TaskType table.  Task.Type and
# the existing completion handlers remain authoritative.
WORK_TYPE_METADATA = {
    Task.Type.VACCINATION: {"target_types": ("animal", "group"), "capabilities": (Permissions.Health.CREATE,), "recurring": True, "domain_completion": True, "inventory_effect": True},
    Task.Type.TREATMENT: {"target_types": ("animal",), "capabilities": (Permissions.Health.CREATE,), "recurring": True, "domain_completion": True, "inventory_effect": True},
    Task.Type.FEED_ISSUANCE: {"target_types": ("animal", "group"), "capabilities": (Permissions.Feed.CREATE,), "recurring": True, "domain_completion": True, "inventory_effect": True},
    Task.Type.MOVEMENT: {"target_types": ("animal", "group"), "capabilities": (Permissions.MovementRecord.CREATE,), "recurring": False, "domain_completion": True, "inventory_effect": False},
    Task.Type.OBSERVATION: {"target_types": ("animal",), "capabilities": ("record_health_observation",), "recurring": True, "domain_completion": True, "inventory_effect": False},
    Task.Type.WEIGHT: {"target_types": ("animal",), "capabilities": (Permissions.Animal.UPDATE,), "recurring": True, "domain_completion": True, "inventory_effect": False},
    Task.Type.PREGNANCY_CHECK: {"target_types": ("animal",), "capabilities": (Permissions.Reproduction.CREATE,), "recurring": True, "domain_completion": True, "inventory_effect": False},
    Task.Type.SALE: {"target_types": ("animal",), "capabilities": (Permissions.SalesRecord.CREATE,), "recurring": False, "domain_completion": True, "inventory_effect": False},
    Task.Type.MORTALITY: {"target_types": ("animal",), "capabilities": (Permissions.Health.CREATE,), "recurring": False, "domain_completion": True, "inventory_effect": False},
    Task.Type.GENERIC: {"target_types": (), "capabilities": (), "recurring": True, "domain_completion": False, "inventory_effect": False},
}


def eligible_assignee_rows(user, org, farm, meta, *, channel=None):
    """Shared current-authority resolver for web and JWT mobile surfaces."""
    candidates = User.objects.filter(account_status="active", is_active=True).filter(Q(organization=org) | Q(id=org.user_id)).distinct()
    rows = []
    for candidate in candidates:
        if not authorized_farms(candidate, org).filter(pk=farm.pk).exists():
            continue
        if channel == "mobile":
            from role.models import UserRole
            if not UserRole.objects.filter(user=candidate, farm=farm, status="active", role__active=True,
                                           role__mobile_access=True).exists():
                continue
        if has_capability(candidate, org, "complete_operation", farm=farm) and any(has_capability(candidate, org, cap, farm=farm) for cap in meta["capabilities"]):
            rows.append({"id": str(candidate.id), "display_name": candidate.get_full_name() or candidate.email})
    return rows


def _work_type_or_404(work_type):
    try:
        return WORK_TYPE_METADATA[work_type]
    except KeyError:
        raise ContractError(404, ErrorCode.RESOURCE_NOT_FOUND, "Work type could not be found.")


@ops_router.get("/work-types/", response={200: V2Success, 401: V2Error, 403: V2Error})
def work_types(request):
    user = require_user(request)
    org = resolve_organization(user)
    _require_cap(user, org, "view_operation")
    return 200, success_body(data=[{"code": code, **meta} for code, meta in WORK_TYPE_METADATA.items()], message="Work types fetched successfully.")


@ops_router.get("/work-types/{work_type}/eligible-targets/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error})
def eligible_targets(request, work_type: str, farm_id: int, target_type: str = "animal", search: str = None,
                     livestock_species_id: int = None, livestock_breed_id: int = None, gender: str = None,
                     group_id: int = None, housing_unit_id: int = None, health_status: str = None,
                     lifecycle_status: str = None, page: int = 1, page_size: int = 20):
    user = require_user(request)
    org = resolve_organization(user)
    _require_cap(user, org, "create_operation")
    meta = _work_type_or_404(work_type)
    farm = require_farm(org, farm_id, user)
    require_permission(user, org, Permissions.Animal.VIEW, farm=farm)
    if target_type not in meta["target_types"]:
        raise ContractError(422, ErrorCode.TARGET_NOT_ELIGIBLE, "This work type does not support the requested target type.")
    if target_type == "group":
        qs = AnimalGroup.objects.filter(farm=farm, status=AnimalGroup.Status.ACTIVE)
        if search:
            qs = qs.filter(name__icontains=search)
        return 200, paginated(qs.order_by("name", "id"), page, page_size, lambda row: {"id": row.id, "type": "group", "name": row.name, "farm_id": row.farm_id}, "Eligible targets fetched successfully.")
    qs = Animal.objects.filter(farm=farm, status="active").select_related("livestock_species", "livestock_breed", "housing_unit")
    if search:
        qs = qs.filter(Q(tag_id__icontains=search) | Q(notes__icontains=search))
    for field, value in (("livestock_species_id", livestock_species_id), ("livestock_breed_id", livestock_breed_id), ("gender", gender), ("housing_unit_id", housing_unit_id), ("health_status", health_status), ("status", lifecycle_status)):
        if value is not None:
            qs = qs.filter(**{field: value})
    if group_id is not None:
        qs = qs.filter(group_memberships__group_id=group_id, group_memberships__status=AnimalGroupMember.Status.ACTIVE)
    return 200, paginated(qs.distinct().order_by("tag_id", "id"), page, page_size, lambda row: {"id": row.id, "type": "animal", "tag_id": row.tag_id, "farm_id": row.farm_id}, "Eligible targets fetched successfully.")


@ops_router.get("/work-types/{work_type}/eligible-assignees/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error})
def eligible_assignees(request, work_type: str, farm_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    _require_cap(user, org, "assign_operation")
    meta = _work_type_or_404(work_type)
    farm = require_farm(org, farm_id, user)
    return 200, success_body(data=eligible_assignee_rows(user, org, farm, meta), message="Eligible assignees fetched successfully.")


def _task_perm(user, org, *codes):
    require_permission(user, org, *codes)


def _caps(user, org):
    return build_capabilities(user, org, permission_codes_for_user(user, org))["capabilities"]


def _require_cap(user, org, name: str, farm=None):
    require_permission(user, org, name, farm=farm)


def _domain_complete_perm(task):
    mapping = {
        Task.Type.VACCINATION: (Permissions.Health.CREATE,),
        Task.Type.TREATMENT: (Permissions.Health.CREATE,),
        Task.Type.OBSERVATION: ("record_health_observation",),
        Task.Type.MORTALITY: (Permissions.Health.CREATE,),
        Task.Type.WEIGHT: (Permissions.Animal.UPDATE, Permissions.Animal.CREATE),
        Task.Type.PREGNANCY_CHECK: (Permissions.Reproduction.CREATE,),
        Task.Type.FEED_ISSUANCE: (Permissions.Feed.CREATE,),
        Task.Type.SALE: (Permissions.SalesRecord.CREATE,),
        Task.Type.MOVEMENT: (Permissions.MovementRecord.CREATE,),
        Task.Type.GENERIC: (Permissions.Animal.CREATE, Permissions.Farm.UPDATE),
    }
    return mapping.get(task.task_type, (Permissions.Animal.CREATE,))


def _open_qs(org, user, farm_id=None):
    qs = Task.objects.filter(farm__in=authorized_farms(user, org)).select_related(
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
@atomic_mutation
def create_operations_task(request, payload: TaskCreateIn):
    user = require_user(request)
    org = resolve_organization(user)
    _require_cap(user, org, "create_operation")
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
    _require_cap(user, org, "view_operation")
    qs = _open_qs(org, user, farm_id)
    if assigned_to_me:
        qs = qs.filter(assigned_to=user)
    if task_type:
        qs = qs.filter(task_type=task_type)
    if status == "open":
        qs = qs.exclude(
            status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED, Task.Status.UNABLE_TO_COMPLETE]
        )
    elif status == "overdue":
        qs = qs.exclude(
            status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED, Task.Status.UNABLE_TO_COMPLETE]
        ).filter(due_at__lt=timezone.now())
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
    task = get_task(org, task_id)
    require_farm(org, task.farm_id, user)
    # A directly assigned task is visible to its assignee even when the
    # assignee's role does not include broad operation-list capability. Farm
    # scope is still enforced below.
    if task.assigned_to_id != user.id:
        _require_cap(user, org, "view_operation")
    return 200, success_body(data=serialize_task(task), message="Task fetched successfully.")


@ops_router.post(
    "/tasks/{task_id}/assign/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error},
    summary="Assign or reassign a task",
)
@atomic_mutation
def task_assign(request, task_id: int, payload: TaskAssignIn):
    user = require_user(request)
    org = resolve_organization(user)
    task = get_task(org, task_id)
    require_farm(org, task.farm_id, user)
    _require_cap(user, org, "reassign_operation" if task.assigned_to_id else "assign_operation", farm=task.farm)
    task = assign_task(task, user, payload.assignee_id)
    return 200, success_body(data=serialize_task(task), message="Task assigned successfully.")


@ops_router.post(
    "/tasks/{task_id}/accept/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error},
    summary="Accept an assigned task",
)
@atomic_mutation
def task_accept(request, task_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    task = get_task(org, task_id)
    require_farm(org, task.farm_id, user)
    _require_cap(user, org, "complete_operation", farm=task.farm)
    task = accept_task(task, user)
    return 200, success_body(data=serialize_task(task), message="Task accepted successfully.")


@ops_router.post(
    "/tasks/{task_id}/start/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error},
    summary="Start a task",
)
@atomic_mutation
def task_start(request, task_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    task = get_task(org, task_id)
    require_farm(org, task.farm_id, user)
    _require_cap(user, org, "complete_operation", farm=task.farm)
    task = start_task(task, user)
    return 200, success_body(data=serialize_task(task), message="Task started successfully.")


@ops_router.post(
    "/tasks/{task_id}/complete/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error, 422: V2Error},
    summary="Complete a task and write the domain record",
)
@atomic_mutation
def task_complete(request, task_id: int, payload: TaskCompleteIn):
    user = require_user(request)
    org = resolve_organization(user)
    key, cached = begin_idempotency(user, request, payload)
    if cached:
        return cached
    task = get_task(org, task_id)
    require_farm(org, task.farm_id, user)
    _require_cap(user, org, "complete_operation", farm=task.farm)
    require_permission(user, org, *_domain_complete_perm(task), farm=task.farm)
    task = complete_task(task, user, _payload_dict(payload), evidence=payload.evidence or "")
    body = success_body(data=serialize_task(task), message="Task completed successfully.")
    store_idempotency(user, key, 200, body)
    return 200, body


@ops_router.post(
    "/tasks/{task_id}/cancel/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error},
    summary="Cancel a task",
)
@atomic_mutation
def task_cancel(request, task_id: int, payload: TaskCancelIn):
    user = require_user(request)
    org = resolve_organization(user)
    task = get_task(org, task_id)
    require_farm(org, task.farm_id, user)
    _require_cap(user, org, "cancel_operation", farm=task.farm)
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
    _require_cap(user, org, "view_operation")
    qs = _open_qs(org, user, farm_id).filter(assigned_to=user).exclude(
        status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED, Task.Status.UNABLE_TO_COMPLETE]
    )
    return 200, paginated(
        qs.order_by("due_at", "-priority"), page, page_size, serialize_task, "My work fetched successfully."
    )


@ops_router.get(
    "/exceptions/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Server-scoped operational exceptions queue",
)
def operational_exceptions(request, page: int = 1, page_size: int = 20, farm_id: int = None, reason_code: str = None):
    """Management view over unable-to-complete tasks; not a separate task type."""
    user = require_user(request)
    org = resolve_organization(user)
    _require_cap(user, org, "view_operation")
    qs = _open_qs(org, user, farm_id).filter(status=Task.Status.UNABLE_TO_COMPLETE)
    if reason_code:
        qs = qs.filter(unable_reason_code=reason_code)
    return 200, paginated(
        qs.order_by("-unable_to_complete_at", "-id"), page, page_size, serialize_task,
        "Operational exceptions fetched successfully.",
    )


@ops_router.get(
    "/today/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Tasks due today",
)
def today_work(request, page: int = 1, page_size: int = 20, farm_id: int = None):
    user = require_user(request)
    org = resolve_organization(user)
    _require_cap(user, org, "view_operation")
    today = timezone.localdate()
    qs = (
        _open_qs(org, user, farm_id)
        .filter(assigned_to=user, due_at__date=today)
        .exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED, Task.Status.UNABLE_TO_COMPLETE])
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
    _require_cap(user, org, "view_operation")
    qs = (
        _open_qs(org, user, farm_id)
        .filter(assigned_to=user, due_at__lt=timezone.now())
        .exclude(
            status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED, Task.Status.UNABLE_TO_COMPLETE]
        )
    )
    return 200, paginated(qs, page, page_size, serialize_task, "Overdue work fetched successfully.")


@ops_router.get(
    "/dashboard/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Authorized operational progress dashboard",
)
def operations_dashboard(request, farm_id: int = None):
    """D02-009 server-authoritative, side-effect-free operational metrics."""
    user = require_user(request)
    org = resolve_organization(user)
    _require_cap(user, org, "view_operation")
    farm = require_farm(org, farm_id, user) if farm_id is not None else None
    farms = authorized_farms(user, org)
    if farm is not None:
        farms = farms.filter(pk=farm.pk)
    # Users without management capability retain the D02-008 personal scope.
    from common.access import has_capability
    personal = not (has_capability(user, org, "assign_operation", farm=farm) or has_capability(user, org, "reassign_operation", farm=farm))
    qs = Task.objects.filter(organization=org, farm__in=farms)
    if personal:
        qs = qs.filter(assigned_to=user)
    now = timezone.now()
    lagos = ZoneInfo("Africa/Lagos")
    next_day = now.astimezone(lagos).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    # D02-009 uses the existing executable lifecycle population.  A draft is
    # non-terminal, but is not actionable until it is assigned.
    actionable = Q(status__in=[Task.Status.ASSIGNED, Task.Status.ACCEPTED, Task.Status.IN_PROGRESS])
    counts = qs.aggregate(
        completed=Count("id", filter=Q(status=Task.Status.COMPLETED)),
        actionable=Count("id", filter=actionable),
        due_today=Count("id", filter=actionable & Q(due_at__gte=now, due_at__lt=next_day)),
        overdue=Count("id", filter=actionable & Q(due_at__lt=now)),
    )
    completed, actionable_count = counts["completed"], counts["actionable"]
    total = completed + actionable_count
    percentage = round((completed / total * 100) if total else 0, 2)
    data = {**counts, "completion_percentage": percentage, "team_progress": {"completed": completed, "total": total, "percentage": percentage}}
    return 200, success_body(data=data, message="Operational dashboard fetched successfully.", meta={"evaluation_time": now.astimezone(lagos).isoformat(), "timezone": "Africa/Lagos", "farm_scope": farm.id if farm else "authorized", "personal_scope": personal})


@ops_router.get(
    "/schedules/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Task schedules",
)
def list_schedules(request, page: int = 1, page_size: int = 20, farm_id: int = None):
    user = require_user(request)
    org = resolve_organization(user)
    _require_cap(user, org, "view_operation")
    qs = TaskSchedule.objects.filter(farm__in=authorized_farms(user, org))
    if farm_id is not None:
        farm = require_farm(org, farm_id, user)
        qs = qs.filter(farm=farm)
    return 200, paginated(qs, page, page_size, serialize_schedule, "Schedules fetched successfully.")


@ops_router.post(
    "/schedules/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 422: V2Error},
    summary="Create a task schedule",
)
@atomic_mutation
def create_schedule(request, payload: ScheduleCreateIn):
    user = require_user(request)
    org = resolve_organization(user)
    _require_cap(user, org, "create_operation")
    farm = require_farm(org, payload.farm_id, user)
    if payload.recurrence not in TaskSchedule.Recurrence.values:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Invalid recurrence.")
    if not payload.title.strip():
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "title is required.")
    if payload.priority not in Task.Priority.values:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Invalid schedule priority.")
    starts_at = payload.starts_at or payload.next_run_at
    if payload.ends_at and payload.ends_at < starts_at:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "ends_at must be on or after starts_at.")
    if payload.next_run_at < starts_at or (payload.ends_at and payload.next_run_at > payload.ends_at):
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "next_run_at must be inside the schedule window.")
    animal, group, assignee = validate_schedule_template(
        org=org,
        farm=farm,
        task_type=payload.task_type,
        animal_id=payload.animal_id,
        group_id=payload.group_id,
        assignee_id=payload.assignee_id,
    )
    schedule = TaskSchedule.objects.create(
        organization=org,
        farm=farm,
        animal=animal,
        group=group,
        task_type=payload.task_type,
        title=payload.title,
        description=payload.description or "",
        recurrence=payload.recurrence,
        starts_at=starts_at,
        ends_at=payload.ends_at,
        priority=payload.priority,
        next_run_at=payload.next_run_at,
        assignee=assignee,
        template_payload=payload.template_payload or {},
        created_by=user,
    )
    emit_event(
        farm, "schedule_created", f"Schedule created — {schedule.title}", schedule.description,
        "task_schedule", schedule.id, user, animal=animal, group=group,
        metadata={"recurrence": schedule.recurrence, "starts_at": schedule.starts_at.isoformat(), "ends_at": schedule.ends_at.isoformat() if schedule.ends_at else None, "priority": schedule.priority, "next_run_at": schedule.next_run_at.isoformat()},
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
@atomic_mutation
def run_schedule_endpoint(request, schedule_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    try:
        schedule = TaskSchedule.objects.get(id=schedule_id, organization=org)
    except TaskSchedule.DoesNotExist:
        raise ContractError(404, ErrorCode.SCHEDULE_NOT_FOUND, "Schedule could not be found.")
    require_farm(org, schedule.farm_id, user)
    _require_cap(user, org, "create_operation", farm=schedule.farm)
    task = run_schedule(schedule, user)
    return 200, success_body(data=serialize_task(task), message="Schedule run successfully.")


@ops_router.post(
    "/tasks/{task_id}/unable-to-complete/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error, 422: V2Error},
    summary="Mark a task unable to complete",
)
@atomic_mutation
def task_unable(request, task_id: int, payload: TaskUnableIn):
    user = require_user(request)
    org = resolve_organization(user)
    key, cached = begin_idempotency(user, request, payload)
    if cached:
        return cached
    task = get_task(org, task_id)
    require_farm(org, task.farm_id, user)
    _require_cap(user, org, "complete_operation", farm=task.farm)
    task = mark_unable_to_complete(task, user, payload.dict())
    body = success_body(data=serialize_task(task), message="Unable-to-complete recorded.")
    store_idempotency(user, key, 200, body)
    return 200, body


@ops_router.post(
    "/tasks/{task_id}/reopen/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error},
    summary="Reopen or reschedule unable work",
)
@atomic_mutation
def task_reopen(request, task_id: int, payload: TaskReopenIn):
    user = require_user(request)
    org = resolve_organization(user)
    task = get_task(org, task_id)
    require_farm(org, task.farm_id, user)
    _require_cap(user, org, "assign_operation", farm=task.farm)
    task = reopen_task(task, user, payload.dict())
    return 200, success_body(data=serialize_task(task), message="Task reopened successfully.")


@ops_router.get(
    "/schedules/{schedule_id}/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Schedule detail",
)
def schedule_detail(request, schedule_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    try:
        schedule = TaskSchedule.objects.get(id=schedule_id, organization=org)
    except TaskSchedule.DoesNotExist:
        raise ContractError(404, ErrorCode.SCHEDULE_NOT_FOUND, "Schedule could not be found.")
    require_farm(org, schedule.farm_id, user)
    _require_cap(user, org, "view_operation", farm=schedule.farm)
    return 200, success_body(data=serialize_schedule(schedule), message="Schedule fetched successfully.")


@ops_router.patch(
    "/schedules/{schedule_id}/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 422: V2Error},
    summary="Update a schedule",
)
@atomic_mutation
def schedule_patch(request, schedule_id: int, payload: SchedulePatchIn):
    user = require_user(request)
    org = resolve_organization(user)
    try:
        schedule = TaskSchedule.objects.get(id=schedule_id, organization=org)
    except TaskSchedule.DoesNotExist:
        raise ContractError(404, ErrorCode.SCHEDULE_NOT_FOUND, "Schedule could not be found.")
    require_farm(org, schedule.farm_id, user)
    _require_cap(user, org, "create_operation", farm=schedule.farm)
    before = {
        "title": schedule.title, "description": schedule.description, "recurrence": schedule.recurrence,
        "next_run_at": schedule.next_run_at.isoformat(), "assignee_id": str(schedule.assignee_id) if schedule.assignee_id else None,
        "animal_id": schedule.animal_id, "group_id": schedule.group_id, "is_active": schedule.is_active,
        "starts_at": schedule.starts_at.isoformat() if schedule.starts_at else None,
        "ends_at": schedule.ends_at.isoformat() if schedule.ends_at else None,
        "priority": schedule.priority,
    }
    if payload.title is not None:
        schedule.title = payload.title
    if payload.description is not None:
        schedule.description = payload.description
    if payload.recurrence:
        if payload.recurrence not in TaskSchedule.Recurrence.values:
            raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Invalid recurrence.")
        schedule.recurrence = payload.recurrence
    if payload.next_run_at:
        schedule.next_run_at = payload.next_run_at
    if "starts_at" in payload.__fields_set__:
        schedule.starts_at = payload.starts_at
    if "ends_at" in payload.__fields_set__:
        schedule.ends_at = payload.ends_at
    if payload.priority is not None:
        if payload.priority not in Task.Priority.values:
            raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Invalid schedule priority.")
        schedule.priority = payload.priority
    if payload.assignee_id is not None:
        schedule.assignee_id = payload.assignee_id
    if payload.animal_id is not None:
        schedule.animal_id = payload.animal_id
    if payload.group_id is not None:
        schedule.group_id = payload.group_id
    reactivating = payload.is_active is True and not schedule.is_active
    if payload.is_active is not None and not reactivating:
        schedule.is_active = payload.is_active
    if schedule.ends_at and schedule.ends_at < timezone.now():
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "ends_at must be in the future when a schedule is active.")
    # Subject and assignee mutations are validated against the same farm and
    # execution rules as a new schedule.  Existing tasks remain untouched.
    validate_schedule_template(
        org=org,
        farm=schedule.farm,
        task_type=schedule.task_type,
        animal_id=schedule.animal_id,
        group_id=schedule.group_id,
        assignee_id=schedule.assignee_id,
    )
    effective_start = schedule.starts_at or schedule.next_run_at
    if schedule.ends_at and schedule.ends_at < effective_start:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "ends_at must be on or after starts_at.")
    if schedule.next_run_at < effective_start or (schedule.ends_at and schedule.next_run_at > schedule.ends_at):
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "next_run_at must be inside the schedule window.")
    schedule.save()
    after = {
        "title": schedule.title, "description": schedule.description, "recurrence": schedule.recurrence,
        "next_run_at": schedule.next_run_at.isoformat(), "assignee_id": str(schedule.assignee_id) if schedule.assignee_id else None,
        "animal_id": schedule.animal_id, "group_id": schedule.group_id, "is_active": schedule.is_active,
        "starts_at": schedule.starts_at.isoformat() if schedule.starts_at else None,
        "ends_at": schedule.ends_at.isoformat() if schedule.ends_at else None,
        "priority": schedule.priority,
    }
    changeset = {key: {"before": before[key], "after": after[key]} for key in before if before[key] != after[key]}
    if changeset:
        emit_event(
            schedule.farm, "schedule_updated", f"Schedule updated — {schedule.title}", "Material schedule fields changed.",
            "task_schedule", schedule.id, user, animal=schedule.animal, group=schedule.group,
            changeset=changeset,
        )
    generated = reactivate_schedule(schedule, user) if reactivating else None
    schedule.refresh_from_db()
    data = serialize_schedule(schedule)
    if generated:
        data["generated_task"] = serialize_task(generated)
    return 200, success_body(data=data, message="Schedule updated successfully.")


@ops_router.post(
    "/schedules/{schedule_id}/deactivate/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Deactivate a schedule without deleting history",
)
@atomic_mutation
def schedule_deactivate(request, schedule_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    try:
        schedule = TaskSchedule.objects.get(id=schedule_id, organization=org)
    except TaskSchedule.DoesNotExist:
        raise ContractError(404, ErrorCode.SCHEDULE_NOT_FOUND, "Schedule could not be found.")
    require_farm(org, schedule.farm_id, user)
    _require_cap(user, org, "create_operation", farm=schedule.farm)
    schedule.is_active = False
    schedule.save(update_fields=["is_active", "updated_at"])
    emit_event(
        schedule.farm, "schedule_deactivated", f"Schedule deactivated — {schedule.title}", "Schedule deactivated by user.",
        "task_schedule", schedule.id, user, animal=schedule.animal, group=schedule.group,
    )
    return 200, success_body(data=serialize_schedule(schedule), message="Schedule deactivated successfully.")
