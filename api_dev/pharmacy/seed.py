_DRUG_CATEGORY_NAMES = [
    "Antibiotic",
    "Antiparasitic",
    "Vaccine",
    "Vitamin/Supplement",
    "Anti-inflammatory",
    "Hormonal",
    "Antiseptic/Disinfectant",
    "Other",
]

# A modest system-defined starter library — common, widely-used veterinary
# drugs, not species-specific. Farms add whatever else they actually stock
# via the farm-defined Drug create endpoint.
_DRUG_SEED = [
    ("Oxytetracycline", "Antibiotic", "injection", "ml", 0),
    ("Penicillin", "Antibiotic", "injection", "ml", 7),
    ("Ivermectin", "Antiparasitic", "injection", "ml", 28),
    ("Albendazole", "Antiparasitic", "oral_liquid", "ml", 14),
    ("Multivitamin Injection", "Vitamin/Supplement", "injection", "ml", 0),
    ("Iodine Tincture", "Antiseptic/Disinfectant", "topical", "ml", 0),
]


def seed_drug_master():
    from .models import DrugCategory, Drug

    categories = {}
    created_categories = 0
    for name in _DRUG_CATEGORY_NAMES:
        cat, was_created = DrugCategory.objects.get_or_create(name=name, defaults={"is_system": True})
        categories[name] = cat
        if was_created:
            created_categories += 1

    created_drugs = 0
    for name, category_name, dosage_form, unit, withdrawal_days in _DRUG_SEED:
        _, was_created = Drug.objects.get_or_create(
            name=name, farm=None,
            defaults={
                "category": categories[category_name], "dosage_form": dosage_form,
                "unit_of_measurement": unit, "withdrawal_period_days": withdrawal_days,
                "is_system": True,
            },
        )
        if was_created:
            created_drugs += 1

    return {"categories": created_categories, "drugs": created_drugs}
