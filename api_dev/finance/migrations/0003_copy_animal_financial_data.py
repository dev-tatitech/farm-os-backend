from django.db import migrations


def copy_forward(apps, schema_editor):
    OldAnimalAcquisition = apps.get_model("animals", "AnimalAcquisition")
    NewAnimalAcquisition = apps.get_model("finance", "AnimalAcquisition")
    AnimalFinancialProfile = apps.get_model("finance", "AnimalFinancialProfile")
    Animal = apps.get_model("animals", "Animal")

    acquisition_fields = [
        "supplier", "purchase_price", "currency", "payment_status", "payment_method",
        "transaction_reference", "supporting_document", "notes", "purchase_date",
        "transportation_cost", "veterinary_inspection_cost", "other_acquisition_cost",
        "country_of_origin", "import_date", "shipping_cost", "customs_clearance_cost",
        "quarantine_cost", "veterinary_certification_cost", "insurance_cost",
        "other_import_cost", "production_cost_dam_feeding",
        "production_cost_pregnancy_treatment", "production_cost_delivery",
        "production_cost_breeding", "estimated_opening_value", "valuation_date",
        "valuation_method", "valuation_notes", "created_at", "updated_at",
    ]

    for old in OldAnimalAcquisition.objects.all().iterator():
        NewAnimalAcquisition.objects.create(
            animal_id=old.animal_id,
            **{f: getattr(old, f) for f in acquisition_fields},
        )

    for animal in Animal.objects.exclude(
        acquisition_cost=None, opening_value=None, current_estimated_value=None
    ).iterator():
        AnimalFinancialProfile.objects.create(
            animal_id=animal.id,
            acquisition_cost=animal.acquisition_cost,
            opening_value=animal.opening_value,
            current_estimated_value=animal.current_estimated_value,
        )


def copy_backward(apps, schema_editor):
    # Old columns/table no longer exist by the time this app's forward
    # migration would be reversed in practice (animals/0026 runs after this
    # one and drops them) — nothing meaningful to restore into.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0002_animalacquisition_animalfinancialprofile"),
    ]

    operations = [
        migrations.RunPython(copy_forward, copy_backward),
    ]
