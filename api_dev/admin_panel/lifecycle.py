from django.utils import timezone

# Default per-species life-stage ladder (age in months). These are sensible
# husbandry-standard defaults, not hardcoded universal truths — every row is
# a normal, farm-editable LifeStageDefinition record once seeded.
_LIFE_STAGE_SEED = {
    "Cattle": {"suckling": 3, "weaned": 8, "juvenile": 12, "grower": 15, "breeding_eligible": 15, "senior": 96},
    "Sheep": {"suckling": 2, "weaned": 4, "juvenile": 7, "grower": 10, "breeding_eligible": 7, "senior": 72},
    "Goat": {"suckling": 2, "weaned": 4, "juvenile": 7, "grower": 10, "breeding_eligible": 7, "senior": 72},
    "Pig": {"suckling": 1, "weaned": 2, "juvenile": 4, "grower": 6, "breeding_eligible": 6, "senior": 48},
    "Rabbit": {"suckling": 1, "weaned": 2, "juvenile": 4, "grower": 5, "breeding_eligible": 5, "senior": 36},
    "Horse": {"suckling": 6, "weaned": 12, "juvenile": 24, "grower": 36, "breeding_eligible": 24, "senior": 180},
    "Camel": {"suckling": 12, "weaned": 18, "juvenile": 36, "grower": 48, "breeding_eligible": 36, "senior": 216},
}


def seed_life_stages():
    from .models import LifeStageDefinition, LivestockSpecies

    created = 0
    for species_name, m in _LIFE_STAGE_SEED.items():
        try:
            species = LivestockSpecies.objects.get(name=species_name)
        except LivestockSpecies.DoesNotExist:
            continue

        newborn_max = min(1, m["suckling"])
        stages = [
            ("Newborn", 1, 0, newborn_max),
            ("Suckling", 2, newborn_max, m["suckling"]),
            ("Weaned", 3, m["suckling"], m["weaned"]),
            ("Juvenile", 4, m["weaned"], m["juvenile"]),
            ("Grower", 5, m["juvenile"], m["grower"]),
            ("Mature", 6, m["grower"], None),
            ("Breeding Eligible", 7, m["breeding_eligible"], None),
            ("Senior", 8, m["senior"], None),
        ]
        for name, order, min_age, max_age in stages:
            _, was_created = LifeStageDefinition.objects.get_or_create(
                species=species, name=name,
                defaults={"order": order, "min_age_months": min_age, "max_age_months": max_age, "is_system": True},
            )
            if was_created:
                created += 1

        for name, order, sex in [("Pregnant", 9, "female"), ("Lactating", 10, "female")]:
            _, was_created = LifeStageDefinition.objects.get_or_create(
                species=species, name=name,
                defaults={
                    "order": order, "applicable_sex": sex, "is_system": True,
                    "requires_pregnant": name == "Pregnant" or None,
                    "requires_lactating": name == "Lactating" or None,
                },
            )
            if was_created:
                created += 1

        # Non-auto-derived stages: valid for manual assignment/override, but
        # not suggested automatically (no age/weight/flag criteria set).
        for name, order in [("Dry", 11), ("Finishing", 5), ("Retired", 12)]:
            _, was_created = LifeStageDefinition.objects.get_or_create(
                species=species, name=name, defaults={"order": order, "is_system": True, "is_active": False},
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


def suggest_life_stage(animal):
    """
    Auto-suggest a life stage for `animal` from configured LifeStageDefinition
    rows. Sold/Deceased are driven directly by Animal.status, not by age or
    weight, so they're resolved before any rule lookup.
    """
    from .models import LifeStageDefinition

    if animal.status == "sold":
        return "Sold"
    if animal.status == "dead":
        return "Deceased"

    if not animal.livestock_species_id:
        return None

    age_months = _age_in_months(animal)
    latest_weight = animal.weights.order_by("-date").first()
    weight_kg = latest_weight.weight if latest_weight else None

    candidates = LifeStageDefinition.objects.filter(
        species_id=animal.livestock_species_id, is_active=True
    ).order_by("-order")

    for stage in candidates:
        if stage.applicable_sex != "any" and stage.applicable_sex != animal.gender:
            continue
        if stage.requires_pregnant is not None and stage.requires_pregnant != animal.is_pregnant:
            continue
        if stage.requires_lactating is not None and stage.requires_lactating != animal.is_lactating:
            continue
        if stage.min_age_months is not None and (age_months is None or age_months < stage.min_age_months):
            continue
        if stage.max_age_months is not None and (age_months is None or age_months > stage.max_age_months):
            continue
        if stage.min_weight_kg is not None and (weight_kg is None or weight_kg < stage.min_weight_kg):
            continue
        if stage.max_weight_kg is not None and (weight_kg is None or weight_kg > stage.max_weight_kg):
            continue
        return stage.name
    return None


def apply_life_stage(animal, user=None, override_stage=None, override_reason=None):
    """
    Recompute (or override) an animal's life stage, recording the change in
    AnimalLifecycleHistory. Returns the resulting stage name, or None if
    nothing changed and there's nothing to record.
    """
    from .models import AnimalLifecycleHistory

    previous = animal.current_life_stage
    is_override = override_stage is not None
    new_stage = override_stage if is_override else suggest_life_stage(animal)

    if new_stage is None or new_stage == previous:
        return previous

    AnimalLifecycleHistory.objects.create(
        animal=animal,
        previous_stage=previous,
        new_stage=new_stage,
        is_override=is_override,
        override_reason=override_reason if is_override else None,
        changed_by=user,
    )
    animal.current_life_stage = new_stage
    animal.save(update_fields=["current_life_stage"])
    return new_stage
