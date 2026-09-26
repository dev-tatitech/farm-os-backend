CANONICAL_EVENT_NAMES = {
    "task_created": "operation.created",
    "task_assigned": "operation.assigned",
    "task_reassigned": "operation.reassigned",
    "task_unassigned": "operation.unassigned",
    "task_accepted": "operation.accepted",
    "task_started": "operation.started",
    "task_completed": "operation.completed",
    "task_cancelled": "operation.cancelled",
    "task_unable": "operation.unable_to_complete",
    "task_reopened": "operation.reopened",
    "schedule_deactivated": "operation_schedule.deactivated",
    "schedule_reactivated": "operation_schedule.activated",
    "schedule_created": "operation_schedule.created",
    "schedule_updated": "operation_schedule.updated",
    "schedule_task_generated": "operation_schedule.task_generated",
}


def new_event(
    farm, 
    animal, 
    event_type, 
    event_date, 
    event_title,
    event_summary,
    reference_table,
    reference_id, 
    created_by,
    group=None,
    *,
    event_name=None,
    source_module="operations",
    metadata=None,
    changeset=None,
    correlation_id=None,
    occurred_at=None,
):
    from .models import AnimalEvent
    event = event_type_fun(event_type)
    event = AnimalEvent.objects.create(
        farm = farm,
        group = group,
        animal = animal,
        event_type = event,
        event_date = occurred_at or event_date,
        event_title = event_title,
        event_summary = event_summary,
        reference_table = reference_table,
        reference_id = reference_id,
        created_by = created_by,
        event_name=event_name or CANONICAL_EVENT_NAMES.get(event_type, event_type),
        actor_type="user" if created_by is not None else "system",
        actor_display_snapshot=(
            created_by.get_full_name().strip() or created_by.username or created_by.email
        ) if created_by is not None else "System",
        source_module=source_module,
        metadata=metadata or {},
        changeset=changeset or {},
        correlation_id=correlation_id,
    )
    return event

def event_type_fun(name):
    from core.models import EventType
    event, created = EventType.objects.get_or_create(
    name=name)
    return event
