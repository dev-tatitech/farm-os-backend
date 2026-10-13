from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone
from ninja import Router

from animals.models import Animal, AnimalGroup, AnimalGroupMember, AnimalProfileAttribute
from organization.models import Farm
from common.mutations import atomic_mutation
from common.permissions import Permissions
from operations.services import emit_event

from .authz import require_farm, require_permission, require_user, resolve_organization
from .codes import ErrorCode
from .envelope import V2Error, V2Success, success_body
from .exceptions import ContractError
from .helpers import paginated
from .schemas import GroupCreateIn, GroupPatchIn


groups_router = Router(tags=["Groups"])


def _group(org, user, group_id):
    try:
        row = AnimalGroup.objects.select_related("farm").get(id=group_id, farm__organization=org)
    except AnimalGroup.DoesNotExist:
        raise ContractError(404, ErrorCode.GROUP_NOT_FOUND, "Group could not be found.")
    require_farm(org, row.farm_id, user)
    return row


def _serialize(row):
    count = getattr(row, "active_member_count", None)
    if count is None:
        count = row.members.filter(status=AnimalGroupMember.Status.ACTIVE).count()
    return {
        "id": row.id,
        "farm_id": row.farm_id,
        "name": row.name,
        "description": row.description or "",
        "status": row.status,
        "member_count": count,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@groups_router.get("/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 422: V2Error})
def list_groups(request, farm_id: int, page: int = 1, page_size: int = 20,
                status: str = None, include_inactive: bool = False, search: str = None):
    user = require_user(request); org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.VIEW)
    farm = require_farm(org, farm_id, user)
    qs = AnimalGroup.objects.filter(farm=farm).annotate(
        active_member_count=Count("members", filter=Q(members__status=AnimalGroupMember.Status.ACTIVE))
    )
    normalized_status = status.casefold() if status else ("all" if include_inactive else "active")
    if normalized_status == "active":
        qs = qs.filter(status=AnimalGroup.Status.ACTIVE)
    elif normalized_status == "inactive":
        qs = qs.filter(status=AnimalGroup.Status.INACTIVE)
    elif normalized_status != "all":
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "status must be active, inactive, or all.", errors={"status": status})
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
    return 200, paginated(qs.order_by("name", "id"), page, page_size, _serialize, "Groups fetched successfully.")


@groups_router.get("/{group_id}/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error})
def group_detail(request, group_id: int):
    user = require_user(request); org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.VIEW)
    row = _group(org, user, group_id)
    return 200, success_body(data=_serialize(row), message="Group fetched successfully.")


@groups_router.get("/{group_id}/members/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error})
def group_members(request, group_id: int, page: int = 1, page_size: int = 50,
                  include_removed: bool = False, search: str = None,
                  livestock_species_id: int = None, livestock_breed_id: int = None,
                  gender: str = None, lifecycle_status: str = None):
    user = require_user(request); org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.VIEW)
    group = _group(org, user, group_id)
    qs = group.members.select_related(
        "animal", "animal__livestock_species", "animal__livestock_breed",
        "animal__species", "animal__breed", "animal__housing_unit",
    ).order_by("animal__tag_id", "id")
    if not include_removed:
        qs = qs.filter(status=AnimalGroupMember.Status.ACTIVE)
    if search:
        name_match = AnimalProfileAttribute.objects.filter(
            animal_id=OuterRef("animal_id"),
            attribute_key__in=("name", "display_name", "animal_name"),
            attribute_value__icontains=search,
        )
        qs = qs.annotate(_name_match=Exists(name_match)).filter(
            Q(animal__tag_id__icontains=search)
            | Q(animal__notes__icontains=search)
            | Q(_name_match=True)
        )
    if livestock_species_id is not None:
        qs = qs.filter(Q(animal__livestock_species_id=livestock_species_id)
                       | Q(animal__livestock_species__isnull=True, animal__species__id=livestock_species_id))
    if livestock_breed_id is not None:
        qs = qs.filter(Q(animal__livestock_breed_id=livestock_breed_id)
                       | Q(animal__livestock_breed__isnull=True, animal__breed__id=livestock_breed_id))
    if gender:
        qs = qs.filter(animal__gender=gender)
    if lifecycle_status:
        qs = qs.filter(animal__status=lifecycle_status)
    from .animals import serialize_animal_card
    return 200, paginated(qs, page, page_size, lambda row: {"membership_id": row.id, "animal_id": row.animal_id,
        "tag_id": row.animal.tag_id, "joined_at": row.joined_at.isoformat(),
        "removed_at": row.removed_at.isoformat() if row.removed_at else None,
        "status": row.status, "animal": serialize_animal_card(row.animal)}, "Group members fetched successfully.")


@groups_router.post("/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error, 422: V2Error})
@atomic_mutation
def create_group(request, payload: GroupCreateIn):
    user = require_user(request); org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.CREATE)
    farm = require_farm(org, payload.farm_id, user)
    farm = Farm.objects.select_for_update().get(pk=farm.pk)
    name = payload.name.strip()
    if not name:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Group name is required.", errors={"name": "required"})
    if AnimalGroup.objects.filter(farm=farm, name__iexact=name).exists():
        raise ContractError(409, ErrorCode.CONFLICT, "A group with this name already exists.")
    row = AnimalGroup.objects.create(farm=farm, name=name, description=payload.description or "")
    emit_event(farm, "group_created", "Group created", row.name, "animal_group", row.id, user, group=row)
    return 200, success_body(data=_serialize(row), message="Group created successfully.")


@groups_router.patch("/{group_id}/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error, 422: V2Error})
@atomic_mutation
def patch_group(request, group_id: int, payload: GroupPatchIn):
    user = require_user(request); org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.UPDATE)
    row = _group(org, user, group_id)
    Farm.objects.select_for_update().get(pk=row.farm_id)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Group name is required.", errors={"name": "required"})
        if AnimalGroup.objects.filter(farm=row.farm, name__iexact=name).exclude(pk=row.pk).exists():
            raise ContractError(409, ErrorCode.CONFLICT, "A group with this name already exists.")
        row.name = name
    if payload.description is not None:
        row.description = payload.description
    if payload.is_active is not None:
        row.status = AnimalGroup.Status.ACTIVE if payload.is_active else AnimalGroup.Status.INACTIVE
    row.save()
    emit_event(row.farm, "group_updated", "Group updated", row.name, "animal_group", row.id, user, group=row)
    return 200, success_body(data=_serialize(row), message="Group updated successfully.")


@groups_router.post("/{group_id}/members/{animal_id}/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error})
@atomic_mutation
def add_member(request, group_id: int, animal_id: int):
    user = require_user(request); org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.UPDATE)
    group = _group(org, user, group_id)
    try:
        animal = Animal.objects.get(id=animal_id, farm=group.farm)
    except Animal.DoesNotExist:
        raise ContractError(404, ErrorCode.ANIMAL_NOT_FOUND, "Animal could not be found.")
    if group.status != AnimalGroup.Status.ACTIVE:
        raise ContractError(422, ErrorCode.TARGET_NOT_ELIGIBLE, "Inactive groups cannot receive members.")
    with transaction.atomic():
        if AnimalGroupMember.objects.select_for_update().filter(group=group, animal=animal, status=AnimalGroupMember.Status.ACTIVE).exists():
            raise ContractError(409, ErrorCode.CONFLICT, "Animal is already an active member of this group.")
        membership = AnimalGroupMember.objects.create(group=group, animal=animal)
    emit_event(group.farm, "group_membership_added", "Animal added to group", group.name, "animal_group_member", membership.id, user, animal=animal, group=group)
    return 200, success_body(data={"id": membership.id, "animal_id": animal.id, "group_id": group.id, "joined_at": membership.joined_at.isoformat()}, message="Animal added to group successfully.")


@groups_router.delete("/{group_id}/members/{animal_id}/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error})
@atomic_mutation
def remove_member(request, group_id: int, animal_id: int):
    user = require_user(request); org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.UPDATE)
    group = _group(org, user, group_id)
    try:
        membership = AnimalGroupMember.objects.get(group=group, animal_id=animal_id, status=AnimalGroupMember.Status.ACTIVE)
    except AnimalGroupMember.DoesNotExist:
        raise ContractError(404, ErrorCode.ANIMAL_NOT_FOUND, "Current group membership could not be found.")
    membership.status = AnimalGroupMember.Status.REMOVED; membership.removed_at = timezone.now(); membership.save(update_fields=["status", "removed_at"])
    emit_event(group.farm, "group_membership_removed", "Animal removed from group", group.name, "animal_group_member", membership.id, user, animal=membership.animal, group=group)
    return 200, success_body(data={"id": membership.id, "removed_at": membership.removed_at.isoformat()}, message="Animal removed from group successfully.")
