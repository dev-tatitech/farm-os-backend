from django.utils import timezone
from datetime import timedelta

SUDDEN_WEIGHT_LOSS_THRESHOLD_PCT = 8
NO_WEIGHT_RECORDED_DAYS = 60


def _open_alert(animal, farm, alert_type, severity, evidence, recommended_review):
    from .models import HealthAlert

    return HealthAlert.objects.update_or_create(
        animal=animal, alert_type=alert_type, status="open",
        defaults=dict(
            farm=farm, severity=severity, detected_date=timezone.localdate(),
            evidence=evidence, recommended_review=recommended_review,
        ),
    )


def _close_alert_if_open(animal, alert_type):
    from .models import HealthAlert

    HealthAlert.objects.filter(animal=animal, alert_type=alert_type, status="open").update(
        status="resolved", resolution_notes="Auto-resolved: condition no longer detected.",
        resolution_date=timezone.localdate(),
    )


def check_low_weight_for_age(animal, farm):
    from admin_panel.weight_ranges import find_weight_reference_range

    alert_type = "low_weight_for_age"
    latest = animal.weights.order_by("-date").first()
    rng = find_weight_reference_range(animal)
    if not latest or not rng:
        return None

    if rng.min_weight_kg is not None and latest.weight < rng.min_weight_kg:
        return _open_alert(
            animal, farm, alert_type, "attention_required",
            evidence=(
                f"Animal {animal.tag_id} weighs {latest.weight}kg as of {latest.date}, "
                f"below the configured range ({rng.min_weight_kg}-{rng.max_weight_kg}kg) for its age/species."
            ),
            recommended_review="Review feeding, health and growth records.",
        )
    if rng.max_weight_kg is not None and latest.weight > rng.max_weight_kg:
        return _open_alert(
            animal, farm, "high_weight_for_age", "monitor",
            evidence=(
                f"Animal {animal.tag_id} weighs {latest.weight}kg as of {latest.date}, "
                f"above the configured range ({rng.min_weight_kg}-{rng.max_weight_kg}kg) for its age/species."
            ),
            recommended_review="Review feeding plan and body condition.",
        )
    _close_alert_if_open(animal, alert_type)
    _close_alert_if_open(animal, "high_weight_for_age")
    return None


def check_sudden_weight_loss(animal, farm, threshold_pct=SUDDEN_WEIGHT_LOSS_THRESHOLD_PCT):
    from animals.growth import percentage_weight_change

    alert_type = "sudden_weight_loss"
    pct_change = percentage_weight_change(animal)
    if pct_change is not None and pct_change <= -threshold_pct:
        return _open_alert(
            animal, farm, alert_type, "high_priority",
            evidence=f"Animal {animal.tag_id} has lost {abs(pct_change):.1f}% of its recorded body weight since the previous measurement.",
            recommended_review="Conduct a physical and veterinary review.",
        )
    _close_alert_if_open(animal, alert_type)
    return None


def check_no_weight_recorded(animal, farm, days=NO_WEIGHT_RECORDED_DAYS):
    alert_type = "no_weight_recorded"
    latest = animal.weights.order_by("-date").first()
    cutoff = timezone.localdate() - timedelta(days=days)
    if latest is None or latest.date < cutoff:
        last_date = latest.date if latest else "never"
        return _open_alert(
            animal, farm, alert_type, "monitor",
            evidence=f"No weight has been recorded for {animal.tag_id} within the last {days} days (last recorded: {last_date}).",
            recommended_review="Schedule a weight measurement.",
        )
    _close_alert_if_open(animal, alert_type)
    return None


def check_poor_feed_conversion(animal, farm, lookback_days=30):
    """
    Flags animals where feed cost over the lookback window rose but weight
    gain over the same window did not follow proportionally (near-zero or
    negative gain despite continued feed spend).
    """
    from finance.models import Transaction
    from django.db.models import Sum

    alert_type = "poor_feed_conversion"
    cutoff = timezone.localdate() - timedelta(days=lookback_days)

    feed_cost = (
        Transaction.objects.filter(animal=animal, type="expense", category__name="Feed", transaction_date__gte=cutoff)
        .aggregate(total=Sum("amount"))["total"]
        or 0
    )
    weights_in_window = list(animal.weights.filter(date__gte=cutoff).order_by("date"))
    if feed_cost <= 0 or len(weights_in_window) < 2:
        return None

    gain = weights_in_window[-1].weight - weights_in_window[0].weight
    if gain <= 0.1:
        return _open_alert(
            animal, farm, alert_type, "attention_required",
            evidence=(
                f"Feed cost of {feed_cost} was recorded for {animal.tag_id} over the last {lookback_days} days, "
                f"but weight gain over the same period was only {gain:.2f}kg."
            ),
            recommended_review="Review feed quality, feeding quantity and health condition.",
        )
    _close_alert_if_open(animal, alert_type)
    return None


def check_reproductive_concern(animal, farm):
    from reproduction.eligibility import resolve_breeding_rule, _age_in_months
    from reproduction.models import PregnancyRecord, BirthRecord

    alert_type = "reproductive_concern"
    if animal.gender != "female" or not animal.is_active or animal.status != "active":
        return None

    rule = resolve_breeding_rule(animal, farm=farm)
    if not rule or rule.recommended_breeding_age_months is None:
        return None

    age_months = _age_in_months(animal)
    if age_months is None or age_months < rule.recommended_breeding_age_months:
        return None

    if animal.is_pregnant:
        return None

    has_reproductive_event = (
        PregnancyRecord.objects.filter(animal=animal, result="pregnant").exists()
        or BirthRecord.objects.filter(mother=animal).exists()
    )
    if not has_reproductive_event:
        return _open_alert(
            animal, farm, alert_type, "monitor",
            evidence=(
                f"Animal {animal.tag_id} has passed the recommended breeding age "
                f"({rule.recommended_breeding_age_months} months) but has no successful reproductive event on record."
            ),
            recommended_review="Review reproductive and health history.",
        )
    _close_alert_if_open(animal, alert_type)
    return None


def check_production_decline(animal, farm, recent_days=7, baseline_days=30):
    from animals.models import MilkRecord
    from django.db.models import Sum, Avg

    alert_type = "production_decline"
    today = timezone.localdate()

    recent_avg = (
        MilkRecord.objects.filter(animal=animal, record_date__gte=today - timedelta(days=recent_days))
        .values("record_date").annotate(daily_total=Sum("quantity"))
        .aggregate(avg=Avg("daily_total"))["avg"]
    )
    baseline_avg = (
        MilkRecord.objects.filter(
            animal=animal,
            record_date__gte=today - timedelta(days=baseline_days),
            record_date__lt=today - timedelta(days=recent_days),
        )
        .values("record_date").annotate(daily_total=Sum("quantity"))
        .aggregate(avg=Avg("daily_total"))["avg"]
    )
    if recent_avg is None or baseline_avg is None or baseline_avg == 0:
        return None

    if recent_avg < baseline_avg * 0.85:
        return _open_alert(
            animal, farm, alert_type, "attention_required",
            evidence=(
                f"Milk output for {animal.tag_id} has averaged {recent_avg:.1f}/day over the last {recent_days} days, "
                f"down from a {baseline_avg:.1f}/day average over the prior period."
            ),
            recommended_review="Review feed, health, lactation stage and environmental conditions.",
        )
    _close_alert_if_open(animal, alert_type)
    return None


ALL_CHECKS = [
    check_low_weight_for_age,
    check_sudden_weight_loss,
    check_no_weight_recorded,
    check_poor_feed_conversion,
    check_reproductive_concern,
    check_production_decline,
]


def run_health_alert_scan(animal, farm=None):
    """Runs every detector for a single animal, returns the list of (created/updated) alerts triggered."""
    farm = farm or animal.farm
    triggered = []
    for check_fn in ALL_CHECKS:
        result = check_fn(animal, farm)
        if result:
            alert, _ = result
            triggered.append(alert)
    return triggered
