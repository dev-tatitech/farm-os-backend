from django.db.models import Count, Q
from ninja import Router

from account.models import User
from admin_panel.models import FarmHousingUnit
from alerts.models import Alert
from animals.models import Animal, AnimalEvent
from common.permissions import Permissions
from farms.models import FarmUnit
from operations.models import Task
from operations.services import serialize_event
from role.models import UserRole

from .authz import (
    is_organization_owner,
    require_farm,
    require_permission,
    require_user,
    resolve_organization,
)
from .envelope import V2Error, V2Success, success_body
from .helpers import paginated
from .schemas import FarmPatchIn

farms_router = Router(tags=["Farms"])


def _farm_payload(farm, org):
    animals = Animal.objects.filter(farm=farm)
    return {
        "id": farm.id,
        "organization_id": str(org.id),
        "name": farm.name,
        "farm_code": farm.farm_code,
        "status": farm.status,
        "is_primary": farm.is_primary,
        "farm_type": farm.farm_type.name if farm.farm_type_id else None,
        "city": farm.city,
        "location_address": farm.location_address,
        "latitude": farm.latitude,
        "longitude": farm.longitude,
        "country": farm.country.name if farm.country_id else None,
        "state_region": farm.state_region.name if farm.state_region_id else None,
        "counts": {
            "animals": animals.count(),
            "active_animals": animals.filter(status="active").count(),
            "sold": animals.filter(status="sold").count(),
            "dead": animals.filter(status="dead").count(),
            "quarantine": animals.filter(is_quarantine=True).count(),
            "open_tasks": Task.objects.filter(farm=farm)
            .exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
            .count(),
            "open_alerts": Alert.objects.filter(farm=farm, status=Alert.Status.OPEN).count(),
            "housing_units": FarmHousingUnit.objects.filter(farm=farm).count(),
            "farm_units": FarmUnit.objects.filter(farm=farm).count(),
        },
    }


@farms_router.get(
    "/{farm_id}/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Farm profile",
)
def get_farm(request, farm_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    farm = require_farm(org, farm_id, user)
    farm = (
        type(farm)
        .objects.select_related("farm_type", "country", "state_region")
        .get(id=farm.id)
    )
    return 200, success_body(data=_farm_payload(farm, org), message="Farm fetched successfully.")


@farms_router.patch(
    "/{farm_id}/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Update farm profile",
)
def patch_farm(request, farm_id: int, payload: FarmPatchIn):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Farm.UPDATE)
    farm = require_farm(org, farm_id, user)
    if payload.name is not None:
        farm.name = payload.name
    if payload.city is not None:
        farm.city = payload.city
    if payload.location_address is not None:
        farm.location_address = payload.location_address
    if payload.status is not None:
        farm.status = payload.status
    if payload.is_primary is not None:
        farm.is_primary = payload.is_primary
        if payload.is_primary:
            type(farm).objects.filter(organization=org).exclude(id=farm.id).update(is_primary=False)
    farm.save()
    return 200, success_body(data=_farm_payload(farm, org), message="Farm updated successfully.")


@farms_router.get(
    "/{farm_id}/overview/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Farm operational overview",
)
def farm_overview(request, farm_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    farm = require_farm(org, farm_id, user)
    animals = Animal.objects.filter(farm=farm)
    health = animals.values("health_status").annotate(count=Count("id"))
    data = {
        **_farm_payload(farm, org),
        "health_breakdown": {row["health_status"]: row["count"] for row in health},
        "people_count": UserRole.objects.filter(farm=farm).values("user").distinct().count(),
    }
    return 200, success_body(data=data, message="Farm overview fetched successfully.")


@farms_router.get(
    "/{farm_id}/timeline/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Farm timeline",
)
def farm_timeline(request, farm_id: int, page: int = 1, page_size: int = 20, event_type: str = None):
    user = require_user(request)
    org = resolve_organization(user)
    farm = require_farm(org, farm_id, user)
    qs = (
        AnimalEvent.objects.filter(farm=farm)
        .select_related("event_type", "animal")
        .order_by("-event_date", "-id")
    )
    if event_type:
        qs = qs.filter(event_type__name=event_type)
    return 200, paginated(qs, page, page_size, serialize_event, "Timeline fetched successfully.")


@farms_router.get(
    "/{farm_id}/people/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="People assigned to the farm",
)
def farm_people(request, farm_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    farm = require_farm(org, farm_id, user)
    rows = UserRole.objects.filter(Q(farm=farm) | Q(farm__isnull=True, user__organization=org)).select_related(
        "user", "role"
    )
    people = {}
    if org.user_id:
        owner = User.objects.filter(id=org.user_id).first()
        if owner:
            people[str(owner.id)] = {
                "id": str(owner.id),
                "email": owner.email,
                "username": owner.username,
                "is_owner": True,
                "roles": [{"role": "owner", "farm_id": None}],
            }
    for row in rows:
        key = str(row.user_id)
        entry = people.setdefault(
            key,
            {
                "id": key,
                "email": row.user.email,
                "username": row.user.username,
                "is_owner": org.user_id == row.user_id,
                "roles": [],
            },
        )
        entry["roles"].append(
            {
                "role": row.role.name,
                "role_code": row.role.code,
                "farm_id": row.farm_id,
            }
        )
    return 200, success_body(data=list(people.values()), message="People fetched successfully.")


@farms_router.get(
    "/{farm_id}/units/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Farm housing units",
)
def farm_units(request, farm_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    farm = require_farm(org, farm_id, user)
    housing = [
        {
            "id": unit.id,
            "kind": "housing_unit",
            "name": unit.name,
            "status": unit.status,
            "capacity": unit.capacity,
            "occupancy": unit.occupancy,
            "location": unit.location,
        }
        for unit in FarmHousingUnit.objects.filter(farm=farm)
    ]
    units = [
        {
            "id": unit.id,
            "kind": "farm_unit",
            "name": unit.name,
            "code": unit.code,
            "status": unit.status,
            "capacity": unit.capacity,
            "unit_type": unit.unit_type.name if unit.unit_type_id else None,
        }
        for unit in FarmUnit.objects.filter(farm=farm).select_related("unit_type")
    ]
    return 200, success_body(
        data={"housing_units": housing, "farm_units": units},
        message="Units fetched successfully.",
    )


@farms_router.get(
    "/{farm_id}/alerts/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Farm attention alerts (not tasks)",
)
def farm_alerts(request, farm_id: int, page: int = 1, page_size: int = 20, status: str = "open"):
    user = require_user(request)
    org = resolve_organization(user)
    farm = require_farm(org, farm_id, user)
    qs = Alert.objects.filter(farm=farm)
    if status:
        qs = qs.filter(status=status)

    def serialize(alert):
        return {
            "id": alert.id,
            "alert_type": alert.alert_type,
            "priority": alert.priority,
            "title": alert.title,
            "message": alert.message,
            "status": alert.status,
            "due_date": alert.due_date.isoformat() if alert.due_date else None,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
        }

    return 200, paginated(qs, page, page_size, serialize, "Alerts fetched successfully.")
