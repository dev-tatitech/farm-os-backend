from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone
from ninja import Router

from admin_panel.models import FarmHousingUnit, LivestockBreed, LivestockSpecies
from animals.models import Animal, AnimalEvent, MilkRecord
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
from .schemas import AnimalCreateIn

animals_router = Router(tags=["Animals"])


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
        "status": animal.status,
        "health_status": animal.health_status,
        "flags": {
            "is_pregnant": animal.is_pregnant,
            "is_lactating": animal.is_lactating,
            "is_quarantine": animal.is_quarantine,
            "is_active": animal.is_active,
            "is_breeding_restricted": animal.is_breeding_restricted,
        },
        "card": {
            "id": animal.id,
            "tag_id": animal.tag_id,
            "species": species_name,
            "breed": breed_name,
            "gender": animal.gender,
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
        "open_tasks": [serialize_task(task) for task in open_tasks],
    }


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
def create_animal(request, payload: AnimalCreateIn):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.CREATE)
    key, cached = begin_idempotency(user, request, payload)
    if cached:
        return cached
    farm = require_farm(org, payload.farm_id, user)
    if payload.status not in ("active", "sold", "dead"):
        raise ContractError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "status must be active, sold, or dead.",
            errors={"status": payload.status},
        )
    if Animal.objects.filter(tag_id__iexact=payload.tag_id).exists():
        raise ContractError(409, ErrorCode.DUPLICATE_RECORD, "Tag ID already exists.")
    data = {
        "user": user,
        "farm": farm,
        "tag_id": payload.tag_id,
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
    qs = Animal.objects.filter(tag_id__iexact=tag_id, farm__organization=org)
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
            "status": animal.status,
            "health_status": animal.health_status,
        },
        message="Tag resolved successfully.",
    )
