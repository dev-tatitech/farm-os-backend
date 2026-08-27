from django.db.models import Q
from django.utils import timezone

# Default age-band weight reference ranges (kg), per species. General
# husbandry-standard estimates, not breed/sex-specific — every row is an
# ordinary, farm-editable WeightReferenceRange record once seeded, and a farm
# or breed-specific override always takes priority over these system rows
# (see find_weight_reference_range).
_WEIGHT_RANGE_SEED = {
    "Cattle": [(0, 6, 50, 150), (6, 12, 150, 250), (12, 24, 250, 400), (24, None, 400, 700)],
    "Sheep": [(0, 6, 10, 30), (6, 12, 25, 45), (12, 24, 40, 70), (24, None, 45, 90)],
    "Goat": [(0, 6, 8, 25), (6, 12, 20, 35), (12, 24, 30, 55), (24, None, 35, 70)],
    "Pig": [(0, 6, 5, 60), (6, 12, 60, 110), (12, 24, 100, 180), (24, None, 150, 250)],
    "Rabbit": [(0, 6, 0.5, 2.5), (6, 12, 2, 4), (12, 24, 3, 5), (24, None, 3, 6)],
    "Horse": [(0, 6, 80, 200), (6, 12, 150, 300), (12, 24, 250, 450), (24, None, 400, 600)],
    "Camel": [(0, 6, 40, 120), (6, 12, 100, 200), (12, 24, 180, 350), (24, None, 300, 600)],
}


def seed_weight_ranges():
    from .models import WeightReferenceRange, LivestockSpecies

    created = 0
    for species_name, bands in _WEIGHT_RANGE_SEED.items():
        try:
            species = LivestockSpecies.objects.get(name=species_name)
        except LivestockSpecies.DoesNotExist:
            continue
        for min_age, max_age, min_kg, max_kg in bands:
            _, was_created = WeightReferenceRange.objects.get_or_create(
                species=species, breed=None, farm=None,
                min_age_months=min_age, max_age_months=max_age,
                defaults={"min_weight_kg": min_kg, "max_weight_kg": max_kg, "is_system": True},
            )
            if was_created:
                created += 1
    return created


def _age_in_months(animal):
    if animal.dob:
        return (timezone.localdate() - animal.dob).days / 30.44
    if animal.estimated_age_months is not None:
        return float(animal.estimated_age_months)
    return None


def _age_band_filter(age_months):
    return (
        (Q(min_age_months__isnull=True) | Q(min_age_months__lte=age_months))
        & (Q(max_age_months__isnull=True) | Q(max_age_months__gte=age_months))
    )


def find_weight_reference_range(animal):
    """
    Most-specific-wins lookup for the age band containing this animal:
    farm+breed > farm-only > breed-only > system default.
    """
    from .models import WeightReferenceRange

    if not animal.livestock_species_id:
        return None
    age_months = _age_in_months(animal)
    if age_months is None:
        return None

    base = WeightReferenceRange.objects.filter(
        species_id=animal.livestock_species_id, is_active=True
    ).filter(_age_band_filter(age_months))

    breed_id = animal.livestock_breed_id
    for farm_filter in [animal.farm_id, None]:
        for breed_filter in ([breed_id] if breed_id else []) + [None]:
            for sex_filter in [animal.gender, "any"]:
                rng = base.filter(farm_id=farm_filter, breed_id=breed_filter, sex=sex_filter).first()
                if rng:
                    return rng
    return None
