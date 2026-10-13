from common.mutations import atomic_mutation
from common.access import authorized_farms
import uuid
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from ninja import File, Router, UploadedFile

from admin_panel.models import FarmHousingUnit, LivestockBreed, LivestockSpecies
from animals.models import Animal, AnimalEvent, AnimalMedia, MilkRecord
from common.permissions import Permissions
from feed.models import FeedIssuanceRecord
from health.models import TreatmentRecord, VaccinationRecord
from movement_records.models import MovementRecord
from movement_records.sale_readiness import evaluate_sale_readiness
from operations.models import Task
from operations.services import serialize_event, serialize_task
from reproduction.models import InseminationRecord, PregnancyRecord

from .authz import require_animal, require_farm, require_permission, require_user, resolve_organization
from .codes import ErrorCode
from .envelope import V2Error, V2Success, success_body
from .exceptions import ContractError
from .helpers import begin_idempotency, paginated, store_idempotency
from .schemas import AnimalCreateIn, AnimalPatchIn

animals_router = Router(tags=["Animals"])

ALLOWED_CREATE_STATUSES = ("active", "sold", "dead", "transferred_out", "culled")
ACTIVE_POPULATION = ("active",)


def _age_months(animal):
    today = timezone.localdate()
    if animal.dob:
        from dateutil.relativedelta import relativedelta as rdelta

        diff = rdelta(today, animal.dob)
        return diff.years * 12 + diff.months
    return animal.estimated_age_months or 0


def _internal_tag():
    return f"INT-{uuid.uuid4().hex[:12].upper()}"


def profile_completion(animal):
    """Central, deterministic completion projection for web and mobile."""
    fields = [
        ("tag_id", "Identification tag", bool(animal.tag_id)),
        ("species", "Species", bool(animal.livestock_species_id or animal.species_id)),
        ("breed", "Breed", bool(animal.livestock_breed_id or animal.breed_id)),
        ("date_of_birth", "Date of birth", bool(animal.dob or animal.estimated_age_months is not None)),
        ("housing_unit", "Housing unit", bool(animal.housing_unit_id or animal.unit_id)),
        ("source_type", "Source", bool(animal.source_type)),
    ]
    missing = [{"key": key, "label": label} for key, label, present in fields if not present]
    total = len(fields); completed = total - len(missing)
    return {"percentage": round(completed * 100 / total) if total else 100, "completed": completed, "total_applicable": total, "missing": missing}


def _media_payload(row):
    return {"id": row.id, "url": row.file.url if row.file else None, "note": row.note, "is_primary": row.is_primary, "captured_at": row.captured_at.isoformat() if row.captured_at else None, "uploaded_at": row.created_at.isoformat()}


def _preserve_legacy_primary(animal, user):
    """Attach the pre-gallery profile file to history before replacing it."""
    if not animal.image or animal.media.filter(file=animal.image.name).exists():
        return None
    return AnimalMedia.objects.create(animal=animal, file=animal.image.name,
        note="Previous profile photo", is_primary=False, uploaded_by=user)


def serialize_animal_card(animal):
    from .animal_query import animal_display_name

    species_name = (
        animal.livestock_species.name
        if animal.livestock_species
        else (animal.species.name if animal.species else None)
    )
    breed_name = (
        animal.livestock_breed.name
        if animal.livestock_breed
        else (animal.breed.name if animal.breed else None)
    )
    housing = None
    if animal.housing_unit_id:
        housing = {"id": animal.housing_unit_id, "name": animal.housing_unit.name}
    return {
        "id": animal.id,
        "tag_id": animal.tag_id or None,
        "name": animal_display_name(animal),
        "farm_id": animal.farm_id,
        "species": species_name,
        "breed": breed_name,
        "gender": animal.gender,
        "age_months": _age_months(animal),
        "lifecycle_status": animal.status,
        "health_status": animal.health_status,
        "housing_unit": housing,
        "flags": {
            "is_pregnant": animal.is_pregnant,
            "is_lactating": animal.is_lactating,
            "is_quarantine": animal.is_quarantine,
            "needs_attention": animal.health_status in ("sick", "at_risk") or animal.is_quarantine,
            "is_active": animal.status == "active",
            "_mutability": "read_only_derived",
        },
        "image_url": animal.image.url if animal.image else None,
        "profile_completion": profile_completion(animal),
    }


def build_animal_profile(animal):
    today = timezone.localdate()
    if animal.dob:
        from dateutil.relativedelta import relativedelta as rdelta

        diff = rdelta(today, animal.dob)
        age_months = diff.years * 12 + diff.months
    else:
        age_months = animal.estimated_age_months or 0

    species_name = (
        animal.livestock_species.name
        if animal.livestock_species
        else (animal.species.name if animal.species else None)
    )
    breed_name = (
        animal.livestock_breed.name
        if animal.livestock_breed
        else (animal.breed.name if animal.breed else None)
    )
    unit_name = (
        animal.housing_unit.name
        if animal.housing_unit
        else (animal.unit.name if animal.unit else None)
    )
    last_insemination = (
        InseminationRecord.objects.filter(animal=animal)
        .order_by("-service_date")
        .values("service_date", "method")
        .first()
    )
    pregnancy = (
        PregnancyRecord.objects.filter(animal=animal)
        .order_by("-check_date")
        .values("result", "expected_delivery_date")
        .first()
    )
    if animal.is_lactating:
        preg_status = "Lactating"
    elif animal.is_pregnant:
        preg_status = "Pregnant"
    else:
        preg_status = "Not Pregnant"
    last_vaccination = (
        VaccinationRecord.objects.filter(animal=animal)
        .order_by("-date_given")
        .values("vaccine_name", "date_given", "next_due_date")
        .first()
    )
    last_treatment = (
        TreatmentRecord.objects.filter(animal=animal)
        .order_by("-treatment_date")
        .values("diagnosis", "treatment_date", "severity")
        .first()
    )
    last_feed = (
        FeedIssuanceRecord.objects.filter(animal=animal)
        .order_by("-issue_date")
        .values("issue_date", "quantity_issued")
        .first()
    )
    last_movement = (
        MovementRecord.objects.filter(animal=animal)
        .select_related("from_housing_unit", "to_housing_unit", "from_unit", "to_unit")
        .order_by("-move_date")
        .first()
    )
    milk_today = (
        MilkRecord.objects.filter(animal=animal, record_date=today).aggregate(total=Sum("quantity"))["total"]
        or 0
    )
    open_tasks = list(
        Task.objects.filter(animal=animal)
        .exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
        .select_related("assigned_to")[:10]
    )
    readiness = evaluate_sale_readiness(animal, farm=animal.farm)
    return {
        "id": animal.id,
        "tag_id": animal.tag_id,
        "lifecycle_status": animal.status,
        "status": animal.status,
        "health_status": animal.health_status,
        "flags": {
            "is_pregnant": animal.is_pregnant,
            "is_lactating": animal.is_lactating,
            "is_quarantine": animal.is_quarantine,
            "needs_attention": animal.health_status in ("sick", "at_risk") or animal.is_quarantine,
            "is_active": animal.status == "active",
            "is_breeding_restricted": animal.is_breeding_restricted,
            "_mutability": "read_only_derived",
        },
        "card": {
            "id": animal.id,
            "tag_id": animal.tag_id,
            "species": species_name,
            "breed": breed_name,
            "gender": animal.gender,
            "lifecycle_status": animal.status,
            "status": animal.status,
            "age_months": age_months,
            "housing_unit": unit_name,
            "image_url": animal.image.url if animal.image else None,
        },
        "overview": {
            "species": species_name,
            "livestock_species_id": animal.livestock_species_id,
            "breed": breed_name,
            "livestock_breed_id": animal.livestock_breed_id,
            "housing_unit": unit_name,
            "housing_unit_id": animal.housing_unit_id,
            "farm_id": animal.farm_id,
            "farm": animal.farm.name,
            "mother_tag": animal.mother.tag_id if animal.mother else None,
            "source": animal.get_source_type_display(),
            "entry_date": animal.created_at.date().isoformat() if animal.created_at else None,
        },
        "reproduction": {
            "last_insemination_date": last_insemination["service_date"] if last_insemination else None,
            "expected_delivery_date": pregnancy["expected_delivery_date"] if pregnancy else None,
            "pregnancy_status": preg_status,
        },
        "production": {
            "lactation_status": "Lactating" if animal.is_lactating else "Not Lactating",
            "milk_production_today": milk_today,
        },
        "health": {
            "health_status": animal.health_status,
            "is_quarantine": animal.is_quarantine,
            "last_vaccination": last_vaccination,
            "last_treatment": last_treatment,
        },
        "feeding": {"last_feed_issuance": last_feed},
        "movement": {
            "last_move_date": last_movement.move_date if last_movement else None,
            "from_unit": (
                (
                    last_movement.from_housing_unit.name
                    if last_movement.from_housing_unit
                    else None
                )
                or (last_movement.from_unit.name if last_movement.from_unit else None)
            )
            if last_movement
            else None,
            "to_unit": (
                (
                    last_movement.to_housing_unit.name
                    if last_movement.to_housing_unit
                    else None
                )
                or (last_movement.to_unit.name if last_movement.to_unit else None)
            )
            if last_movement
            else None,
        },
        "sale_readiness": readiness,
        "profile_completion": profile_completion(animal),
        "open_tasks": [serialize_task(task) for task in open_tasks],
    }


@animals_router.get(
    "/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 422: V2Error},
    summary="List animals (card records)",
)
def list_animals(
    request,
    page: int = 1,
    page_size: int = 20,
    farm_id: int = None,
    search: str = None,
    livestock_species_id: int = None,
    livestock_breed_id: int = None,
    gender: str = None,
    lifecycle_status: str = None,
    health_status: str = None,
    housing_unit_id: int = None,
    group_id: int = None,
    is_pregnant: bool = None,
    is_lactating: bool = None,
    is_quarantine: bool = None,
    needs_attention: bool = None,
    label_id: int = None,
    profile_incomplete: bool = None,
    open_observation: bool = None,
    open_health_case: bool = None,
    age_min_months: int = None,
    age_max_months: int = None,
    sort: str = "-id",
):
    user = require_user(request)
    org = resolve_organization(user)
    from .animal_query import query_animals
    return 200, query_animals(user, org, page=page, page_size=page_size, farm_id=farm_id,
        search=search, livestock_species_id=livestock_species_id, livestock_breed_id=livestock_breed_id,
        gender=gender, lifecycle_status=lifecycle_status, health_status=health_status,
        housing_unit_id=housing_unit_id, group_id=group_id, is_pregnant=is_pregnant,
        is_lactating=is_lactating, is_quarantine=is_quarantine, needs_attention=needs_attention,
        label_id=label_id, profile_incomplete=profile_incomplete, open_observation=open_observation,
        open_health_case=open_health_case, age_min_months=age_min_months, age_max_months=age_max_months, sort=sort)


@animals_router.patch(
    "/{animal_id}/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error, 422: V2Error},
    summary="Partial animal update",
)
@atomic_mutation
def patch_animal(request, animal_id: int, payload: AnimalPatchIn):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.UPDATE)
    animal = require_animal(org, animal_id)
    require_farm(org, animal.farm_id, user)
    forbidden = {
        "is_pregnant": payload.is_pregnant,
        "is_lactating": payload.is_lactating,
        "is_quarantine": payload.is_quarantine,
        "needs_attention": payload.needs_attention,
        "is_active": payload.is_active,
        "status": payload.status,
        "lifecycle_status": payload.lifecycle_status,
    }
    sent = {key: value for key, value in forbidden.items() if value is not None}
    if sent:
        raise ContractError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Animal condition flags and lifecycle status are read-only derived state. "
            "Change them through the domain workflow (pregnancy check, quarantine, mortality, sale).",
            errors=sent,
        )
    if animal.status in ("dead", "sold"):
        code = ErrorCode.ANIMAL_ALREADY_DECEASED if animal.status == "dead" else ErrorCode.ANIMAL_ALREADY_SOLD
        raise ContractError(409, code, "Exited animals cannot be updated through generic PATCH.")
    if payload.tag_id:
        if Animal.objects.filter(tag_id__iexact=payload.tag_id).exclude(id=animal.id).exists():
            raise ContractError(409, ErrorCode.DUPLICATE_RECORD, "Tag ID already exists.")
        animal.tag_id = payload.tag_id
    if payload.notes is not None:
        animal.notes = payload.notes
    if payload.gender:
        animal.gender = payload.gender
    if payload.dob is not None:
        animal.dob = payload.dob
    if payload.estimated_age_months is not None:
        animal.estimated_age_months = payload.estimated_age_months
    if payload.livestock_species_id:
        try:
            animal.livestock_species = LivestockSpecies.objects.get(
                id=payload.livestock_species_id, is_active=True
            )
        except LivestockSpecies.DoesNotExist:
            raise ContractError(422, ErrorCode.INVALID_SPECIES, "Species could not be found.")
    if payload.livestock_breed_id:
        try:
            breed = LivestockBreed.objects.get(id=payload.livestock_breed_id, is_active=True)
        except LivestockBreed.DoesNotExist:
            raise ContractError(422, ErrorCode.INVALID_BREED, "Breed could not be found.")
        animal.livestock_breed = breed
    if payload.housing_unit_id:
        try:
            animal.housing_unit = FarmHousingUnit.objects.get(
                id=payload.housing_unit_id, farm=animal.farm, status="active"
            )
        except FarmHousingUnit.DoesNotExist:
            raise ContractError(422, ErrorCode.INVALID_HOUSING_UNIT, "Housing unit could not be found.")
    try:
        animal.save()
    except ValidationError as exc:
        raise ContractError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Animal could not be updated.",
            errors=getattr(exc, "message_dict", {"details": getattr(exc, "messages", [str(exc)])}),
        )
    return 200, success_body(data=build_animal_profile(animal), message="Animal updated successfully.")


@animals_router.get(
    "/{animal_id}/profile/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Animal operational profile",
)
def animal_profile(request, animal_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.VIEW)
    animal = require_animal(org, animal_id)
    require_farm(org, animal.farm_id, user)
    return 200, success_body(
        data=build_animal_profile(animal), message="Animal profile fetched successfully."
    )


@animals_router.get("/{animal_id}/media/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error}, summary="List animal gallery")
def list_animal_media(request, animal_id: int, page: int = 1, page_size: int = 30):
    user = require_user(request); org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.VIEW)
    animal = require_animal(org, animal_id); require_farm(org, animal.farm_id, user)
    return 200, paginated(animal.media.all(), page, page_size, _media_payload, "Animal media fetched successfully.")


@animals_router.post("/{animal_id}/media/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 422: V2Error}, summary="Upload animal gallery image")
@atomic_mutation
def upload_animal_media(request, animal_id: int, file: UploadedFile = File(...), note: str = "", make_primary: bool = False, captured_at: datetime | None = None):
    user = require_user(request); org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.UPDATE)
    animal = require_animal(org, animal_id); require_farm(org, animal.farm_id, user)
    if not (file.content_type or "").startswith("image/"):
        raise ContractError(422, ErrorCode.INVALID_FILE_TYPE, "Only image uploads are supported.")
    with transaction.atomic():
        if make_primary or not animal.media.filter(is_primary=True).exists():
            _preserve_legacy_primary(animal, user)
            animal.media.filter(is_primary=True).update(is_primary=False)
            make_primary = True
        row = AnimalMedia.objects.create(animal=animal, file=file, note=note, captured_at=captured_at, is_primary=make_primary, uploaded_by=user)
        if make_primary:
            animal.image = row.file; animal.save(update_fields=["image"])
    from operations.services import emit_event
    emit_event(animal.farm, "animal_media_uploaded", "Animal media uploaded", note, "animal_media", row.id, user, animal=animal)
    return 200, success_body(data=_media_payload(row), message="Animal media uploaded successfully.")


@animals_router.post("/{animal_id}/media/{media_id}/primary/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error})
@atomic_mutation
def set_primary_animal_media(request, animal_id: int, media_id: int):
    user = require_user(request); org = resolve_organization(user); require_permission(user, org, Permissions.Animal.UPDATE)
    animal = require_animal(org, animal_id); require_farm(org, animal.farm_id, user)
    try: row = animal.media.get(id=media_id)
    except AnimalMedia.DoesNotExist: raise ContractError(404, ErrorCode.RESOURCE_NOT_FOUND, "Animal media could not be found.")
    with transaction.atomic():
        _preserve_legacy_primary(animal, user)
        animal.media.filter(is_primary=True).update(is_primary=False); row.is_primary = True; row.save(update_fields=["is_primary"])
        animal.image = row.file; animal.save(update_fields=["image"])
    from operations.services import emit_event
    emit_event(animal.farm, "animal_primary_photo_changed", "Primary animal photo changed", "", "animal_media", row.id, user, animal=animal)
    return 200, success_body(data=_media_payload(row), message="Primary animal photo updated successfully.")


@animals_router.get(
    "/{animal_id}/timeline/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Animal timeline",
)
def animal_timeline(request, animal_id: int, page: int = 1, page_size: int = 20):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.VIEW)
    animal = require_animal(org, animal_id)
    require_farm(org, animal.farm_id, user)
    qs = (
        AnimalEvent.objects.filter(animal=animal)
        .select_related("event_type", "animal")
        .order_by("-event_date", "-id")
    )
    return 200, paginated(qs, page, page_size, serialize_event, "Timeline fetched successfully.")


@animals_router.post(
    "/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error, 422: V2Error},
    summary="Progressive animal create (lifecycle status only)",
)
@atomic_mutation
def create_animal(request, payload: AnimalCreateIn):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.CREATE)
    key, cached = begin_idempotency(user, request, payload)
    if cached:
        return cached
    farm = require_farm(org, payload.farm_id, user)
    if payload.status not in ALLOWED_CREATE_STATUSES:
        raise ContractError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "status must be active, sold, dead, transferred_out, or culled.",
            errors={"status": payload.status},
        )
    tag_id = (payload.tag_id or "").strip()
    if tag_id and Animal.objects.filter(tag_id__iexact=tag_id).exists():
        raise ContractError(409, ErrorCode.DUPLICATE_RECORD, "Tag ID already exists.")
    data = {
        "user": user,
        "farm": farm,
        "tag_id": tag_id or _internal_tag(),
        "gender": payload.gender,
        "source_type": payload.source_type,
        "status": payload.status,
        "notes": payload.notes or "",
        "dob": payload.dob,
        "estimated_age_months": payload.estimated_age_months,
    }
    if payload.livestock_species_id:
        try:
            data["livestock_species"] = LivestockSpecies.objects.get(
                id=payload.livestock_species_id, is_active=True
            )
        except LivestockSpecies.DoesNotExist:
            raise ContractError(422, ErrorCode.INVALID_SPECIES, "Species could not be found.")
    if payload.livestock_breed_id:
        try:
            breed = LivestockBreed.objects.get(id=payload.livestock_breed_id, is_active=True)
        except LivestockBreed.DoesNotExist:
            raise ContractError(422, ErrorCode.INVALID_BREED, "Breed could not be found.")
        if data.get("livestock_species") and breed.species_id != data["livestock_species"].id:
            raise ContractError(422, ErrorCode.INVALID_BREED, "Breed does not belong to the selected species.")
        data["livestock_breed"] = breed
    if payload.housing_unit_id:
        try:
            data["housing_unit"] = FarmHousingUnit.objects.get(
                id=payload.housing_unit_id, farm=farm, status="active"
            )
        except FarmHousingUnit.DoesNotExist:
            raise ContractError(422, ErrorCode.INVALID_HOUSING_UNIT, "Housing unit could not be found.")
    if payload.mother_id:
        data["mother"] = require_animal(org, payload.mother_id, farm)
    animal = Animal(**data)
    try:
        animal.save()
    except ValidationError as exc:
        raise ContractError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Animal could not be created.",
            errors=getattr(exc, "message_dict", {"details": getattr(exc, "messages", [str(exc)])}),
        )
    body = success_body(data=build_animal_profile(animal), message="Animal created successfully.")
    store_idempotency(user, key, 200, body)
    return 200, body


@animals_router.get(
    "/resolve-tag/{tag_id}/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Resolve an animal tag within the organization",
)
def resolve_tag(request, tag_id: str, farm_id: int = None):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.VIEW)
    qs = Animal.objects.filter(tag_id__iexact=tag_id, farm__in=authorized_farms(user, org))
    if farm_id is not None:
        farm = require_farm(org, farm_id, user)
        qs = qs.filter(farm=farm)
    animal = qs.select_related("farm", "livestock_species", "livestock_breed", "housing_unit").first()
    if not animal:
        raise ContractError(404, ErrorCode.TAG_NOT_FOUND, "No animal found for this tag.")
    require_farm(org, animal.farm_id, user)
    return 200, success_body(
        data={
            "id": animal.id,
            "tag_id": animal.tag_id,
            "farm_id": animal.farm_id,
            "lifecycle_status": animal.status,
            "status": animal.status,
            "health_status": animal.health_status,
        },
        message="Tag resolved successfully.",
    )
