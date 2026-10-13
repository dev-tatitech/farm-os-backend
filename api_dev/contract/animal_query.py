from django.db.models import Case, Exists, IntegerField, Max, OuterRef, Q, Subquery, When

from animals.models import Animal, AnimalProfileAttribute
from common.access import authorized_farms
from common.permissions import Permissions

from .authz import require_farm, require_permission
from .codes import ErrorCode
from .exceptions import ContractError
from .helpers import paginated


SUPPORTED_ANIMAL_SORTS = {
    "id", "-id", "status", "-status", "created_at", "-created_at", "newest", "oldest",
    "tag_id", "-tag_id", "tag_asc", "tag_desc", "name", "name_asc", "name_desc",
    "recent_activity", "-recent_activity", "recently_updated",
    "profile_completion_asc", "profile_completion_desc",
}


def animal_display_name(animal):
    """Resolve a saved animal name consistently, falling back to its tag."""
    priorities = {"name": 0, "display_name": 1, "animal_name": 2}
    attributes = getattr(animal, "_prefetched_objects_cache", {}).get("profile_attributes")
    if attributes is None:
        attributes = AnimalProfileAttribute.objects.filter(
            animal_id=animal.pk, attribute_key__in=priorities,
        ).order_by(
            Case(
                When(attribute_key="name", then=0),
                When(attribute_key="display_name", then=1),
                default=2,
                output_field=IntegerField(),
            ),
            "id",
        )
    for attribute in attributes:
        value = attribute.attribute_value.strip()
        if value:
            return value
    return animal.tag_id or f"Animal {animal.pk}"


def query_animals(user, org, *, page=1, page_size=20, farm_id=None, search=None,
                  livestock_species_id=None, livestock_breed_id=None, gender=None,
                  lifecycle_status=None, health_status=None, housing_unit_id=None,
                  group_id=None, is_pregnant=None, is_lactating=None, is_quarantine=None,
                  needs_attention=None, label_id=None, profile_incomplete=None,
                  open_observation=None, open_health_case=None, age_min_months=None,
                  age_max_months=None, sort="-id"):
    require_permission(user, org, Permissions.Animal.VIEW)
    qs = Animal.objects.filter(farm__in=authorized_farms(user, org)).select_related(
        "farm", "livestock_species", "livestock_breed", "housing_unit", "species", "breed"
    ).prefetch_related("profile_attributes")
    if farm_id is not None:
        qs = qs.filter(farm=require_farm(org, farm_id, user))
    if search:
        name_match = AnimalProfileAttribute.objects.filter(
            animal_id=OuterRef("pk"),
            attribute_key__in=("name", "display_name", "animal_name"),
            attribute_value__icontains=search,
        )
        lookup = Q(tag_id__icontains=search) | Q(notes__icontains=search)
        if search.isdigit(): lookup |= Q(id=int(search))
        qs = qs.annotate(_name_match=Exists(name_match)).filter(lookup | Q(_name_match=True))
    for field, value in (("livestock_species_id", livestock_species_id), ("livestock_breed_id", livestock_breed_id), ("gender", gender), ("status", lifecycle_status), ("health_status", health_status), ("housing_unit_id", housing_unit_id), ("is_pregnant", is_pregnant), ("is_lactating", is_lactating), ("is_quarantine", is_quarantine)):
        if value is not None: qs = qs.filter(**{field: value})
    if group_id is not None: qs = qs.filter(group_memberships__group_id=group_id, group_memberships__status="ACTIVE")
    if needs_attention is True:
        qs = qs.filter(Q(health_status__in=["sick", "at_risk"]) | Q(is_quarantine=True))
    elif needs_attention is False:
        qs = qs.exclude(Q(health_status__in=["sick", "at_risk"]) | Q(is_quarantine=True))
    if label_id is not None: qs = qs.filter(label_assignments__label_id=label_id)
    incomplete_profile = (
        Q(tag_id="")
        | Q(livestock_species__isnull=True, species__isnull=True)
        | Q(livestock_breed__isnull=True, breed__isnull=True)
        | Q(dob__isnull=True, estimated_age_months__isnull=True)
        | Q(housing_unit__isnull=True, unit__isnull=True)
        | Q(source_type="")
    )
    if profile_incomplete is True:
        qs = qs.filter(incomplete_profile)
    elif profile_incomplete is False:
        qs = qs.exclude(incomplete_profile)
    if open_observation is True:
        qs = qs.filter(health_observations__status__in=["open", "acknowledged"])
    elif open_observation is False:
        qs = qs.exclude(health_observations__status__in=["open", "acknowledged"])
    if open_health_case is True:
        qs = qs.filter(health_cases__status="open")
    elif open_health_case is False:
        qs = qs.exclude(health_cases__status="open")
    if age_min_months is not None or age_max_months is not None:
        from dateutil.relativedelta import relativedelta
        from django.utils import timezone
        today = timezone.localdate()
        if age_min_months is not None:
            cutoff = today - relativedelta(months=age_min_months)
            qs = qs.filter(Q(dob__lte=cutoff) | Q(dob__isnull=True, estimated_age_months__gte=age_min_months))
        if age_max_months is not None:
            cutoff = today - relativedelta(months=age_max_months)
            qs = qs.filter(Q(dob__gte=cutoff) | Q(dob__isnull=True, estimated_age_months__lte=age_max_months))
    if sort not in SUPPORTED_ANIMAL_SORTS:
        raise ContractError(
            422, ErrorCode.VALIDATION_ERROR,
            "Unsupported animal sort order.", errors={"sort": sort},
        )
    if sort in ("recent_activity", "-recent_activity"):
        qs = qs.annotate(_recent_activity=Max("animal_event_animals__event_date"))
        ordering = ["-_recent_activity", "-id"] if sort == "recent_activity" else ["_recent_activity", "id"]
    elif sort in ("profile_completion_asc", "profile_completion_desc"):
        # The serializer defines the canonical profile-completion rubric;
        # avoid duplicating it in an ORM expression that can drift.
        from .animals import profile_completion
        rows = list(qs.order_by("id"))
        rows.sort(key=lambda animal: (profile_completion(animal)["percentage"], animal.id),
                  reverse=sort.endswith("desc"))
        from .animals import serialize_animal_card
        return paginated(rows, page, page_size, serialize_animal_card, "Animals fetched successfully.")
    elif sort in ("name", "name_asc", "name_desc"):
        name_attribute = AnimalProfileAttribute.objects.filter(
            animal_id=OuterRef("pk"),
            attribute_key__in=("name", "display_name", "animal_name"),
        ).order_by("attribute_key", "id")
        qs = qs.annotate(_animal_name=Subquery(name_attribute.values("attribute_value")[:1]))
        ordering = ["-_animal_name", "-tag_id", "-id"] if sort == "name_desc" else ["_animal_name", "tag_id", "id"]
    else:
        ordering_map = {
            "id": ["id"], "-id": ["-id"], "tag_id": ["tag_id", "id"], "-tag_id": ["-tag_id", "-id"],
            "status": ["status", "id"], "-status": ["-status", "-id"],
            "created_at": ["created_at", "id"], "-created_at": ["-created_at", "-id"],
            "newest": ["-created_at", "-id"], "oldest": ["created_at", "id"],
            "tag_asc": ["tag_id", "id"], "tag_desc": ["-tag_id", "-id"],
            "recently_updated": ["-updated_at", "-id"],
        }
        ordering = ordering_map.get(sort, ["-id"])
    from .animals import serialize_animal_card
    return paginated(qs.order_by(*ordering).distinct(), page, page_size, serialize_animal_card, "Animals fetched successfully.")
