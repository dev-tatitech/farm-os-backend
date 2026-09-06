"""Seed Nigeria country, states (AdminLevel1), and LGAs (AdminLevel2)."""
from __future__ import annotations

import json
from pathlib import Path

from django.db import transaction

from .models import AdminLevel1, AdminLevel2, Country

DATA_PATH = Path(__file__).resolve().parent / "data" / "nigeria_states_lgas.json"
NIGERIA_TZ = "Africa/Lagos"


def _load_states_lgas() -> list[dict]:
    with DATA_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload["states"]


def _get_or_create_country() -> tuple[Country, bool]:
    country = Country.objects.filter(name__iexact="Nigeria").first()
    if country:
        return country, False
    return Country.objects.create(name="Nigeria"), True


def _get_or_create_state(country: Country, name: str) -> tuple[AdminLevel1, bool]:
    state = AdminLevel1.objects.filter(country=country, name__iexact=name).first()
    if state:
        if not state.timezone:
            state.timezone = NIGERIA_TZ
            state.save(update_fields=["timezone"])
        return state, False
    return AdminLevel1.objects.create(country=country, name=name, timezone=NIGERIA_TZ), True


def _get_or_create_lga(state: AdminLevel1, name: str) -> tuple[AdminLevel2, bool]:
    lga = AdminLevel2.objects.filter(admin_level1=state, name__iexact=name).first()
    if lga:
        return lga, False
    return AdminLevel2.objects.create(admin_level1=state, name=name), True


@transaction.atomic
def seed_nigeria_geography() -> dict:
    country, country_created = _get_or_create_country()
    states_data = _load_states_lgas()

    stats = {
        "country": {"name": country.name, "id": country.id, "created": country_created},
        "states": {"seeded": 0, "skipped": 0, "total_in_dataset": len(states_data)},
        "lgas": {"seeded": 0, "skipped": 0, "total_in_dataset": 0},
    }

    for row in states_data:
        state_name = row["name"].strip()
        _, state_created = _get_or_create_state(country, state_name)
        if state_created:
            stats["states"]["seeded"] += 1
        else:
            stats["states"]["skipped"] += 1

        state = AdminLevel1.objects.get(country=country, name__iexact=state_name)
        for lga_name in row.get("lgas") or []:
            lga_name = lga_name.strip()
            if not lga_name:
                continue
            stats["lgas"]["total_in_dataset"] += 1
            _, lga_created = _get_or_create_lga(state, lga_name)
            if lga_created:
                stats["lgas"]["seeded"] += 1
            else:
                stats["lgas"]["skipped"] += 1

    return stats
