from uuid import UUID

from django.db.models import Count, Q
from ninja import Router

from account.models import User
from animals.models import Animal, AnimalEvent
from operations.models import Task
from operations.services import serialize_event, work_summary_for
from organization.models import Farm
from role.models import Role

from .authz import (
    is_organization_owner,
    require_organization,
    require_user,
    resolve_organization,
)
from .capabilities import build_capabilities, permission_codes_for_user, user_assignments
from .codes import ErrorCode
from .envelope import V2Error, V2Success, success_body
from .exceptions import ContractError
from .helpers import paginated
from .schemas import OrgPatchIn

orgs_router = Router(tags=["Organizations"])
users_router = Router(tags=["Users"])


def _org_payload(org, user):
    farms = Farm.objects.filter(organization=org)
    people = User.objects.filter(Q(organization=org) | Q(id=org.user_id)).distinct()
    open_tasks = Task.objects.filter(organization=org).exclude(
        status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED]
    )
    animals = Animal.objects.filter(farm__organization=org)
    return {
        "id": str(org.id),
        "name": org.name,
        "code": org.code,
        "status": org.status,
        "industry": org.industry_type.name if org.industry_type_id else None,
        "country": org.country.name if org.country_id else None,
        "state_region": org.state_region.name if org.state_region_id else None,
        "logo": org.logo.url if org.logo else None,
        "is_owner": is_organization_owner(user, org),
        "counts": {
            "farms": farms.count(),
            "people": people.count(),
            "animals": animals.count(),
            "active_animals": animals.filter(status="active").count(),
            "open_tasks": open_tasks.count(),
        },
    }


@users_router.get(
    "/me/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Current user operational profile",
)
def users_me(request):
    user = require_user(request)
    org = resolve_organization(user)
    codes = permission_codes_for_user(user, org)
    data = {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "account_status": user.account_status,
        "is_admin": user.is_superuser,
        "organization": {
            "id": str(org.id),
            "name": org.name,
            "code": org.code,
            "status": org.status,
        },
        "assignments": user_assignments(user, org),
        "permissions": sorted(codes),
        "work_summary": work_summary_for(user, org),
    }
    return 200, success_body(data=data, message="User profile fetched successfully.")


@users_router.get(
    "/me/capabilities/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Role-aware capabilities and navigation",
)
def users_me_capabilities(request):
    user = require_user(request)
    org = resolve_organization(user)
    codes = permission_codes_for_user(user, org)
    data = build_capabilities(user, org, codes)
    return 200, success_body(data=data, message="Capabilities fetched successfully.")


@users_router.get(
    "/me/activity/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Current user activity timeline",
)
def users_me_activity(request, page: int = 1, page_size: int = 20):
    user = require_user(request)
    org = resolve_organization(user)
    qs = (
        AnimalEvent.objects.filter(farm__organization=org, created_by=user)
        .select_related("event_type", "animal", "farm")
        .order_by("-event_date", "-id")
    )
    return 200, paginated(qs, page, page_size, serialize_event, "Activity fetched successfully.")


@users_router.get(
    "/me/tasks/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Tasks assigned to the current user",
)
def users_me_tasks(request, page: int = 1, page_size: int = 20, status: str = None):
    from operations.services import serialize_task

    user = require_user(request)
    org = resolve_organization(user)
    qs = Task.objects.filter(organization=org, assigned_to=user).select_related(
        "animal", "assigned_to", "created_by", "farm"
    )
    if status == "open":
        qs = qs.exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
    elif status:
        qs = qs.filter(status=status)
    return 200, paginated(qs, page, page_size, serialize_task, "Tasks fetched successfully.")


@orgs_router.get(
    "/{organization_id}/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Organization operational profile",
)
def get_organization(request, organization_id: UUID):
    user = require_user(request)
    org = require_organization(user, organization_id)
    org = (
        type(org)
        .objects.select_related("industry_type", "country", "state_region")
        .get(id=org.id)
    )
    return 200, success_body(data=_org_payload(org, user), message="Organization fetched successfully.")


@orgs_router.patch(
    "/{organization_id}/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Update organization profile",
)
def patch_organization(request, organization_id: UUID, payload: OrgPatchIn):
    user = require_user(request)
    org = require_organization(user, organization_id)
    if not is_organization_owner(user, org):
        raise ContractError(403, ErrorCode.PERMISSION_DENIED, "Only the organization owner can update this profile.")
    if payload.name:
        org.name = payload.name
    if payload.status:
        if payload.status not in dict(org.STATUS_CHOICES):
            raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Invalid organization status.")
        org.status = payload.status
    org.save()
    return 200, success_body(data=_org_payload(org, user), message="Organization updated successfully.")


@orgs_router.get(
    "/{organization_id}/summary/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Organization summary counts",
)
def organization_summary(request, organization_id: UUID):
    user = require_user(request)
    org = require_organization(user, organization_id)
    animals = Animal.objects.filter(farm__organization=org)
    farms = Farm.objects.filter(organization=org)
    data = {
        "organization_id": str(org.id),
        "farms": farms.count(),
        "animals": {
            "total": animals.count(),
            "active": animals.filter(status="active").count(),
            "sold": animals.filter(status="sold").count(),
            "dead": animals.filter(status="dead").count(),
            "quarantine": animals.filter(is_quarantine=True).count(),
            "pregnant": animals.filter(is_pregnant=True).count(),
        },
        "open_tasks": Task.objects.filter(organization=org)
        .exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
        .count(),
        "roles": Role.objects.filter(organization=org).count(),
        "people": User.objects.filter(Q(organization=org) | Q(id=org.user_id)).distinct().count(),
    }
    return 200, success_body(data=data, message="Organization summary fetched successfully.")


@orgs_router.get(
    "/{organization_id}/activity/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Organization activity timeline",
)
def organization_activity(request, organization_id: UUID, page: int = 1, page_size: int = 20):
    user = require_user(request)
    org = require_organization(user, organization_id)
    qs = (
        AnimalEvent.objects.filter(farm__organization=org)
        .select_related("event_type", "animal", "farm")
        .order_by("-event_date", "-id")
    )
    return 200, paginated(qs, page, page_size, serialize_event, "Activity fetched successfully.")


@orgs_router.get(
    "/{organization_id}/farms/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Farms in the organization",
)
def organization_farms(request, organization_id: UUID, page: int = 1, page_size: int = 20):
    user = require_user(request)
    org = require_organization(user, organization_id)

    def serialize(farm):
        counts = Animal.objects.filter(farm=farm).aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(status="active")),
        )
        return {
            "id": farm.id,
            "name": farm.name,
            "farm_code": farm.farm_code,
            "status": farm.status,
            "is_primary": farm.is_primary,
            "farm_type": farm.farm_type.name if farm.farm_type_id else None,
            "city": farm.city,
            "animal_count": counts["total"],
            "active_animals": counts["active"],
        }

    qs = Farm.objects.filter(organization=org).select_related("farm_type").order_by("-is_primary", "name")
    return 200, paginated(qs, page, page_size, serialize, "Farms fetched successfully.")
