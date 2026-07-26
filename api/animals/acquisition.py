from django.utils import timezone

from .models import AnimalAcquisition

ACQUISITION_FIELDS = [
    "supplier", "purchase_price", "currency", "payment_status", "payment_method",
    "transaction_reference", "notes", "purchase_date", "transportation_cost",
    "veterinary_inspection_cost", "other_acquisition_cost", "country_of_origin",
    "import_date", "shipping_cost", "customs_clearance_cost", "quarantine_cost",
    "veterinary_certification_cost", "insurance_cost", "other_import_cost",
    "production_cost_dam_feeding", "production_cost_pregnancy_treatment",
    "production_cost_delivery", "production_cost_breeding", "estimated_opening_value",
    "valuation_date", "valuation_method", "valuation_notes",
]


def has_acquisition_data(payload) -> bool:
    return any(getattr(payload, f, None) not in (None, "") for f in ACQUISITION_FIELDS)


def save_animal_acquisition(animal, payload, user):
    """
    Shared by the standalone acquisition endpoint and the animal-creation
    endpoints, so the cost formulas and Finance posting only exist once.
    Creates/updates the AnimalAcquisition row, computes cost for this
    animal's source_type, and posts the Finance transaction exactly once —
    safe to call again later (e.g. to attach a receipt) without double-posting.
    """
    from finance.services import record_transaction
    from finance.models import Transaction
    from common.audit import log_audit

    previous_acq = AnimalAcquisition.objects.filter(animal=animal).first()
    previous_purchase_price = previous_acq.purchase_price if previous_acq else None

    defaults = {f: getattr(payload, f, None) for f in ACQUISITION_FIELDS}
    acq, _ = AnimalAcquisition.objects.update_or_create(animal=animal, defaults=defaults)

    if previous_acq is not None and previous_purchase_price != payload.purchase_price:
        log_audit(
            user=user, action="edit_purchase_value", source_module="animals",
            object_type="AnimalAcquisition", object_id=acq.id,
            previous_value=previous_purchase_price, new_value=payload.purchase_price,
            reason=getattr(payload, "notes", None),
        )

    already_posted = Transaction.objects.filter(animal=animal, source_module="animal_acquisition").exists()
    today = timezone.localdate()

    if not already_posted:
        if animal.source_type == "purchased":
            total = acq.total_purchased_cost()
            if total:
                record_transaction(
                    farm=animal.farm, type="expense", category_name="Acquisition", amount=total,
                    transaction_date=acq.purchase_date or today, source_module="animal_acquisition",
                    source_id=animal.id, animal=animal, currency=acq.currency,
                    payment_status=acq.payment_status, payment_method=acq.payment_method,
                    transaction_reference=acq.transaction_reference, created_by=user,
                )
            animal.acquisition_cost = total or None

        elif animal.source_type == "imported":
            total = acq.total_landed_cost()
            if total:
                record_transaction(
                    farm=animal.farm, type="expense", category_name="Acquisition", amount=total,
                    transaction_date=acq.import_date or today, source_module="animal_acquisition",
                    source_id=animal.id, animal=animal, currency=acq.currency,
                    payment_status=acq.payment_status, payment_method=acq.payment_method,
                    transaction_reference=acq.transaction_reference, created_by=user,
                )
            animal.acquisition_cost = total or None

        elif animal.source_type == "born":
            # Internal production cost, not a purchase — post component costs
            # under their own categories instead of a single "Acquisition" line.
            if acq.production_cost_breeding:
                record_transaction(
                    farm=animal.farm, type="expense", category_name="Breeding",
                    amount=acq.production_cost_breeding, transaction_date=today,
                    source_module="animal_acquisition", source_id=animal.id, animal=animal, created_by=user,
                )
            vet_amount = (acq.production_cost_delivery or 0) + (acq.production_cost_pregnancy_treatment or 0)
            if vet_amount:
                record_transaction(
                    farm=animal.farm, type="expense", category_name="Veterinary Service",
                    amount=vet_amount, transaction_date=today,
                    source_module="animal_acquisition", source_id=animal.id, animal=animal, created_by=user,
                )
            if acq.production_cost_dam_feeding:
                record_transaction(
                    farm=animal.farm, type="expense", category_name="Feed",
                    amount=acq.production_cost_dam_feeding, transaction_date=today,
                    source_module="animal_acquisition", source_id=animal.id, animal=animal, created_by=user,
                )

        elif animal.source_type == "opening_record":
            # Pre-existing value, not a new expense — nothing was spent
            # through this system, so no Finance transaction is posted.
            animal.opening_value = acq.estimated_opening_value

        animal.save(update_fields=["acquisition_cost", "opening_value"])

    return acq
