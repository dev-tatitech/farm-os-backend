# Species-level default breeding eligibility rules. These are standard
# husbandry benchmarks, not hardcoded universal law — every row is an
# ordinary, farm-editable BreedingEligibilityRule record once seeded, and a
# farm can add its own farm-scoped (or farm+breed-scoped) override that takes
# priority over these system defaults (see eligibility.resolve_breeding_rule).
_BREEDING_RULE_SEED = {
    "Cattle": dict(min_breeding_age_months=15, recommended_breeding_age_months=18, max_breeding_age_months=144,
                   min_breeding_weight_kg=250, min_postpartum_interval_days=60, max_births_lifetime=10),
    "Sheep": dict(min_breeding_age_months=7, recommended_breeding_age_months=8, max_breeding_age_months=96,
                  min_breeding_weight_kg=32, min_postpartum_interval_days=30, max_births_lifetime=12),
    "Goat": dict(min_breeding_age_months=7, recommended_breeding_age_months=8, max_breeding_age_months=96,
                 min_breeding_weight_kg=25, min_postpartum_interval_days=30, max_births_lifetime=12),
    "Pig": dict(min_breeding_age_months=6, recommended_breeding_age_months=8, max_breeding_age_months=48,
                min_breeding_weight_kg=100, min_postpartum_interval_days=21, max_births_lifetime=14),
    "Rabbit": dict(min_breeding_age_months=5, recommended_breeding_age_months=6, max_breeding_age_months=36,
                   min_breeding_weight_kg=3, min_postpartum_interval_days=30, max_births_lifetime=20),
    "Horse": dict(min_breeding_age_months=24, recommended_breeding_age_months=36, max_breeding_age_months=192,
                  min_breeding_weight_kg=350, min_postpartum_interval_days=30, max_births_lifetime=15),
    "Camel": dict(min_breeding_age_months=36, recommended_breeding_age_months=48, max_breeding_age_months=216,
                  min_breeding_weight_kg=300, min_postpartum_interval_days=90, max_births_lifetime=10),
}


def seed_breeding_rules():
    from .models import BreedingEligibilityRule
    from admin_panel.models import LivestockSpecies

    created = 0
    for species_name, fields in _BREEDING_RULE_SEED.items():
        try:
            species = LivestockSpecies.objects.get(name=species_name)
        except LivestockSpecies.DoesNotExist:
            continue
        _, was_created = BreedingEligibilityRule.objects.get_or_create(
            species=species, breed=None, farm=None,
            defaults={**fields, "is_system": True, "allow_pregnant_and_lactating": True},
        )
        if was_created:
            created += 1
    return created
