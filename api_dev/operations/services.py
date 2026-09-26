import calendar
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from animals.event import new_event
from animals.models import Animal, AnimalEvent, AnimalGroup, AnimalWeight
from common.access import authorized_farms
from contract.authz import is_organization_owner
from contract.codes import ErrorCode
from contract.exceptions import ContractError
from feed.models import FeedBatch, FeedInventory, FeedIssuanceRecord
from health.models import HealthCase, HealthObservation, MortalityRecord, TreatmentRecord, VaccinationRecord
from movement_records.models import MovementRecord, SalesRecord
from movement_records.sale_readiness import evaluate_sale_readiness
from organization.models import Farm, Organization
from reproduction.models import PregnancyRecord
from pharmacy.models import Drug, DrugBatch

from .models import Notification, Task, TaskAssignment, TaskEvidence, TaskSchedule


OPEN_STATUSES = (
    Task.Status.DRAFT,
    Task.Status.ASSIGNED,
    Task.Status.ACCEPTED,
    Task.Status.IN_PROGRESS,
)

# Product decision D02-007: scheduling is calculated against the FarmOS MVP
# operational timezone. Persisted Django timestamps remain offset-aware/UTC.
SCHEDULE_TIMEZONE = ZoneInfo("Africa/Lagos")

# Storage references retain their concrete model/table names.  The public v2
# task result contract exposes the canonical completion vocabulary instead.
RESULT_TYPE_BY_REFERENCE = {
    "vaccination_record": Task.Type.VACCINATION,
    "treatment_record": Task.Type.TREATMENT,
    "feed_issuance_record": Task.Type.FEED_ISSUANCE,
    "sales_record": Task.Type.SALE,
    "movement_record": Task.Type.MOVEMENT,
    "health_observation": Task.Type.OBSERVATION,
    "animal_weight": Task.Type.WEIGHT,
    "pregnancy_record": Task.Type.PREGNANCY_CHECK,
    "mortality_record": Task.Type.MORTALITY,
}

RESULT_EVENT_REFERENCE_TABLE = {
    "vaccination_record": "vaccination", "treatment_record": "treatment",
    "feed_issuance_record": "feed_issuance", "sales_record": "sale",
    "movement_record": "movement", "health_observation": "health_observation",
    "animal_weight": "weight", "pregnancy_record": "pregnancy",
    "mortality_record": "mortality",
}


def public_result_type(reference_table: str) -> str:
    return RESULT_TYPE_BY_REFERENCE.get(reference_table, reference_table)


def json_value(value: Any):
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if hasattr(value, "hex"):
        return str(value)
    return value


def as_datetime(value):
    if value is None:
        return timezone.now()
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            return timezone.make_aware(value)
        return value
    if isinstance(value, date):
        return timezone.make_aware(datetime.combine(value, datetime.min.time()))
    return timezone.now()


def emit_event(
    farm,
    event_type: str,
    title: str,
    summary: str,
    reference_table: str,
    reference_id: int,
    created_by,
    animal=None,
    group=None,
    event_date=None,
    *,
    metadata=None,
    changeset=None,
    correlation_id=None,
):
    return new_event(
        farm,
        animal,
        event_type,
        as_datetime(event_date),
        title,
        summary or "",
        reference_table,
        reference_id,
        created_by,
        group=group,
        metadata=metadata,
        changeset=changeset,
        correlation_id=correlation_id,
    )


def notify(
    user,
    organization,
    title: str,
    body: str = "",
    farm=None,
    category: str = Notification.Category.TASK,
    reference_table: str = "",
    reference_id: int = None,
    notification_type: str = "system",
):
    if user is None:
        return None
    return Notification.objects.create(
        user=user,
        organization=organization,
        farm=farm,
        category=category,
        title=title,
        body=body,
        reference_table=reference_table,
        reference_id=reference_id,
        notification_type=notification_type,
    )


def notify_farm_management(org, farm, *, title, body, reference_table, reference_id, notification_type):
    """Notify current farm-management recipients, never every org member.

    D02-012 treats an unable-to-complete report as a management-attention
    notification.  Current assignment/capability is evaluated at delivery;
    ownership alone is not an implicit subscription.
    """
    from role.models import UserRole
    from common.access import has_capability

    rows = UserRole.objects.filter(
        farm=farm, status="active", role__active=True,
        user__is_active=True, user__account_status="active",
    ).select_related("user")
    recipients = {row.user for row in rows if has_capability(row.user, org, "assign_operation", farm=farm)}
    for recipient in recipients:
        notify(
            recipient, org, title=title, body=body, farm=farm,
            reference_table=reference_table, reference_id=reference_id,
            notification_type=notification_type,
        )


def serialize_task(task: Task) -> dict:
    from contract.identity import actor_payload, display_name, reference_payload, subject_payload

    overdue = bool(task.is_open and task.due_at and task.due_at < timezone.now())
    source_id = task.source_id or (task.schedule_id if task.source_type == Task.SourceType.SCHEDULE else None)
    return {
        "id": task.id,
        "farm_id": task.farm_id,
        "organization_id": str(task.organization_id),
        "animal_id": task.animal_id,
        "animal_tag": task.animal.tag_id if task.animal_id else None,
        "group_id": task.group_id,
        "parent_id": task.parent_id,
        "task_type": task.task_type,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "is_overdue": overdue,
        "priority": task.priority,
        "due_at": json_value(task.due_at),
        "assigned_to": str(task.assigned_to_id) if task.assigned_to_id else None,
        "assigned_to_email": task.assigned_to.email if task.assigned_to_id else None,
        "assignee": {
            "id": str(task.assigned_to_id),
            "display_name": display_name(task.assigned_to),
        }
        if task.assigned_to_id
        else None,
        "created_by": str(task.created_by_id) if task.created_by_id else None,
        "actor": actor_payload(task.created_by, task.organization),
        "accepted_at": json_value(task.accepted_at),
        "started_at": json_value(task.started_at),
        "completed_at": json_value(task.completed_at),
        "cancelled_at": json_value(task.cancelled_at),
        "unable_to_complete_at": json_value(task.unable_to_complete_at),
        "unable_reason_code": task.unable_reason_code or None,
        "source": {
            "type": task.source_type or Task.SourceType.MANUAL,
            "id": source_id,
        },
        "result": reference_payload(public_result_type(task.result_reference_table), task.result_reference_id),
        "subject": subject_payload(animal=task.animal, farm=task.farm),
        "result_reference_table": task.result_reference_table or None,
        "result_reference_id": task.result_reference_id,
        "created_at": json_value(task.created_at),
    }


def work_summary_for(user, org: Organization, farm=None) -> dict:
    today = timezone.localdate()
    farms = [farm] if farm is not None else authorized_farms(user, org)
    assigned = Task.objects.filter(organization=org, farm__in=farms, assigned_to=user).exclude(
        status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED]
    )
    return {
        "open_tasks": assigned.count(),
        "due_today": assigned.filter(due_at__date=today).count(),
        "overdue_tasks": assigned.filter(due_at__lt=timezone.now()).count(),
        "completed_today": Task.objects.filter(
            organization=org,
            farm__in=farms,
            assigned_to=user,
            status=Task.Status.COMPLETED,
            completed_at__date=today,
        ).count(),
    }


def _get_animal(org: Organization, farm: Farm, animal_id: Optional[int]):
    if not animal_id:
        return None
    try:
        return Animal.objects.get(id=animal_id, farm=farm, farm__organization=org)
    except Animal.DoesNotExist:
        raise ContractError(404, ErrorCode.ANIMAL_NOT_FOUND, "Animal could not be found.")


def _get_group(farm: Farm, group_id: Optional[int]):
    if not group_id:
        return None
    try:
        return AnimalGroup.objects.get(id=group_id, farm=farm)
    except AnimalGroup.DoesNotExist:
        raise ContractError(404, ErrorCode.VALIDATION_ERROR, "Group could not be found.")


def _get_assignee(org: Organization, assignee_id, farm=None):
    if not assignee_id:
        return None
    from account.models import User
    from common.access import authorized_farms
    user = User.objects.filter(Q(organization=org) | Q(id=org.user_id), id=assignee_id,
                               account_status="active", is_active=True).first()
    if user is None:
        raise ContractError(404, ErrorCode.USER_NOT_FOUND, "User could not be found.")
    if farm is not None and not authorized_farms(user, org).filter(pk=farm.pk).exists():
        raise ContractError(403, ErrorCode.FARM_ACCESS_DENIED, "Assignee does not have access to this farm.")
    return user


def _validate_subject(task_type: str, animal, group):
    """Enforce the D02-002 subject model supported by the current contract."""
    if animal and group:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Select either an animal or a group, not both.")
    animal_only = {
        Task.Type.TREATMENT, Task.Type.OBSERVATION, Task.Type.WEIGHT,
        Task.Type.PREGNANCY_CHECK, Task.Type.SALE, Task.Type.MORTALITY,
    }
    animal_or_group = {Task.Type.VACCINATION, Task.Type.FEED_ISSUANCE, Task.Type.MOVEMENT}
    if task_type in animal_only and animal is None:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "This task type requires an individual animal subject.")
    if task_type in animal_or_group and animal is None and group is None:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "This task type requires an animal or group subject.")
    if task_type == Task.Type.PREGNANCY_CHECK and animal.gender != "female":
        raise ContractError(422, ErrorCode.INVALID_ANIMAL_STATE, "Pregnancy checks require a female animal.")


def _derived_task_title(task_type: str, animal, group, supplied_title: str) -> str:
    if task_type == Task.Type.GENERIC:
        if not (supplied_title or "").strip():
            raise ContractError(422, ErrorCode.VALIDATION_ERROR, "title is required for a generic task.")
        return supplied_title.strip()
    subject = animal.tag_id if animal else group.name
    patterns = {
        Task.Type.VACCINATION: "Vaccinate {subject}", Task.Type.TREATMENT: "Treat {subject}",
        Task.Type.FEED_ISSUANCE: "Issue feed to {subject}", Task.Type.OBSERVATION: "Record health observation — {subject}",
        Task.Type.WEIGHT: "Weigh {subject}", Task.Type.MOVEMENT: "Move {subject}",
        Task.Type.PREGNANCY_CHECK: "Pregnancy Check — {subject}", Task.Type.SALE: "Sell {subject}",
        Task.Type.MORTALITY: "Record mortality — {subject}",
    }
    return patterns[task_type].format(subject=subject)


def _validate_assignee_can_execute(assignee, org: Organization, farm: Farm, task_type: str):
    if assignee is None:
        return
    from common.access import has_capability
    from common.permissions import Permissions

    domain_permissions = {
        Task.Type.VACCINATION: (Permissions.Health.CREATE,), Task.Type.TREATMENT: (Permissions.Health.CREATE,),
        Task.Type.OBSERVATION: ("record_health_observation",), Task.Type.MORTALITY: (Permissions.Health.CREATE,),
        Task.Type.WEIGHT: (Permissions.Animal.UPDATE, Permissions.Animal.CREATE), Task.Type.PREGNANCY_CHECK: (Permissions.Reproduction.CREATE,),
        Task.Type.FEED_ISSUANCE: (Permissions.Feed.CREATE,), Task.Type.SALE: (Permissions.SalesRecord.CREATE,),
        Task.Type.MOVEMENT: (Permissions.MovementRecord.CREATE,), Task.Type.GENERIC: (Permissions.Animal.CREATE, Permissions.Farm.UPDATE),
    }
    has_operation = has_capability(assignee, org, "complete_operation", farm=farm)
    has_domain = any(has_capability(assignee, org, code, farm=farm) for code in domain_permissions[task_type])
    if not has_operation or not has_domain:
        missing = ([] if has_operation else ["complete_operation"]) + ([] if has_domain else list(domain_permissions[task_type]))
        raise ContractError(422, ErrorCode.VALIDATION_ERROR,
            "Assignee is not eligible to execute this task for the selected farm.",
            errors={"assignee_id": "missing capabilities: " + ", ".join(missing)})


def validate_schedule_template(*, org: Organization, farm: Farm, task_type: str, animal_id=None,
                               group_id=None, assignee_id=None):
    """Validate that a schedule can only generate a currently-valid Operations task.

    A schedule stores a future work definition; it must not be able to bypass the
    subject and assignee rules applied to a manually created task.
    """
    if task_type not in Task.Type.values:
        raise ContractError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Invalid task type.",
            errors={"task_type": task_type},
        )
    animal = _get_animal(org, farm, animal_id)
    group = _get_group(farm, group_id)
    _validate_subject(task_type, animal, group)
    assignee = _get_assignee(org, assignee_id, farm)
    _validate_assignee_can_execute(assignee, org, farm, task_type)
    return animal, group, assignee


def create_task(
    *,
    org: Organization,
    farm: Farm,
    user,
    task_type: str,
    title: str,
    description: str = "",
    animal_id=None,
    group_id=None,
    due_at=None,
    priority: str = Task.Priority.NORMAL,
    assignee_id=None,
    parent=None,
    schedule=None,
    source_type=None,
    source_id=None,
    occurrence_key="",
    preserve_title=False,
) -> Task:
    if task_type not in Task.Type.values:
        raise ContractError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Invalid task type.",
            errors={"task_type": task_type},
        )
    animal = _get_animal(org, farm, animal_id)
    group = _get_group(farm, group_id)
    _validate_subject(task_type, animal, group)
    assignee = _get_assignee(org, assignee_id, farm)
    _validate_assignee_can_execute(assignee, org, farm, task_type)
    if priority not in Task.Priority.values:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Invalid priority.")
    title = title.strip() if preserve_title else _derived_task_title(task_type, animal, group, title)
    if not title:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "title is required.")
    task = Task.objects.create(
        organization=org,
        farm=farm,
        animal=animal,
        group=group,
        parent=parent,
        schedule=schedule,
        task_type=task_type,
        title=title,
        description=description or "",
        priority=priority,
        due_at=as_datetime(due_at) if due_at else None,
        created_by=user,
        status=Task.Status.ASSIGNED if assignee else Task.Status.DRAFT,
        assigned_to=assignee,
        source_type=source_type
        or (Task.SourceType.SCHEDULE if schedule else Task.SourceType.MANUAL),
        source_id=source_id or (schedule.id if schedule else None),
        occurrence_key=occurrence_key or "",
    )
    if assignee:
        TaskAssignment.objects.create(
            task=task, user=assignee, assigned_by=user, status=TaskAssignment.Status.PENDING
        )
        notify(
            assignee,
            org,
            title="Task assigned",
            body=task.title,
            farm=farm,
            reference_table="task",
            reference_id=task.id,
            notification_type="task_assigned",
        )
    emit_event(
        farm,
        "task_created",
        f"Task created — {task.title}",
        task.description,
        "task",
        task.id,
        user,
        animal=animal,
        group=group,
        metadata={
            "task_type": task.task_type,
            "priority": task.priority,
            "due_at": json_value(task.due_at),
            "assignee_id": str(task.assigned_to_id) if task.assigned_to_id else None,
        },
    )
    if assignee:
        emit_event(
            farm, "task_assigned", f"Task assigned — {task.title}", "Initial task assignment.",
            "task", task.id, user, animal=animal, group=group,
            metadata={"previous_assignee_id": None, "new_assignee_id": str(assignee.id)},
        )
    return task


def get_task(org: Organization, task_id: int, farm: Farm = None) -> Task:
    try:
        qs = Task.objects.select_related("farm", "animal", "assigned_to", "created_by", "group")
        task = qs.get(id=task_id, organization=org)
    except Task.DoesNotExist:
        raise ContractError(404, ErrorCode.TASK_NOT_FOUND, "Task could not be found.")
    if farm and task.farm_id != farm.id:
        raise ContractError(404, ErrorCode.TASK_NOT_FOUND, "Task could not be found.")
    return task


def assign_task(task: Task, actor, assignee_id) -> Task:
    task = Task.objects.select_for_update().select_related("farm", "organization").get(pk=task.pk)
    if task.status in (Task.Status.COMPLETED, Task.Status.CANCELLED, Task.Status.UNABLE_TO_COMPLETE):
        raise ContractError(
            409, ErrorCode.TASK_INVALID_STATE, "Closed tasks must be reopened before assignment."
        )
    assignee = _get_assignee(task.organization, assignee_id, task.farm)
    if not assignee:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "assignee_id is required.")
    _validate_assignee_can_execute(assignee, task.organization, task.farm, task.task_type)
    previous_assignee = task.assigned_to
    TaskAssignment.objects.filter(
        task=task, status=TaskAssignment.Status.PENDING
    ).update(status=TaskAssignment.Status.SUPERSEDED)
    TaskAssignment.objects.create(
        task=task, user=assignee, assigned_by=actor, status=TaskAssignment.Status.PENDING
    )
    task.assigned_to = assignee
    task.status = Task.Status.ASSIGNED
    task.accepted_at = None
    task.save(update_fields=["assigned_to", "status", "accepted_at", "updated_at"])
    emit_event(
        task.farm,
        "task_reassigned" if previous_assignee else "task_assigned",
        f"Task {'reassigned' if previous_assignee else 'assigned'} — {task.title}",
        f"Previous assignee: {getattr(previous_assignee, 'email', 'unassigned')}; new assignee: {assignee.email}",
        "task",
        task.id,
        actor,
        animal=task.animal,
        group=task.group,
        changeset={"assigned_to": {
            "before": str(previous_assignee.id) if previous_assignee else None,
            "after": str(assignee.id),
        }},
    )
    notify(
        assignee,
        task.organization,
        title="Task assigned",
        body=task.title,
        farm=task.farm,
        reference_table="task",
        reference_id=task.id,
        notification_type="task_reassigned" if previous_assignee else "task_assigned",
    )
    return task


def unassign_open_tasks_for_access_loss(user, actor, *, farm: Farm = None, reason: str) -> int:
    """Remove current assignments after a deliberate access-loss decision.

    The task and its historical assignment records remain intact.  This does
    not cancel or complete work; management can subsequently assign it again.
    Caller must already be inside the governing account/role transaction.
    """
    tasks = Task.objects.select_for_update().filter(assigned_to=user).exclude(
        status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED]
    )
    if farm is not None:
        tasks = tasks.filter(farm=farm)
    count = 0
    # Do not join nullable subject relations while issuing FOR UPDATE on
    # PostgreSQL; lock the Task rows themselves and resolve relations lazily.
    for task in tasks:
        TaskAssignment.objects.filter(
            task=task,
            user=user,
            status__in=[TaskAssignment.Status.PENDING, TaskAssignment.Status.ACCEPTED],
        ).update(status=TaskAssignment.Status.SUPERSEDED)
        task.assigned_to = None
        task.status = Task.Status.DRAFT
        task.accepted_at = None
        task.started_at = None
        task.save(update_fields=["assigned_to", "status", "accepted_at", "started_at", "updated_at"])
        emit_event(
            task.farm,
            "task_unassigned",
            f"Task unassigned — {task.title}",
            reason,
            "task",
            task.id,
            actor,
            animal=task.animal,
            group=task.group,
        )
        count += 1
    return count


def accept_task(task: Task, actor) -> Task:
    task = Task.objects.select_for_update().get(pk=task.pk)
    if task.status == Task.Status.DRAFT:
        raise ContractError(409, ErrorCode.TASK_ASSIGNMENT_REQUIRED, "Task must be assigned before it can be accepted.")
    if task.status == Task.Status.CANCELLED:
        raise ContractError(409, ErrorCode.TASK_ALREADY_CANCELLED, "Task cannot be accepted.")
    if task.status == Task.Status.COMPLETED:
        raise ContractError(409, ErrorCode.TASK_ALREADY_COMPLETED, "Task cannot be accepted.")
    if task.status == Task.Status.ACCEPTED and task.accepted_at:
        raise ContractError(409, ErrorCode.TASK_ALREADY_ACCEPTED, "Task is already accepted.")
    if task.assigned_to_id and task.assigned_to_id != actor.id:
        if not is_organization_owner(actor, task.organization):
            raise ContractError(
                403, ErrorCode.PERMISSION_DENIED, "Only the assignee can accept this task."
            )
    if not task.assigned_to_id:
        task.assigned_to = actor
    task.status = Task.Status.ACCEPTED
    if not task.accepted_at:
        task.accepted_at = timezone.now()
    task.save(update_fields=["assigned_to", "status", "accepted_at", "updated_at"])
    TaskAssignment.objects.filter(task=task, user=task.assigned_to).update(
        status=TaskAssignment.Status.ACCEPTED, accepted_at=task.accepted_at
    )
    emit_event(
        task.farm, "task_accepted", f"Task accepted — {task.title}", "Task responsibility accepted.",
        "task", task.id, actor, animal=task.animal, group=task.group,
    )
    return task


def start_task(task: Task, actor) -> Task:
    task = Task.objects.select_for_update().get(pk=task.pk)
    if task.status not in (Task.Status.ASSIGNED, Task.Status.ACCEPTED):
        raise ContractError(409, ErrorCode.TASK_INVALID_STATE, "Task cannot be started.")
    if task.assigned_to_id != actor.id and not is_organization_owner(actor, task.organization):
        raise ContractError(
            403, ErrorCode.TASK_NOT_ASSIGNED_TO_USER, "Only the assignee can start this task."
        )
    if task.status == Task.Status.ASSIGNED:
        accept_task(task, actor)
        task.refresh_from_db()
    task.status = Task.Status.IN_PROGRESS
    if not task.started_at:
        task.started_at = timezone.now()
    if not task.accepted_at:
        task.accepted_at = task.started_at
    task.save(update_fields=["status", "started_at", "accepted_at", "updated_at"])
    emit_event(
        task.farm, "task_started", f"Task started — {task.title}", "Work started.",
        "task", task.id, actor, animal=task.animal, group=task.group,
    )
    return task


def cancel_task(task: Task, actor, reason: str = "") -> Task:
    if task.status == Task.Status.CANCELLED:
        raise ContractError(409, ErrorCode.TASK_ALREADY_CANCELLED, "Task cannot be cancelled.")
    if task.status == Task.Status.COMPLETED:
        raise ContractError(409, ErrorCode.TASK_ALREADY_COMPLETED, "Task cannot be cancelled.")
    if task.status == Task.Status.UNABLE_TO_COMPLETE:
        raise ContractError(409, ErrorCode.TASK_INVALID_STATE, "Unable-to-complete tasks must be reopened before cancellation.")
    if not (reason or "").strip():
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "cancelled_reason is required.")
    previous = task.status
    task.status = Task.Status.CANCELLED
    if not task.cancelled_at:
        task.cancelled_at = timezone.now()
    task.cancel_reason = reason.strip()
    task.save(update_fields=["status", "cancelled_at", "cancel_reason", "updated_at"])
    emit_event(
        task.farm,
        "task_cancelled",
        f"Task cancelled — {task.title}",
        reason or "",
        "task",
        task.id,
        actor,
        animal=task.animal,
        group=task.group,
        metadata={"previous_status": previous, "reason": task.cancel_reason},
    )
    if task.assigned_to_id:
        notify(
            task.assigned_to,
            task.organization,
            title="Task cancelled",
            body=task.title,
            farm=task.farm,
            reference_table="task",
            reference_id=task.id,
            notification_type="task_cancelled",
        )
    return task


def _ensure_completable(task: Task, actor):
    if task.status == Task.Status.COMPLETED:
        raise ContractError(409, ErrorCode.TASK_ALREADY_COMPLETED, "Task is already completed.")
    if task.status == Task.Status.CANCELLED:
        raise ContractError(409, ErrorCode.TASK_ALREADY_CANCELLED, "Cancelled tasks cannot be completed.")
    if task.status == Task.Status.UNABLE_TO_COMPLETE:
        raise ContractError(
            409,
            ErrorCode.TASK_UNABLE_TO_COMPLETE_RECORDED,
            "Reopen this task before completing it.",
        )
    if not task.assigned_to_id:
        raise ContractError(
            409,
            ErrorCode.TASK_ASSIGNMENT_REQUIRED,
            "Task must be assigned before it can be completed.",
        )
    if task.assigned_to_id != actor.id and not is_organization_owner(actor, task.organization):
        raise ContractError(
            403, ErrorCode.PERMISSION_DENIED, "Only the assignee can complete this task."
        )
    # Accept and Start are intentionally optional. Direct completion from
    # ASSIGNED therefore retains null accepted_at and started_at timestamps.


def _stock_error(exc: ValidationError):
    messages = []
    if hasattr(exc, "messages"):
        messages = list(exc.messages)
    elif hasattr(exc, "message_dict"):
        for v in exc.message_dict.values():
            messages.extend(v if isinstance(v, list) else [v])
    text = " ".join(str(m) for m in messages) or str(exc)
    lower = text.lower()
    if "drug" in lower or "batch" in lower:
        code = ErrorCode.INSUFFICIENT_DRUG_STOCK
    elif "feed" in lower or "stock" in lower:
        code = ErrorCode.INSUFFICIENT_FEED_STOCK
    else:
        code = ErrorCode.TASK_COMPLETION_FAILED
    raise ContractError(409, code, text, errors={"details": messages})


def _complete_vaccination(task: Task, actor, payload: dict):
    vaccine_name = payload.get("vaccine_name")
    if not vaccine_name:
        raise ContractError(
            422, ErrorCode.VALIDATION_ERROR, "vaccine_name is required.", errors={"vaccine_name": "required"}
        )
    record = VaccinationRecord(
        farm=task.farm,
        animal=task.animal,
        group=task.group,
        vaccine_name=vaccine_name,
        date_given=payload.get("date_given") or timezone.localdate(),
        next_due_date=payload.get("next_due_date"),
        notes=payload.get("notes") or "",
        created_by=actor,
    )
    try:
        record.full_clean()
        record.save()
    except ValidationError as exc:
        _stock_error(exc)
    emit_event(
        task.farm,
        "vaccination",
        f"Vaccination - {record.vaccine_name}",
        record.notes or "",
        "vaccination",
        record.id,
        actor,
        animal=task.animal,
        group=task.group,
        event_date=record.date_given,
    )
    if record.next_due_date:
        create_task(
            org=task.organization,
            farm=task.farm,
            user=actor,
            task_type=Task.Type.VACCINATION,
            title=f"Follow-up vaccination — {record.vaccine_name}",
            description=f"Due after {record.vaccine_name}",
            animal_id=task.animal_id,
            group_id=task.group_id,
            due_at=record.next_due_date,
            assignee_id=task.assigned_to_id,
            # Direct domain actions deliberately have no Task.  A follow-up is
            # still legitimate work, but it cannot point at a fabricated task.
            parent=task if task.pk else None,
            source_type=Task.SourceType.VACCINATION_FOLLOW_UP,
            source_id=record.id,
        )
    return "vaccination_record", record.id


def _complete_treatment(task: Task, actor, payload: dict):
    diagnosis = payload.get("diagnosis")
    treatment = payload.get("treatment")
    severity = payload.get("severity") or "mild"
    if not diagnosis or not treatment:
        raise ContractError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "diagnosis and treatment are required.",
            errors={"diagnosis": "required", "treatment": "required"},
        )
    data = {
        "farm": task.farm,
        "animal": task.animal,
        "group": task.group,
        "diagnosis": diagnosis,
        "treatment": treatment,
        "severity": severity,
        "treatment_date": payload.get("treatment_date") or timezone.localdate(),
        "next_follow_up_date": payload.get("next_follow_up_date"),
        "notes": payload.get("notes") or "",
        "created_by": actor,
    }
    if payload.get("drug_id"):
        data["drug"] = Drug.objects.filter(id=payload["drug_id"]).first()
    if payload.get("drug_batch_id"):
        try:
            data["drug_batch"] = DrugBatch.objects.get(id=payload["drug_batch_id"], farm=task.farm)
        except DrugBatch.DoesNotExist:
            raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Drug batch could not be found.")
    if payload.get("quantity_administered") is not None:
        data["quantity_administered"] = payload["quantity_administered"]
    if payload.get("case_id"):
        try:
            data["case"] = HealthCase.objects.get(id=payload["case_id"], farm=task.farm)
        except HealthCase.DoesNotExist:
            raise ContractError(404, ErrorCode.HEALTH_CASE_NOT_FOUND, "Health case could not be found.")
    record = TreatmentRecord(**data)
    try:
        record.full_clean()
        record.save()
    except ValidationError as exc:
        _stock_error(exc)
    emit_event(
        task.farm,
        "treatment",
        f"Treatment - {record.severity}",
        record.diagnosis,
        "treatment",
        record.id,
        actor,
        animal=task.animal,
        group=task.group,
        event_date=record.treatment_date,
    )
    if record.next_follow_up_date:
        create_task(
            org=task.organization,
            farm=task.farm,
            user=actor,
            task_type=Task.Type.TREATMENT,
            title=f"Treatment follow-up — {task.title}",
            animal_id=task.animal_id,
            group_id=task.group_id,
            due_at=record.next_follow_up_date,
            assignee_id=task.assigned_to_id,
            parent=task if task.pk else None,
            source_type=Task.SourceType.TREATMENT_FOLLOW_UP,
            source_id=record.id,
        )
    return "treatment_record", record.id


def execute_direct_domain_action(
    org: Organization,
    farm: Farm,
    actor,
    *,
    task_type: str,
    animal=None,
    group=None,
    payload: Optional[dict] = None,
):
    """Execute a permitted ad-hoc domain action without persisting a Task.

    The transient Task supplies the shared typed-workflow handlers with the
    subject and farm context.  It is intentionally never saved: the resulting
    business record, not an Operations task, is authoritative for this path.
    """
    handlers = {
        Task.Type.VACCINATION: _complete_vaccination,
        Task.Type.TREATMENT: _complete_treatment,
        Task.Type.FEED_ISSUANCE: _complete_feed,
        Task.Type.SALE: _complete_sale,
        Task.Type.MOVEMENT: _complete_movement,
        Task.Type.OBSERVATION: _complete_observation,
        Task.Type.WEIGHT: _complete_weight,
        Task.Type.PREGNANCY_CHECK: _complete_pregnancy_check,
        Task.Type.MORTALITY: _complete_mortality,
    }
    handler = handlers.get(task_type)
    if handler is None:
        raise ContractError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "task_type must name a typed domain action; generic has no domain result.",
        )
    context = Task(
        organization=org,
        farm=farm,
        animal=animal,
        group=group,
        task_type=task_type,
        title=f"Ad-hoc {task_type.replace('_', ' ')}",
        description="",
        created_by=actor,
    )
    with transaction.atomic():
        return handler(context, actor, payload or {})


def _complete_feed(task: Task, actor, payload: dict):
    inventory_id = payload.get("feed_inventory_id")
    quantity = payload.get("quantity_issued")
    if not inventory_id or quantity is None:
        raise ContractError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "feed_inventory_id and quantity_issued are required.",
        )
    try:
        inventory = FeedInventory.objects.get(id=inventory_id, farm=task.farm)
    except FeedInventory.DoesNotExist:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Feed inventory could not be found.")
    target_type = payload.get("target_type") or ("group" if task.group_id and not task.animal_id else "animal")
    record = FeedIssuanceRecord(
        farm=task.farm,
        target_type=target_type,
        animal=task.animal if target_type == "animal" else None,
        group=task.group if target_type == "group" else None,
        feed_inventory=inventory,
        quantity_issued=quantity,
        issue_date=payload.get("issue_date") or timezone.localdate(),
        issued_by=actor,
        notes=payload.get("notes") or "",
        feeding_period=payload.get("feeding_period"),
        allocation_method=payload.get("allocation_method"),
    )
    if payload.get("feed_batch_id"):
        try:
            record.feed_batch = FeedBatch.objects.get(id=payload["feed_batch_id"], farm=task.farm)
        except FeedBatch.DoesNotExist:
            raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Feed batch could not be found.")
    try:
        record.save()
    except ValidationError as exc:
        _stock_error(exc)
    emit_event(
        task.farm,
        "feeding",
        f"Feed Issued - {record.quantity_issued}",
        record.notes or "",
        "feed_issuance_record",
        record.id,
        actor,
        animal=task.animal,
        group=task.group,
        event_date=record.issue_date,
    )
    return "feed_issuance_record", record.id


def _complete_sale(task: Task, actor, payload: dict):
    if not task.animal_id:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "A sale task requires an animal.")
    animal = task.animal
    if animal.status == "dead":
        raise ContractError(409, ErrorCode.ANIMAL_ALREADY_DECEASED, "Animal is already deceased.")
    if animal.status == "sold":
        raise ContractError(409, ErrorCode.ANIMAL_ALREADY_SOLD, "Animal is already sold.")
    buyer_name = payload.get("buyer_name")
    price = payload.get("price")
    if not buyer_name or price is None:
        raise ContractError(
            422, ErrorCode.VALIDATION_ERROR, "buyer_name and price are required."
        )
    readiness = evaluate_sale_readiness(animal, farm=task.farm, expected_sale_price=price)
    override_reason = payload.get("override_reason")
    if readiness.get("restrictions") and not override_reason:
        raise ContractError(
            409,
            ErrorCode.INVALID_ANIMAL_STATE,
            "Animal is not eligible for sale.",
            errors={"restrictions": readiness.get("restrictions"), "readiness": readiness},
        )
    sale = SalesRecord(
        farm=task.farm,
        animal=animal,
        buyer_name=buyer_name,
        price=price,
        sale_date=as_datetime(payload.get("sale_date")),
        reason=payload.get("reason") or "",
        notes=payload.get("notes") or "",
        created_by=actor,
    )
    if override_reason:
        sale._override_restriction = True
    try:
        sale.save()
    except ValidationError as exc:
        _stock_error(exc)
    emit_event(
        task.farm,
        "sale",
        f"Sale — {animal.tag_id}",
        buyer_name,
        "sales_record",
        sale.id,
        actor,
        animal=animal,
        event_date=sale.sale_date,
    )
    return "sales_record", sale.id


def _complete_movement(task: Task, actor, payload: dict):
    record = MovementRecord(
        farm=task.farm,
        animal=task.animal,
        group=task.group,
        move_date=as_datetime(payload.get("move_date")),
        reason=payload.get("reason") or payload.get("notes") or "",
        created_by=actor,
    )
    if payload.get("to_housing_unit_id"):
        from admin_panel.models import FarmHousingUnit

        record.to_housing_unit_id = payload["to_housing_unit_id"]
        if task.animal and task.animal.housing_unit_id:
            record.from_housing_unit_id = task.animal.housing_unit_id
    if payload.get("to_unit_id"):
        from farms.models import FarmUnit

        record.to_unit_id = payload["to_unit_id"]
        if task.animal and task.animal.unit_id:
            record.from_unit_id = task.animal.unit_id
    try:
        record.full_clean()
        record.save()
    except ValidationError as exc:
        _stock_error(exc)
    if task.animal and record.to_housing_unit_id:
        task.animal.housing_unit_id = record.to_housing_unit_id
        task.animal.save(update_fields=["housing_unit"])
    emit_event(
        task.farm,
        "movement",
        "Animal moved",
        record.reason or "",
        "movement_record",
        record.id,
        actor,
        animal=task.animal,
        group=task.group,
        event_date=record.move_date,
    )
    return "movement_record", record.id


def _complete_observation(task: Task, actor, payload: dict):
    observation = HealthObservation.objects.create(
        farm=task.farm,
        animal=task.animal,
        group=task.group,
        observed_at=as_datetime(payload.get("observed_at")),
        symptoms=payload.get("symptoms") or payload.get("notes") or task.description,
        severity=payload.get("severity") or "mild",
        created_by=actor,
        case_id=payload.get("case_id"),
    )
    emit_event(
        task.farm,
        "observation",
        "Health observation",
        observation.symptoms,
        "health_observation",
        observation.id,
        actor,
        animal=task.animal,
        group=task.group,
        event_date=observation.observed_at,
    )
    return "health_observation", observation.id


def _complete_weight(task: Task, actor, payload: dict):
    if not task.animal_id:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "A weight task requires an animal.")
    weight = payload.get("weight")
    if weight is None:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "weight is required.")
    measured = payload.get("measured_at") or payload.get("date") or timezone.localdate()
    if hasattr(measured, "date"):
        measured = measured.date()
    record, _ = AnimalWeight.objects.update_or_create(
        animal=task.animal,
        date=measured,
        defaults={"farm": task.farm, "weight": float(weight)},
    )
    emit_event(
        task.farm,
        "weight",
        f"Weight — {record.weight} kg",
        payload.get("notes") or "",
        "animal_weight",
        record.id,
        actor,
        animal=task.animal,
        event_date=record.date,
    )
    return "animal_weight", record.id


def _complete_pregnancy_check(task: Task, actor, payload: dict):
    if not task.animal_id:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "A pregnancy check requires an animal.")
    result = payload.get("result")
    if result not in ("pregnant", "not_pregnant"):
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "result must be pregnant or not_pregnant.")
    checked = payload.get("checked_at") or timezone.localdate()
    if hasattr(checked, "date"):
        checked = checked.date()
    defaults = {
        "check_date": checked,
        "result": result,
        "expected_delivery_date": payload.get("expected_delivery_date"),
        "notes": payload.get("notes") or "",
        "created_by": actor,
    }
    try:
        record, created = PregnancyRecord.objects.get_or_create(
            farm=task.farm, animal=task.animal, defaults=defaults
        )
    except ValidationError as exc:
        _stock_error(exc)
    if not created:
        for key, value in defaults.items():
            setattr(record, key, value)
        record._override_eligibility = True
        try:
            record.save()
        except ValidationError as exc:
            _stock_error(exc)
    task.animal.refresh_from_db()
    task.animal.is_pregnant = result == "pregnant"
    task.animal.save(update_fields=["is_pregnant"])
    emit_event(
        task.farm,
        "pregnancy_check",
        f"Pregnancy check — {result}",
        record.notes or "",
        "pregnancy_record",
        record.id,
        actor,
        animal=task.animal,
        event_date=record.check_date,
    )
    return "pregnancy_record", record.id


def _complete_mortality(task: Task, actor, payload: dict):
    if not task.animal_id:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "A mortality task requires an animal.")
    animal = task.animal
    if animal.status == "dead":
        raise ContractError(409, ErrorCode.ANIMAL_ALREADY_DECEASED, "Animal is already deceased.")
    died_at = payload.get("died_at") or payload.get("death_date") or timezone.localdate()
    if hasattr(died_at, "date"):
        died_at = died_at.date()
    record = MortalityRecord(
        farm=task.farm,
        animal=animal,
        cause=payload.get("cause") or payload.get("notes") or "Not specified",
        death_date=died_at,
        notes=payload.get("notes") or "",
        created_by=actor,
    )
    try:
        record.full_clean()
        record.save()
    except ValidationError as exc:
        _stock_error(exc)
    emit_event(
        task.farm,
        "mortality",
        f"Mortality — {animal.tag_id or animal.id}",
        record.cause,
        "mortality_record",
        record.id,
        actor,
        animal=animal,
        event_date=record.death_date,
    )
    incompatible = (
        Task.Type.VACCINATION,
        Task.Type.TREATMENT,
        Task.Type.FEED_ISSUANCE,
        Task.Type.SALE,
        Task.Type.MOVEMENT,
        Task.Type.OBSERVATION,
        Task.Type.WEIGHT,
        Task.Type.PREGNANCY_CHECK,
        Task.Type.MORTALITY,
    )
    now = timezone.now()
    open_tasks = (
        Task.objects.filter(animal=animal, organization=task.organization, task_type__in=incompatible)
        .exclude(id=task.id)
        .exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
    )
    for sibling in open_tasks:
        sibling.status = Task.Status.CANCELLED
        sibling.cancelled_at = now
        sibling.cancel_reason = "system mortality"
        sibling.save(update_fields=["status", "cancelled_at", "cancel_reason", "updated_at"])
        emit_event(
            sibling.farm,
            "task_cancelled",
            f"Task cancelled — {sibling.title}",
            "system mortality",
            "task",
            sibling.id,
            actor,
            animal=animal,
        )
    return "mortality_record", record.id


UNABLE_REASON_CODES = {
    "animal_unavailable",
    "animal_moved",
    "animal_sick",
    "material_unavailable",
    "medicine_unavailable",
    "equipment_unavailable",
    "incorrect_assignment",
    "unable_to_identify_subject",
    "unsafe_to_proceed",
    "other",
}


def mark_unable_to_complete(task: Task, actor, payload: Optional[dict] = None) -> Task:
    payload = payload or {}
    if task.status == Task.Status.COMPLETED:
        raise ContractError(409, ErrorCode.TASK_ALREADY_COMPLETED, "Completed tasks cannot be marked unable.")
    if task.status == Task.Status.CANCELLED:
        raise ContractError(409, ErrorCode.TASK_ALREADY_CANCELLED, "Cancelled tasks cannot be marked unable.")
    if task.status == Task.Status.UNABLE_TO_COMPLETE:
        raise ContractError(
            409, ErrorCode.TASK_UNABLE_TO_COMPLETE_RECORDED, "Unable-to-complete is already recorded."
        )
    if task.status not in (Task.Status.ASSIGNED, Task.Status.ACCEPTED, Task.Status.IN_PROGRESS):
        raise ContractError(409, ErrorCode.TASK_INVALID_STATE, "Task must be assigned before it can be marked unable.")
    if task.assigned_to_id != actor.id and not is_organization_owner(actor, task.organization):
        raise ContractError(
            403, ErrorCode.TASK_NOT_ASSIGNED_TO_USER, "Only the assignee can mark this task unable to complete."
        )
    reason = payload.get("reason_code") or "other"
    if reason not in UNABLE_REASON_CODES:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Invalid reason_code.")
    if reason == "other" and not (payload.get("notes") or "").strip():
        raise ContractError(
            422, ErrorCode.VALIDATION_ERROR,
            "notes are required when reason_code is other.", errors={"notes": "required for other"},
        )
    previous = task.status
    task.status = Task.Status.UNABLE_TO_COMPLETE
    task.unable_to_complete_at = timezone.now()
    task.unable_reason_code = reason
    task.unable_notes = payload.get("notes") or ""
    task.save(
        update_fields=[
            "status",
            "unable_to_complete_at",
            "unable_reason_code",
            "unable_notes",
            "updated_at",
        ]
    )
    emit_event(
        task.farm,
        "task_unable",
        f"Unable to complete — {task.title}",
        f"{reason}: {task.unable_notes} (was {previous})",
        "task",
        task.id,
        actor,
        animal=task.animal,
        group=task.group,
        metadata={"previous_status": previous, "reason_code": reason},
    )
    notify_farm_management(
        task.organization, task.farm, title="Task unable to complete", body=task.title,
        reference_table="task", reference_id=task.id,
        notification_type="operational_exception_created",
    )
    return task


def reopen_task(task: Task, actor, payload: Optional[dict] = None) -> Task:
    payload = payload or {}
    if task.status == Task.Status.COMPLETED:
        raise ContractError(
            409, ErrorCode.TASK_CANNOT_BE_REOPENED, "Ordinary workers must not reopen completed tasks."
        )
    if task.status not in (Task.Status.UNABLE_TO_COMPLETE, Task.Status.CANCELLED):
        raise ContractError(409, ErrorCode.TASK_CANNOT_BE_REOPENED, "Only unable or cancelled tasks can be reopened.")
    previous = task.status
    previous_reason = task.unable_reason_code or task.cancel_reason or ""
    if payload.get("assignee_id"):
        task.assigned_to = _get_assignee(task.organization, payload["assignee_id"])
    if payload.get("due_at"):
        task.due_at = as_datetime(payload["due_at"])
    task.status = Task.Status.ASSIGNED if task.assigned_to_id else Task.Status.DRAFT
    task.unable_to_complete_at = None
    task.unable_reason_code = ""
    task.unable_notes = ""
    task.cancelled_at = None
    task.cancel_reason = ""
    task.accepted_at = None
    task.started_at = None
    task.save(
        update_fields=[
            "assigned_to",
            "due_at",
            "status",
            "unable_to_complete_at",
            "unable_reason_code",
            "unable_notes",
            "cancelled_at",
            "cancel_reason",
            "accepted_at",
            "started_at",
            "updated_at",
        ]
    )
    emit_event(
        task.farm,
        "task_reopened",
        f"Task reopened — {task.title}",
        f"Was {previous}. {payload.get('reason') or previous_reason}",
        "task",
        task.id,
        actor,
        animal=task.animal,
        group=task.group,
        changeset={"status": {"before": previous, "after": task.status}},
    )
    if task.assigned_to_id:
        notify(
            task.assigned_to,
            task.organization,
            title="Task reopened",
            body=payload.get("reason") or task.title,
            farm=task.farm,
            reference_table="task",
            reference_id=task.id,
            notification_type="task_reopened",
        )
    return task


def complete_task(task: Task, actor, payload: Optional[dict] = None, evidence: str = "") -> Task:
    payload = payload or {}
    handlers = {
        Task.Type.VACCINATION: _complete_vaccination,
        Task.Type.TREATMENT: _complete_treatment,
        Task.Type.FEED_ISSUANCE: _complete_feed,
        Task.Type.SALE: _complete_sale,
        Task.Type.MOVEMENT: _complete_movement,
        Task.Type.OBSERVATION: _complete_observation,
        Task.Type.WEIGHT: _complete_weight,
        Task.Type.PREGNANCY_CHECK: _complete_pregnancy_check,
        Task.Type.MORTALITY: _complete_mortality,
        Task.Type.GENERIC: None,
    }
    handler = handlers.get(task.task_type)
    with transaction.atomic():
        task = Task.objects.select_for_update().get(pk=task.pk)
        _ensure_completable(task, actor)
        table, ref_id = "", None
        if handler:
            table, ref_id = handler(task, actor, payload)
        correlation_id = uuid.uuid4()
        if table and ref_id:
            # The typed domain event is a distinct fact, but shares the
            # workflow correlation with the Operations completion event.
            AnimalEvent.objects.filter(
                farm=task.farm,
                reference_table=RESULT_EVENT_REFERENCE_TABLE.get(table, table),
                reference_id=ref_id,
            ).update(correlation_id=correlation_id)
        task.status = Task.Status.COMPLETED
        task.completed_at = timezone.now()
        task.completion_payload = json_value(payload)
        task.result_reference_table = table
        task.result_reference_id = ref_id
        task.save(
            update_fields=[
                "status",
                "completed_at",
                "completion_payload",
                "result_reference_table",
                "result_reference_id",
                "updated_at",
            ]
        )
        if evidence:
            TaskEvidence.objects.create(task=task, note=evidence, created_by=actor)
        emit_event(
            task.farm,
            "task_completed",
            f"Task completed — {task.title}",
            task.description,
            "task",
            task.id,
            actor,
            animal=task.animal,
            group=task.group,
            metadata={
                "task_type": task.task_type,
                "result_reference_table": table or None,
                "result_reference_id": ref_id,
            },
            correlation_id=correlation_id,
        )
    return task


def serialize_schedule(schedule: TaskSchedule) -> dict:
    return {
        "id": schedule.id,
        "farm_id": schedule.farm_id,
        "task_type": schedule.task_type,
        "title": schedule.title,
        "description": schedule.description,
        "recurrence": schedule.recurrence,
        "next_run_at": json_value(schedule.next_run_at),
        "is_active": schedule.is_active,
        "assignee_id": str(schedule.assignee_id) if schedule.assignee_id else None,
        "animal_id": schedule.animal_id,
        "group_id": schedule.group_id,
        "created_at": json_value(schedule.created_at),
    }


def bump_schedule(schedule: TaskSchedule):
    next_run = schedule.next_run_at.astimezone(SCHEDULE_TIMEZONE)
    if schedule.recurrence == TaskSchedule.Recurrence.ONCE:
        schedule.is_active = False
    elif schedule.recurrence == TaskSchedule.Recurrence.DAILY:
        schedule.next_run_at = next_run + timedelta(days=1)
    elif schedule.recurrence == TaskSchedule.Recurrence.WEEKLY:
        schedule.next_run_at = next_run + timedelta(days=7)
    elif schedule.recurrence == TaskSchedule.Recurrence.MONTHLY:
        # Preserve the local clock time and use the last valid calendar day,
        # rather than treating a month as an arbitrary 30-day interval.
        month_index = next_run.month
        year = next_run.year + (month_index // 12)
        month = (month_index % 12) + 1
        day = min(next_run.day, calendar.monthrange(year, month)[1])
        schedule.next_run_at = next_run.replace(year=year, month=month, day=day)
    schedule.save(update_fields=["next_run_at", "is_active", "updated_at"])


def _deactivate_ineligible_schedule(schedule: TaskSchedule, actor):
    schedule.is_active = False
    schedule.save(update_fields=["is_active", "updated_at"])
    emit_event(
        schedule.farm,
        "schedule_deactivated",
        f"Schedule deactivated — {schedule.title}",
        "The stored assignee is no longer eligible for this farm or task type.",
        "task_schedule",
        schedule.id,
        actor,
        animal=schedule.animal,
        group=schedule.group,
    )


def reactivate_schedule(schedule: TaskSchedule, actor) -> Task | None:
    """Reactivate and generate at most one missed occurrence.

    Product decision D02-007: a reactivated recurring schedule creates its
    current missed occurrence once, then resumes at the next future Lagos-time
    occurrence; it does not backfill every missed interval.
    """
    with transaction.atomic():
        locked = TaskSchedule.objects.select_for_update().get(id=schedule.id)
        if locked.is_active:
            return None
        locked.is_active = True
        locked.save(update_fields=["is_active", "updated_at"])
        generated = None
        if locked.next_run_at <= timezone.now():
            generated = run_schedule(locked, actor)
            locked.refresh_from_db()
            while locked.is_active and locked.next_run_at <= timezone.now():
                bump_schedule(locked)
                locked.refresh_from_db()
        if locked.is_active:
            emit_event(
                locked.farm,
                "schedule_reactivated",
                f"Schedule reactivated — {locked.title}",
                "Future schedule execution restored.",
                "task_schedule",
                locked.id,
                actor,
                animal=locked.animal,
                group=locked.group,
            )
    return generated


def run_schedule(schedule: TaskSchedule, actor=None, *, due_only: bool = False) -> Task:
    now = timezone.now()
    ineligible_assignee = False
    with transaction.atomic():
        locked = TaskSchedule.objects.select_for_update().get(id=schedule.id)
        if not locked.is_active:
            raise ContractError(409, ErrorCode.TASK_INVALID_STATE, "Schedule is not active.")
        if due_only and locked.next_run_at > now:
            return (
                Task.objects.filter(schedule=locked)
                .exclude(occurrence_key="")
                .order_by("-id")
                .first()
            )
        occurrence_key = locked.next_run_at.isoformat()
        existing = Task.objects.filter(schedule=locked, occurrence_key=occurrence_key).first()
        if existing:
            return existing
        if locked.assignee_id:
            try:
                assignee = _get_assignee(locked.organization, locked.assignee_id, locked.farm)
                _validate_assignee_can_execute(assignee, locked.organization, locked.farm, locked.task_type)
            except ContractError:
                _deactivate_ineligible_schedule(locked, actor)
                ineligible_assignee = True
        if not ineligible_assignee:
            task = create_task(
                org=locked.organization,
                farm=locked.farm,
                user=actor,
                task_type=locked.task_type,
                title=locked.title,
                description=locked.description,
                animal_id=locked.animal_id,
                group_id=locked.group_id,
                due_at=locked.next_run_at,
                assignee_id=locked.assignee_id,
                schedule=locked,
                source_type=Task.SourceType.SCHEDULE,
                source_id=locked.id,
                occurrence_key=occurrence_key,
                # A schedule title is an explicit template label, unlike the
                # derived display title used by direct typed-task creation.
                preserve_title=True,
            )
            emit_event(
                locked.farm, "schedule_task_generated", f"Schedule generated task — {task.title}",
                "Recurring schedule expansion completed.", "task_schedule", locked.id, actor,
                animal=locked.animal, group=locked.group,
                metadata={"generated_task_id": task.id, "occurrence_key": occurrence_key},
            )
            bump_schedule(locked)
    if ineligible_assignee:
        raise ContractError(
            409,
            ErrorCode.TASK_INVALID_STATE,
            "Schedule deactivated because its assignee is no longer eligible.",
        )
    return task


def process_due_schedules(now=None) -> int:
    now = now or timezone.now()
    created = 0
    due_ids = list(
        TaskSchedule.objects.filter(is_active=True, next_run_at__lte=now).values_list("id", flat=True)
    )
    for schedule_id in due_ids:
        try:
            schedule = TaskSchedule.objects.get(id=schedule_id)
            before_key = schedule.next_run_at
            # A scheduled occurrence has no human triggering actor.  Keeping
            # this null avoids falsely attributing future automated work to
            # the person who originally created the schedule.
            task = run_schedule(schedule, None, due_only=True)
            schedule.refresh_from_db()
            if task and (schedule.next_run_at != before_key or not schedule.is_active):
                created += 1
        except ContractError:
            continue
    return created


def serialize_notification(row: Notification) -> dict:
    return {
        "id": row.id,
        "category": row.category,
        "notification_type": row.notification_type,
        "title": row.title,
        "body": row.body,
        "is_read": row.is_read,
        "read_at": json_value(row.read_at),
        "farm_id": row.farm_id,
        "reference_table": row.reference_table or None,
        "reference_id": row.reference_id,
        "created_at": json_value(row.created_at),
    }


def serialize_event(event: AnimalEvent) -> dict:
    from contract.identity import actor_payload, reference_payload, subject_payload

    return {
        "id": event.id,
        "event_name": event.event_name or (event.event_type.name if event.event_type_id else None),
        "actor_type": event.actor_type or ("user" if event.created_by_id else "system"),
        "actor_display_snapshot": event.actor_display_snapshot or None,
        "source_module": event.source_module or None,
        "occurred_at": json_value(event.event_date),
        "recorded_at": json_value(event.created_at),
        "correlation_id": str(event.correlation_id) if event.correlation_id else None,
        "metadata": event.metadata or {},
        "changeset": event.changeset or {},
        "farm_id": event.farm_id,
        "animal_id": event.animal_id,
        "animal_tag": event.animal.tag_id if event.animal_id else None,
        "group_id": event.group_id,
        "event_type": event.event_type.name if event.event_type_id else None,
        "event_date": json_value(event.event_date),  # compatibility alias for occurred_at
        "event_title": event.event_title,
        "event_summary": event.event_summary,
        "reference_table": event.reference_table,
        "reference_id": event.reference_id,
        "reference": reference_payload(event.reference_table, event.reference_id),
        "subject": subject_payload(animal=event.animal, farm=event.farm),
        "created_by": str(event.created_by_id) if event.created_by_id else None,
        "actor": actor_payload(event.created_by, getattr(event.farm, "organization", None)),
        "created_at": json_value(event.created_at),
    }
