from ninja import Router

from animals.models import AnimalEvent
from operations.services import serialize_event

from .authz import require_farm, require_user, resolve_organization
from .envelope import V2Error, V2Success
from .helpers import paginated

timeline_router = Router(tags=["Timeline"])


@timeline_router.get(
    "/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Unified organization timeline",
)
def list_timeline(
    request,
    page: int = 1,
    page_size: int = 20,
    farm_id: int = None,
    animal_id: int = None,
    event_type: str = None,
):
    user = require_user(request)
    org = resolve_organization(user)
    qs = (
        AnimalEvent.objects.filter(farm__organization=org)
        .select_related("event_type", "animal", "farm")
        .order_by("-event_date", "-id")
    )
    if farm_id is not None:
        farm = require_farm(org, farm_id, user)
        qs = qs.filter(farm=farm)
    if animal_id is not None:
        qs = qs.filter(animal_id=animal_id)
    if event_type:
        qs = qs.filter(event_type__name=event_type)
    return 200, paginated(qs, page, page_size, serialize_event, "Timeline fetched successfully.")
