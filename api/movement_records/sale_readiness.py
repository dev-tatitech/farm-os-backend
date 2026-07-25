from django.utils import timezone


def _age_in_months(animal):
    if animal.dob:
        return (timezone.localdate() - animal.dob).days / 30.44
    if animal.estimated_age_months is not None:
        return float(animal.estimated_age_months)
    return None


def resolve_sale_policy(animal, farm=None):
    """Most-specific-wins: farm+breed > farm-only > breed-only > system default."""
    from .models import SalePolicy

    species_id = animal.livestock_species_id
    if not species_id:
        return None
    breed_id = animal.livestock_breed_id
    farm = farm or animal.farm

    qs = SalePolicy.objects.filter(species_id=species_id, is_active=True)
    for farm_filter in ([farm] if farm else []) + [None]:
        for breed_filter in ([breed_id] if breed_id else []) + [None]:
            rule = qs.filter(farm=farm_filter, breed=breed_filter).first()
            if rule:
                return rule
    return None


def evaluate_sale_readiness(animal, farm=None, expected_sale_price=None):
    """
    Returns {status, restrictions, manual_review_reasons, factors}.
    status is one of: not_ready_for_sale, approaching_sale_readiness,
    ready_for_sale, sale_recommended, sale_restricted, manual_review_required.
    A restriction always wins over manual review, which always wins over an
    auto-computed readiness tier — this mirrors spec 9.3's ordering.
    """
    from animals.growth import average_daily_gain
    from finance.services import compute_total_cost_to_date, compute_income_generated
    from health.models import HealthAlert, TreatmentRecord

    farm = farm or animal.farm
    restrictions = []
    manual_review_reasons = []

    if not animal.is_active or animal.status != "active":
        restrictions.append(f"Animal is not active (status: {animal.status}).")
    if animal.is_quarantine:
        restrictions.append("Animal is under quarantine.")

    has_serious_alert = HealthAlert.objects.filter(
        animal=animal, status="open", severity__in=["high_priority", "critical"]
    ).exists()
    if has_serious_alert or animal.health_status == "sick":
        restrictions.append("Animal has an unresolved serious health concern.")

    has_active_treatment = TreatmentRecord.objects.filter(
        animal=animal, next_follow_up_date__gte=timezone.localdate()
    ).exists()
    if has_active_treatment:
        manual_review_reasons.append("Animal has an active treatment with a pending follow-up.")

    from pharmacy.alerts import check_animal_withdrawal_restriction

    withdrawal_treatment = check_animal_withdrawal_restriction(animal)
    if withdrawal_treatment:
        restrictions.append(
            f"Animal is within the drug withdrawal period for {withdrawal_treatment.drug.name} "
            f"(ends {withdrawal_treatment.withdrawal_end_date})."
        )

    policy = resolve_sale_policy(animal, farm=farm)

    if animal.is_pregnant:
        if not policy or not policy.allow_pregnant_sale:
            restrictions.append("Animal is pregnant and farm policy does not allow selling pregnant animals.")
        else:
            manual_review_reasons.append("Animal is pregnant — farm policy allows sale, but this must be disclosed to the buyer.")

    if policy and policy.require_sale_approval and not animal.sale_approved:
        manual_review_reasons.append("Sale requires approval, which has not yet been obtained.")

    latest_weight = animal.weights.order_by("-date").first()
    weight_kg = latest_weight.weight if latest_weight else None
    factors = {
        "current_weight_kg": weight_kg,
        "target_sale_weight_kg": policy.target_sale_weight_kg if policy else None,
        "age_months": _age_in_months(animal),
        "min_sale_age_months": policy.min_sale_age_months if policy else None,
        "growth_rate_kg_per_day": average_daily_gain(animal),
        "total_cost_to_date": compute_total_cost_to_date(animal),
        "income_generated": compute_income_generated(animal),
        "current_estimated_value": float(animal.current_estimated_value) if animal.current_estimated_value else None,
        "withdrawal_end_date": withdrawal_treatment.withdrawal_end_date if withdrawal_treatment else None,
        "is_pregnant": animal.is_pregnant,
        "is_lactating": animal.is_lactating,
        "life_stage": animal.current_life_stage,
    }

    if restrictions:
        return {"status": "sale_restricted", "restrictions": restrictions,
                "manual_review_reasons": manual_review_reasons, "factors": factors}
    if manual_review_reasons:
        return {"status": "manual_review_required", "restrictions": restrictions,
                "manual_review_reasons": manual_review_reasons, "factors": factors}

    if not policy or policy.target_sale_weight_kg is None:
        return {
            "status": "manual_review_required", "restrictions": restrictions,
            "manual_review_reasons": ["No sale policy/target weight configured for this species — manual review required."],
            "factors": factors,
        }

    age_ok = factors["age_months"] is not None and (
        not policy.min_sale_age_months or factors["age_months"] >= policy.min_sale_age_months
    )
    pct_of_target = (weight_kg / policy.target_sale_weight_kg * 100) if weight_kg else 0

    if pct_of_target >= 100 and age_ok:
        status = "ready_for_sale"
    elif pct_of_target >= policy.approaching_ready_threshold_pct:
        status = "approaching_sale_readiness"
    else:
        status = "not_ready_for_sale"

    if status == "ready_for_sale" and expected_sale_price is not None:
        from .profitability import calculate_profitability

        profit_data = calculate_profitability(animal, expected_sale_price=expected_sale_price, farm=farm)
        margin = profit_data["estimated_profit_margin_pct"]
        if margin is not None and margin >= policy.sale_recommended_margin_pct:
            status = "sale_recommended"

    return {"status": status, "restrictions": restrictions, "manual_review_reasons": manual_review_reasons, "factors": factors}
