from ninja import Router

from animals.models import Animal, AnimalLabel, FarmLabel
from common.mutations import atomic_mutation
from common.permissions import Permissions
from operations.services import emit_event

from .authz import require_farm, require_permission, require_user, resolve_organization
from .codes import ErrorCode
from .envelope import V2Error, V2Success, success_body
from .exceptions import ContractError
from .helpers import paginated
from .schemas import LabelCreateIn, LabelPatchIn


settings_router = Router(tags=["Farm Settings"])

# Labels classify operationally; authoritative domain states are never labels.
RESERVED_STATE_LABELS = {"dead", "deceased", "sick", "pregnant", "quarantine", "isolated", "sold", "transferred"}


def _label(org, user, label_id):
    try:
        label = FarmLabel.objects.select_related("farm").get(id=label_id, farm__organization=org)
    except FarmLabel.DoesNotExist:
        raise ContractError(404, ErrorCode.LABEL_NOT_FOUND, "Label could not be found.")
    require_farm(org, label.farm_id, user)
    return label


def _serialize_label(label):
    return {"id": label.id, "farm_id": label.farm_id, "name": label.name, "color": label.color, "description": label.description, "is_active": label.is_active}


@settings_router.get("/labels/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error})
def list_labels(request, farm_id: int, page: int = 1, page_size: int = 50, include_inactive: bool = False):
    user = require_user(request); org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.VIEW)
    farm = require_farm(org, farm_id, user)
    qs = FarmLabel.objects.filter(farm=farm)
    if not include_inactive: qs = qs.filter(is_active=True)
    return 200, paginated(qs, page, page_size, _serialize_label, "Labels fetched successfully.")


@settings_router.post("/labels/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error, 422: V2Error})
@atomic_mutation
def create_label(request, payload: LabelCreateIn):
    user = require_user(request); org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.UPDATE)
    farm = require_farm(org, payload.farm_id, user)
    name = payload.name.strip()
    if not name or name.casefold() in RESERVED_STATE_LABELS:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Labels cannot represent authoritative animal states.")
    if FarmLabel.objects.filter(farm=farm, name__iexact=name).exists(): raise ContractError(409, ErrorCode.CONFLICT, "A label with this name already exists.")
    label = FarmLabel.objects.create(farm=farm, name=name, color=payload.color or "", description=payload.description or "")
    emit_event(farm, "label_created", "Farm label created", name, "farm_label", label.id, user)
    return 200, success_body(data=_serialize_label(label), message="Label created successfully.")


@settings_router.patch("/labels/{label_id}/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 422: V2Error})
@atomic_mutation
def patch_label(request, label_id: int, payload: LabelPatchIn):
    user = require_user(request); org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.UPDATE)
    label = _label(org, user, label_id)
    if payload.name is not None:
        name = payload.name.strip()
        if not name or name.casefold() in RESERVED_STATE_LABELS: raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Labels cannot represent authoritative animal states.")
        label.name = name
    for field in ("color", "description", "is_active"):
        value = getattr(payload, field)
        if value is not None: setattr(label, field, value)
    label.save(); emit_event(label.farm, "label_updated", "Farm label updated", label.name, "farm_label", label.id, user)
    return 200, success_body(data=_serialize_label(label), message="Label updated successfully.")


@settings_router.post("/animals/{animal_id}/labels/{label_id}/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error})
@atomic_mutation
def assign_label(request, animal_id: int, label_id: int):
    user = require_user(request); org = resolve_organization(user); require_permission(user, org, Permissions.Animal.UPDATE)
    label = _label(org, user, label_id)
    try: animal = Animal.objects.get(id=animal_id, farm=label.farm)
    except Animal.DoesNotExist: raise ContractError(404, ErrorCode.ANIMAL_NOT_FOUND, "Animal could not be found.")
    row, created = AnimalLabel.objects.get_or_create(animal=animal, label=label, defaults={"assigned_by": user})
    if not created: raise ContractError(409, ErrorCode.CONFLICT, "Label is already assigned to this animal.")
    emit_event(label.farm, "label_assigned", "Label assigned", label.name, "animal_label", row.id, user, animal=animal)
    return 200, success_body(data={"id": row.id, "animal_id": animal.id, "label": _serialize_label(label)}, message="Label assigned successfully.")


@settings_router.get("/animals/{animal_id}/labels/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error})
def list_animal_labels(request, animal_id: int):
    user = require_user(request); org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.VIEW)
    try: animal = Animal.objects.get(id=animal_id, farm__organization=org)
    except Animal.DoesNotExist: raise ContractError(404, ErrorCode.ANIMAL_NOT_FOUND, "Animal could not be found.")
    require_farm(org, animal.farm_id, user)
    labels = AnimalLabel.objects.filter(animal=animal, label__is_active=True).select_related("label")
    return 200, success_body(data=[_serialize_label(row.label) for row in labels.order_by("label__name", "label_id")], message="Animal labels fetched successfully.")


@settings_router.delete("/animals/{animal_id}/labels/{label_id}/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error})
@atomic_mutation
def unassign_label(request, animal_id: int, label_id: int):
    user = require_user(request); org = resolve_organization(user); require_permission(user, org, Permissions.Animal.UPDATE)
    label = _label(org, user, label_id)
    try: row = AnimalLabel.objects.get(animal_id=animal_id, animal__farm=label.farm, label=label)
    except AnimalLabel.DoesNotExist: raise ContractError(404, ErrorCode.LABEL_NOT_FOUND, "Label assignment could not be found.")
    emit_event(label.farm, "label_removed", "Label removed", label.name, "animal_label", row.id, user, animal=row.animal)
    row.delete()
    return 200, success_body(data={"animal_id": animal_id, "label_id": label_id}, message="Label removed successfully.")
