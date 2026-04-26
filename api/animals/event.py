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
    group=None):
    from .models import AnimalEvent
    event = event_type_fun(event_type)
    event = AnimalEvent.objects.create(
        farm = farm,
        group = group,
        animal = animal,
        event_type = event,
        event_date = event_date,
        event_title = event_title,
        event_summary = event_summary,
        reference_table = reference_table,
        reference_id = reference_id,
        created_by = created_by
    )
    return event

def event_type_fun(name):
    from core.models import EventType
    event, created = EventType.objects.get_or_create(
    name=name)
    return event