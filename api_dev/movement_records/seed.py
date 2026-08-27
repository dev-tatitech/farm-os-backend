# Species-level default sale policies (Phase 4). Standard husbandry sale-weight
# benchmarks, not hardcoded law — every row is a normal, farm-editable
# SalePolicy record once seeded, and farms can override via a farm-scoped
# (or farm+breed-scoped) SalePolicy row that resolve_sale_policy() prefers.
_SALE_POLICY_SEED = {
    "Cattle": dict(target_sale_weight_kg=400, min_sale_age_months=18),
    "Sheep": dict(target_sale_weight_kg=40, min_sale_age_months=8),
    "Goat": dict(target_sale_weight_kg=30, min_sale_age_months=8),
    "Pig": dict(target_sale_weight_kg=90, min_sale_age_months=6),
    "Rabbit": dict(target_sale_weight_kg=2.5, min_sale_age_months=4),
    "Horse": dict(target_sale_weight_kg=400, min_sale_age_months=36),
    "Camel": dict(target_sale_weight_kg=350, min_sale_age_months=36),
}


def seed_sale_policies():
    from .models import SalePolicy
    from admin_panel.models import LivestockSpecies

    created = 0
    for species_name, fields in _SALE_POLICY_SEED.items():
        try:
            species = LivestockSpecies.objects.get(name=species_name)
        except LivestockSpecies.DoesNotExist:
            continue
        _, was_created = SalePolicy.objects.get_or_create(
            species=species, breed=None, farm=None,
            defaults={
                **fields, "is_system": True,
                "allow_pregnant_sale": False, "require_sale_approval": False,
                "expected_sale_expenses_pct": 5, "approaching_ready_threshold_pct": 85,
                "sale_recommended_margin_pct": 15,
            },
        )
        if was_created:
            created += 1
    return created
