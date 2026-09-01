from django.core.exceptions import ValidationError
from ninja import Router

from animals.models import Animal
from common.permissions import Permissions
from reproduction.models import BirthOffspringRecord, BirthRecord

from .authz import require_animal, require_farm, require_permission, require_user, resolve_organization
from .codes import ErrorCode
from .envelope import V2Error, V2Success, success_body
from .exceptions import ContractError
from .helpers import begin_idempotency, store_idempotency
from .schemas import BirthCreateIn, BirthRegisterOffspringIn

births_router = Router(tags=["Reproduction"])


def _serialize_slot(row: BirthOffspringRecord) -> dict:
    return {
        "id": row.id,
        "birth_id": row.birth_record_id,
        "offspring_sequence": row.offspring_sequence,
        "registration_status": row.registration_status,
        "animal_id": row.offspring_animal_id,
        "tag_id": row.offspring_animal.tag_id if row.offspring_animal_id else None,
        "gender": row.gender or None,
    }


def _serialize_birth(birth: BirthRecord) -> dict:
    slots = list(birth.offspring_records.order_by("offspring_sequence"))
    return {
        "id": birth.id,
        "farm_id": birth.farm_id,
        "mother_id": birth.mother_id,
        "birth_date": birth.birth_date.isoformat() if birth.birth_date else None,
        "total_offspring": birth.number_of_offspring,
        "alive": birth.number_alive,
        "dead": birth.number_dead,
        "pending_offspring_registration": birth.pending_offspring_registration,
        "registered": birth.offspring_records.filter(registration_status="registered").count(),
        "notes": birth.notes,
        "offspring": [_serialize_slot(row) for row in slots],
    }


def _get_birth(org, birth_id, farm=None) -> BirthRecord:
    try:
        birth = BirthRecord.objects.select_related("mother", "farm").get(
            id=birth_id, farm__organization=org
        )
    except BirthRecord.DoesNotExist:
        raise ContractError(404, ErrorCode.ANIMAL_NOT_FOUND, "Birth record could not be found.")
    if farm and birth.farm_id != farm.id:
        raise ContractError(404, ErrorCode.ANIMAL_NOT_FOUND, "Birth record could not be found.")
    return birth


@births_router.post(
    "/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 422: V2Error},
    summary="Record a birth with live offspring registration slots",
)
def create_birth(request, payload: BirthCreateIn):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Reproduction.CREATE)
    key, cached = begin_idempotency(user, request, payload)
    if cached:
        return cached
    farm = require_farm(org, payload.farm_id, user)
    mother = require_animal(org, payload.mother_id, farm)
    birth = BirthRecord(
        farm=farm,
        mother=mother,
        birth_date=payload.birth_date,
        number_of_offspring=payload.number_of_offspring,
        number_alive=payload.number_alive,
        number_dead=payload.number_dead,
        notes=payload.notes or "",
        created_by=user,
    )
    try:
        birth.save()
        mother.set_lactating()
    except ValidationError as exc:
        raise ContractError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Birth record is invalid.",
            errors=getattr(exc, "message_dict", {"details": getattr(exc, "messages", [str(exc)])}),
        )
    body = success_body(data=_serialize_birth(birth), message="Birth recorded successfully.")
    store_idempotency(user, key, 200, body)
    return 200, body


@births_router.get(
    "/{birth_id}/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Birth record and offspring registration slots",
)
def birth_detail(request, birth_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Reproduction.VIEW, Permissions.Reproduction.CREATE)
    birth = _get_birth(org, birth_id)
    require_farm(org, birth.farm_id, user)
    return 200, success_body(data=_serialize_birth(birth), message="Birth fetched successfully.")


@births_router.post(
    "/{birth_id}/register-offspring/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error, 422: V2Error},
    summary="Register one live offspring against a birth slot",
)
def register_offspring(request, birth_id: int, payload: BirthRegisterOffspringIn):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.CREATE, Permissions.Reproduction.CREATE)
    key, cached = begin_idempotency(user, request, payload)
    if cached:
        return cached
    birth = _get_birth(org, birth_id)
    require_farm(org, birth.farm_id, user)
    slots = birth.offspring_records.filter(registration_status="registration_required").order_by(
        "offspring_sequence"
    )
    if payload.offspring_sequence:
        slot = slots.filter(offspring_sequence=payload.offspring_sequence).first()
    else:
        slot = slots.first()
    if not slot:
        raise ContractError(
            409,
            ErrorCode.DUPLICATE_RECORD,
            "No live offspring registration slots remain.",
        )
    if payload.tag_id and Animal.objects.filter(tag_id__iexact=payload.tag_id).exists():
        raise ContractError(409, ErrorCode.DUPLICATE_RECORD, "Tag ID already exists.")
    from contract.animals import _internal_tag

    animal = Animal(
        user=user,
        farm=birth.farm,
        tag_id=payload.tag_id or _internal_tag(),
        gender=payload.gender,
        source_type="born",
        status="active",
        mother=birth.mother,
        dob=birth.birth_date,
        notes="",
    )
    if payload.livestock_species_id:
        animal.livestock_species_id = payload.livestock_species_id
    if payload.livestock_breed_id:
        animal.livestock_breed_id = payload.livestock_breed_id
    try:
        animal.save()
    except ValidationError as exc:
        raise ContractError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Offspring animal could not be created.",
            errors=getattr(exc, "message_dict", {"details": getattr(exc, "messages", [str(exc)])}),
        )
    slot.offspring_animal = animal
    slot.registration_status = "registered"
    slot.gender = payload.gender
    if payload.birth_weight is not None:
        slot.birth_weight = payload.birth_weight
    slot.save()
    body = success_body(
        data={"animal_id": animal.id, "birth": _serialize_birth(birth)},
        message="Offspring registered successfully.",
    )
    store_idempotency(user, key, 200, body)
    return 200, body
