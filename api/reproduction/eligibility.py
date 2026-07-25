from django.utils import timezone


def _age_in_months(animal):
    if animal.dob:
        return (timezone.localdate() - animal.dob).days / 30.44
    if animal.estimated_age_months is not None:
        return float(animal.estimated_age_months)
    return None


def resolve_breeding_rule(animal, farm=None):
    """
    Most-specific-wins lookup: farm+breed > farm+species > system+breed >
    system+species. Returns None if nothing is configured for this species
    at all (eligibility checks then only enforce what's universally true —
    sex, active status, not already pregnant).
    """
    from .models import BreedingEligibilityRule

    species_id = animal.livestock_species_id
    if not species_id:
        return None

    breed_id = animal.livestock_breed_id
    farm = farm or animal.farm

    qs = BreedingEligibilityRule.objects.filter(species_id=species_id, is_active=True)

    for farm_filter in ([farm] if farm else []) + [None]:
        for breed_filter in ([breed_id] if breed_id else []) + [None]:
            rule = qs.filter(farm=farm_filter, breed=breed_filter).first()
            if rule:
                return rule
    return None


def check_breeding_eligibility(animal, farm=None, for_pregnancy=False):
    """
    Returns (is_eligible: bool, reasons: list[str]). Never raises — callers
    decide whether to turn failures into a ValidationError.
    """
    reasons = []

    if animal.gender != "female":
        reasons.append("Animal must be female.")
        return False, reasons

    if not animal.is_active or animal.status != "active":
        reasons.append("Animal is not alive/active.")

    if animal.is_pregnant:
        reasons.append("Animal is already pregnant.")

    if animal.is_breeding_restricted:
        reasons.append(animal.breeding_restricted_reason or "Animal is marked breeding-restricted.")

    if animal.current_life_stage in ("Retired", "Sold", "Deceased"):
        reasons.append(f"Animal's lifecycle stage ({animal.current_life_stage}) does not permit breeding.")

    if animal.is_quarantine or animal.health_status in ("sick", "at_risk"):
        reasons.append("Animal has an active health restriction.")

    rule = resolve_breeding_rule(animal, farm=farm)
    age_months = _age_in_months(animal)

    if rule:
        if rule.min_breeding_age_months is not None:
            if age_months is None or age_months < rule.min_breeding_age_months:
                reasons.append(f"Animal has not reached the minimum breeding age ({rule.min_breeding_age_months} months).")
        if rule.max_breeding_age_months is not None:
            if age_months is not None and age_months > rule.max_breeding_age_months:
                reasons.append(f"Animal has exceeded the configured maximum breeding age ({rule.max_breeding_age_months} months).")
        if rule.min_breeding_weight_kg is not None:
            latest_weight = animal.weights.order_by("-date").first()
            weight_kg = latest_weight.weight if latest_weight else None
            if weight_kg is None or weight_kg < rule.min_breeding_weight_kg:
                reasons.append(f"Animal has not reached the minimum breeding weight ({rule.min_breeding_weight_kg} kg).")
        if rule.min_postpartum_interval_days is not None:
            from reproduction.models import BirthRecord
            last_birth = BirthRecord.objects.filter(mother=animal).order_by("-birth_date").first()
            if last_birth:
                days_since = (timezone.localdate() - last_birth.birth_date).days
                if days_since < rule.min_postpartum_interval_days:
                    reasons.append(
                        f"Animal is within the required postpartum recovery interval "
                        f"({rule.min_postpartum_interval_days} days; {days_since} elapsed)."
                    )
        if rule.max_births_lifetime is not None:
            from reproduction.models import BirthRecord
            births = BirthRecord.objects.filter(mother=animal).count()
            if births >= rule.max_births_lifetime:
                reasons.append(f"Animal has reached the configured maximum lifetime births ({rule.max_births_lifetime}).")

    if for_pregnancy and animal.is_lactating and rule and not rule.allow_pregnant_and_lactating:
        reasons.append("Farm/species policy does not allow an animal to be both pregnant and lactating.")

    return len(reasons) == 0, reasons


def lactation_pregnancy_warning(animal, farm=None):
    """
    Non-blocking warning shown when an animal is (or is about to become) both
    pregnant and lactating, unless farm policy explicitly prohibits the
    combination (in which case check_breeding_eligibility already blocks it).
    """
    if animal.is_pregnant and animal.is_lactating:
        return "This animal is both pregnant and lactating — verify this is expected for your farm's management system."
    return None
