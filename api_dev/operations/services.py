from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from animals.event import new_event
from animals.models import Animal, AnimalEvent, AnimalGroup, AnimalWeight
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
    )


def serialize_task(task: Task) -> dict:
    from contract.identity import actor_payload, display_name, reference_payload, subject_payload

    overdue = bool(task.is_open and task.due_at and task.due_at < timezone.now())
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
        "status": "overdue" if overdue else task.status,
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
        "source": reference_payload(task.source_type, task.source_id or task.schedule_id),
        "result": reference_payload(task.result_reference_table, task.result_reference_id),
        "subject": subject_payload(animal=task.animal, farm=task.farm),
        "result_reference_table": task.result_reference_table or None,
        "result_reference_id": task.result_reference_id,
        "created_at": json_value(task.created_at),
    }


def work_summary_for(user, org: Organization) -> dict:
    today = timezone.localdate()
    assigned = Task.objects.filter(organization=org, assigned_to=user).exclude(
        status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED]
    )
    return {
        "open_tasks": assigned.count(),
        "due_today": assigned.filter(due_at__date=today).count(),
        "overdue_tasks": assigned.filter(due_at__lt=timezone.now()).count(),
        "completed_today": Task.objects.filter(
            organization=org,
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


def _get_assignee(org: Organization, assignee_id):
    if not assignee_id:
        return None
    from account.models import User

    try:
        user = User.objects.get(id=assignee_id)
    except (User.DoesNotExist, ValidationError, ValueError):
        raise ContractError(404, ErrorCode.USER_NOT_FOUND, "User could not be found.")
    if user.organization_id == org.id or org.user_id == user.id:
        return user
    if user.organizations.filter(id=org.id).exists():
        return user
    from role.models import UserRole

    if UserRole.objects.filter(user=user).filter(
        Q(farm__organization=org) | Q(farm__isnull=True, user__organization=org)
    ).exists():
        return user
    raise ContractError(
        403,
        ErrorCode.PERMISSION_DENIED,
        "User does not belong to this organization.",
    )


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
    assignee = _get_assignee(org, assignee_id)
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
        priority=priority if priority in Task.Priority.values else Task.Priority.NORMAL,
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
    if task.status in (Task.Status.COMPLETED, Task.Status.CANCELLED):
        raise ContractError(
            409, ErrorCode.TASK_INVALID_STATE, "Completed or cancelled tasks cannot be assigned."
        )
    assignee = _get_assignee(task.organization, assignee_id)
    if not assignee:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "assignee_id is required.")
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
    notify(
        assignee,
        task.organization,
        title="Task assigned",
        body=task.title,
        farm=task.farm,
        reference_table="task",
        reference_id=task.id,
    )
    return task


def accept_task(task: Task, actor) -> Task:
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
    task.accepted_at = timezone.now()
    task.save(update_fields=["assigned_to", "status", "accepted_at", "updated_at"])
    TaskAssignment.objects.filter(task=task, user=task.assigned_to).update(
        status=TaskAssignment.Status.ACCEPTED, accepted_at=task.accepted_at
    )
    return task


def start_task(task: Task, actor) -> Task:
    if task.status not in (Task.Status.ASSIGNED, Task.Status.ACCEPTED, Task.Status.DRAFT):
        raise ContractError(409, ErrorCode.TASK_INVALID_STATE, "Task cannot be started.")
    if task.assigned_to_id != actor.id and not is_organization_owner(actor, task.organization):
        raise ContractError(
            403, ErrorCode.TASK_NOT_ASSIGNED_TO_USER, "Only the assignee can start this task."
        )
    if task.status == Task.Status.ASSIGNED or task.status == Task.Status.DRAFT:
        accept_task(task, actor)
        task.refresh_from_db()
    task.status = Task.Status.IN_PROGRESS
    task.started_at = timezone.now()
    task.save(update_fields=["status", "started_at", "updated_at"])
    return task


def cancel_task(task: Task, actor, reason: str = "") -> Task:
    if task.status == Task.Status.CANCELLED:
        raise ContractError(409, ErrorCode.TASK_ALREADY_CANCELLED, "Task cannot be cancelled.")
    if task.status == Task.Status.COMPLETED:
        raise ContractError(409, ErrorCode.TASK_ALREADY_COMPLETED, "Task cannot be cancelled.")
    task.status = Task.Status.CANCELLED
    task.cancelled_at = timezone.now()
    task.cancel_reason = reason or ""
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
    if task.status == Task.Status.ASSIGNED:
        accept_task(task, actor)
        task.refresh_from_db()


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
            parent=task,
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
            parent=task,
        )
    return "treatment_record", record.id


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
    Task.objects.filter(
        animal=animal, organization=task.organization
    ).exclude(id=task.id).exclude(
        status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED]
    ).update(status=Task.Status.CANCELLED, cancel_reason="Animal deceased", cancelled_at=timezone.now())
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
    if task.assigned_to_id != actor.id and not is_organization_owner(actor, task.organization):
        raise ContractError(
            403, ErrorCode.TASK_NOT_ASSIGNED_TO_USER, "Only the assignee can mark this task unable to complete."
        )
    reason = payload.get("reason_code") or "other"
    if reason not in UNABLE_REASON_CODES:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Invalid reason_code.")
    previous = task.status
    task.status = Task.Status.UNABLE_TO_COMPLETE
    task.unable_to_complete_at = as_datetime(payload.get("performed_at"))
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
    )
    if task.created_by_id:
        notify(
            task.created_by,
            task.organization,
            title="Task unable to complete",
            body=task.title,
            farm=task.farm,
            reference_table="task",
            reference_id=task.id,
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
    if payload.get("assignee_id"):
        task.assigned_to = _get_assignee(task.organization, payload["assignee_id"])
    if payload.get("due_at"):
        task.due_at = as_datetime(payload["due_at"])
    task.status = Task.Status.ASSIGNED if task.assigned_to_id else Task.Status.DRAFT
    task.unable_to_complete_at = None
    task.cancelled_at = None
    task.accepted_at = None
    task.started_at = None
    task.save(
        update_fields=[
            "assigned_to",
            "due_at",
            "status",
            "unable_to_complete_at",
            "cancelled_at",
            "accepted_at",
            "started_at",
            "updated_at",
        ]
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
        )
    return task


def complete_task(task: Task, actor, payload: Optional[dict] = None, evidence: str = "") -> Task:
    payload = payload or {}
    _ensure_completable(task, actor)
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
        table, ref_id = "", None
        if handler:
            table, ref_id = handler(task, actor, payload)
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
        )
        notify(
            task.created_by,
            task.organization,
            title="Task completed",
            body=task.title,
            farm=task.farm,
            reference_table="task",
            reference_id=task.id,
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
    if schedule.recurrence == TaskSchedule.Recurrence.ONCE:
        schedule.is_active = False
    elif schedule.recurrence == TaskSchedule.Recurrence.DAILY:
        schedule.next_run_at = schedule.next_run_at + timedelta(days=1)
    elif schedule.recurrence == TaskSchedule.Recurrence.WEEKLY:
        schedule.next_run_at = schedule.next_run_at + timedelta(days=7)
    elif schedule.recurrence == TaskSchedule.Recurrence.MONTHLY:
        schedule.next_run_at = schedule.next_run_at + timedelta(days=30)
    schedule.save(update_fields=["next_run_at", "is_active", "updated_at"])


def run_schedule(schedule: TaskSchedule, actor) -> Task:
    if not schedule.is_active:
        raise ContractError(409, ErrorCode.TASK_INVALID_STATE, "Schedule is not active.")
    occurrence_key = schedule.next_run_at.isoformat()
    existing = Task.objects.filter(schedule=schedule, occurrence_key=occurrence_key).first()
    if existing:
        return existing
    with transaction.atomic():
        locked = TaskSchedule.objects.select_for_update().get(id=schedule.id)
        if not locked.is_active:
            raise ContractError(409, ErrorCode.TASK_INVALID_STATE, "Schedule is not active.")
        occurrence_key = locked.next_run_at.isoformat()
        existing = Task.objects.filter(schedule=locked, occurrence_key=occurrence_key).first()
        if existing:
            return existing
        task = create_task(
            org=locked.organization,
            farm=locked.farm,
            user=actor or locked.created_by,
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
        )
        bump_schedule(locked)
    return task


def process_due_schedules(now=None) -> int:
    now = now or timezone.now()
    created = 0
    due = TaskSchedule.objects.filter(is_active=True, next_run_at__lte=now)
    for schedule in due:
        before = Task.objects.filter(schedule=schedule).count()
        run_schedule(schedule, schedule.created_by)
        after = Task.objects.filter(schedule=schedule).count()
        if after > before:
            created += 1
    return created


def serialize_notification(row: Notification) -> dict:
    return {
        "id": row.id,
        "category": row.category,
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
        "farm_id": event.farm_id,
        "animal_id": event.animal_id,
        "animal_tag": event.animal.tag_id if event.animal_id else None,
        "group_id": event.group_id,
        "event_type": event.event_type.name if event.event_type_id else None,
        "event_date": json_value(event.event_date),
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
