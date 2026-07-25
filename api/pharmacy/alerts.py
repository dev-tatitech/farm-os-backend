from django.utils import timezone
from datetime import timedelta

EXPIRING_SOON_DAYS = 30


def _open_alert(farm, drug_batch, alert_type, severity, evidence, recommended_review):
    from health.models import HealthAlert

    return HealthAlert.objects.update_or_create(
        drug_batch=drug_batch, alert_type=alert_type, status="open",
        defaults=dict(farm=farm, severity=severity, detected_date=timezone.localdate(),
                      evidence=evidence, recommended_review=recommended_review),
    )


def _close_alert_if_open(drug_batch, alert_type):
    from health.models import HealthAlert

    HealthAlert.objects.filter(drug_batch=drug_batch, alert_type=alert_type, status="open").update(
        status="resolved", resolution_notes="Auto-resolved: condition no longer detected.",
        resolution_date=timezone.localdate(),
    )


def check_batch_expiry(batch):
    today = timezone.localdate()
    if batch.expiry_date < today:
        return _open_alert(
            batch.farm, batch, "drug_expired", "high_priority",
            evidence=f"Batch {batch.batch_number} of {batch.drug.name} expired on {batch.expiry_date}.",
            recommended_review="Remove from active stock and dispose of per regulations.",
        )
    if batch.expiry_date <= today + timedelta(days=EXPIRING_SOON_DAYS):
        return _open_alert(
            batch.farm, batch, "drug_expiring_soon", "monitor",
            evidence=f"Batch {batch.batch_number} of {batch.drug.name} expires on {batch.expiry_date} (within {EXPIRING_SOON_DAYS} days).",
            recommended_review="Plan to use or reorder before expiry.",
        )
    _close_alert_if_open(batch, "drug_expired")
    _close_alert_if_open(batch, "drug_expiring_soon")
    return None


def check_batch_stock_level(batch):
    if batch.quantity_available <= 0:
        return _open_alert(
            batch.farm, batch, "drug_out_of_stock", "attention_required",
            evidence=f"Batch {batch.batch_number} of {batch.drug.name} is out of stock.",
            recommended_review="Reorder or select a different batch for upcoming treatments.",
        )
    if batch.minimum_stock_level is not None and batch.quantity_available <= batch.minimum_stock_level:
        return _open_alert(
            batch.farm, batch, "drug_low_stock", "monitor",
            evidence=(
                f"Batch {batch.batch_number} of {batch.drug.name} has {batch.quantity_available} remaining, "
                f"at or below the configured minimum ({batch.minimum_stock_level})."
            ),
            recommended_review="Reorder soon to avoid running out.",
        )
    _close_alert_if_open(batch, "drug_out_of_stock")
    _close_alert_if_open(batch, "drug_low_stock")
    return None


def run_pharmacy_alert_scan(farm):
    from .models import DrugBatch

    triggered = []
    batches = DrugBatch.objects.filter(farm=farm).exclude(status="depleted").select_related("drug")
    for batch in batches:
        for check_fn in (check_batch_expiry, check_batch_stock_level):
            result = check_fn(batch)
            if result:
                alert, _ = result
                triggered.append(alert)
    return triggered


def get_animals_in_withdrawal(farm, as_of=None):
    """
    Animals currently within a drug withdrawal period — used to restrict
    sale/slaughter/production recording (spec 3.5 last bullet + 9.3).
    """
    from health.models import TreatmentRecord

    as_of = as_of or timezone.localdate()
    return (
        TreatmentRecord.objects.filter(
            animal__isnull=False, withdrawal_end_date__isnull=False, withdrawal_end_date__gte=as_of,
        )
        .filter(animal__farm=farm)
        .select_related("animal", "drug")
    )


def check_animal_withdrawal_restriction(animal, as_of=None):
    """Returns the active withdrawal TreatmentRecord for this animal, or None."""
    from health.models import TreatmentRecord

    as_of = as_of or timezone.localdate()
    return (
        TreatmentRecord.objects.filter(animal=animal, withdrawal_end_date__isnull=False, withdrawal_end_date__gte=as_of)
        .order_by("-withdrawal_end_date")
        .select_related("drug")
        .first()
    )
