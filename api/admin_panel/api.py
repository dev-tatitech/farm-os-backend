from ninja import Router, Query
from typing import Optional
from django.conf import settings
from ninja import File
from account.auth import get_current_user, validate_crftoken
from account.models import User as users
from django.db.models import Q
from ninja.files import UploadedFile
from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from uuid import UUID
from django.forms.models import model_to_dict
from datetime import date, time
import calendar
from django.db.models import Sum
from dateutil.relativedelta import relativedelta
from decimal import Decimal,ROUND_HALF_UP, ROUND_DOWN
from dateutil.parser import parse as parse_datetime
from django.core.mail import send_mail
from ninja import Router, Query
from ninja.errors import HttpError
from pydantic import EmailStr
from django.utils.timezone import now
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
import random
from datetime import datetime
from dateutil.relativedelta import relativedelta
import hmac
import hashlib
import json
import os
from django.db.models.functions import Round
from django.db.models import Value
from django.http import HttpResponse
from account.models import (
    Country,
    AdminLevel1
)
import uuid
from .models import (
    Species,
    Breed,
    UnitType,
    LivestockSpecies,
    LivestockBreed,
    HousingUnitType,
    FarmHousingUnit,
    AnimalClassification,
)
from subcriptions.models import SubscriptionPlan, Subscription
from common.utils import generate_ref
import inspect
from common.permissions import Permissions
from role.models import Permission
from django.http import JsonResponse
from .schema import (
    ListResponseSchema,
    APIResponse,
    SpeciesSchemaIn,
    SpecieUpdateSchema,
    BreedSchemaIn,
    BreedUpdateSchema,
    UnitTypeSchemaIn,
    UnitTypeUpdateSchema,
    LivestockBreedIn,
    LivestockBreedUpdate,
    FarmHousingUnitIn,
    FarmHousingUnitUpdate,
)
from organization.models import Farm
router = Router(tags=["Admin panel"])
@router.post(
    "/species/",
    response={200: APIResponse, 403: APIResponse},
)
def add_species(request, payload: SpeciesSchemaIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    if not user.is_superuser:
         raise HttpError(403, "Permission Denied")
    if Species.objects.filter(name__iexact=payload.name).exists():
        raise HttpError(409, "Species already exists") 
    code = f"Spe-{generate_ref()}" 
    specie = Species.objects.create(
        name = payload.name,
        code = code
    )
    return 200, APIResponse(success=True, message=f"Species added success", data=None)

@router.get("/species/{page}/{page_size}", response={200: APIResponse, 403: APIResponse},)
def get_species(
    request,  
    page: int,
    page_size: int,
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    
  
    species = Species.objects.all()
    paginator = Paginator(species, page_size)
    page_obj = paginator.page(page)

    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "name":data.name
            }
        )
    return 200, ListResponseSchema(
        success=True,
        message=f"species fetch successfully",
        data=serialized,
        num_pages=paginator.num_pages,
        current_page=page_obj.number,
        total_items=paginator.count,
        has_next=page_obj.has_next,
        has_previous=page_obj.has_previous,
    )
 
@router.patch("/species", response={200: APIResponse, 403: APIResponse},)
def update_species(request, payload: SpecieUpdateSchema):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    
    if not user.is_superuser:
         raise HttpError(403, "Permission Denied")
     
    species = get_object_or_404(Species, id = payload.species_id)
    if payload.name:
        species.name = payload.name

    species.save()
    data = {
            "id": species.id,
            "name": species.name
        }
  
    return 200, APIResponse(
        success=True, message="species update successfully", data=data
    )
    
@router.post(
    "/breed/",
    response={200: APIResponse, 403: APIResponse},
)
def add_breed(request, payload: BreedSchemaIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    if not user.is_superuser:
         raise HttpError(403, "Permission Denied")
    species = get_object_or_404(Species, id = payload.species_id)
    if Breed.objects.filter(name__iexact=payload.name).exists():
        raise HttpError(409, "Species already exists") 
    code = f"Bre-{generate_ref()}" 
    
    specie = Breed.objects.create(
        species = species,
        name = payload.name,
        code = code
    )
    return 200, APIResponse(success=True, message=f"breed added success", data=None)

@router.get("/breed/{page}/{page_size}", response={200: APIResponse, 403: APIResponse},)
def get_breed(
    request,  
    page: int,
    page_size: int,
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    
   
    breed = Breed.objects.select_related("species").all()
    paginator = Paginator(breed, page_size)
    page_obj = paginator.page(page)

    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "species":data.species.name,
                "name":data.name
            }
        )
    return 200, ListResponseSchema(
        success=True,
        message=f"Breed fetch successfully",
        data=serialized,
        num_pages=paginator.num_pages,
        current_page=page_obj.number,
        total_items=paginator.count,
        has_next=page_obj.has_next,
        has_previous=page_obj.has_previous,
    )
 
@router.patch("/breed", response={200: APIResponse, 403: APIResponse},)
def update_breed(request, payload: BreedUpdateSchema):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    
    if not user.is_superuser:
         raise HttpError(403, "Permission Denied")
    breed = get_object_or_404(Breed, id = payload.breed_id)
    
    if payload.name:
        breed.name = payload.name
    if payload.species_id:
        species = get_object_or_404(Species, id = payload.species_id)
        breed.species = species
    breed.save()
    data = {
            "id": breed.id,
            "species": breed.species.name,
            "name": breed.name
        }
  
    return 200, APIResponse(
        success=True, message="breed update successfully", data=data
    )
    
@router.post(
    "/unit-type/",
    response={200: APIResponse, 403: APIResponse},
)
def add_unit_type(request, payload: UnitTypeSchemaIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    if not user.is_superuser:
         raise HttpError(403, "Permission Denied")
    if UnitType.objects.filter(name__iexact=payload.name).exists():
        raise HttpError(409, "unit type already exists") 
    code = f"UT-{generate_ref()}"   
    specie = UnitType.objects.create(
        name = payload.name,
        code = code
    )
    return 200, APIResponse(success=True, message=f"unit type added success", data=None)

@router.get("/unit-type/{page}/{page_size}", response={200: APIResponse, 403: APIResponse},)
def get_get_unit_type(
    request,  
    page: int,
    page_size: int,
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    
    if not user.is_superuser:
         raise HttpError(403, "Permission Denied")
     
    unit_type = UnitType.objects.all()
    paginator = Paginator(unit_type, page_size)
    page_obj = paginator.page(page)

    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "name":data.name
            }
        )
    return 200, ListResponseSchema(
        success=True,
        message=f"unit_type fetch successfully",
        data=serialized,
        num_pages=paginator.num_pages,
        current_page=page_obj.number,
        total_items=paginator.count,
        has_next=page_obj.has_next,
        has_previous=page_obj.has_previous,
    )
    
@router.patch("/unit-type", response={200: APIResponse, 403: APIResponse},)
def update_unit_type(request, payload: UnitTypeUpdateSchema):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    
    if not user.is_superuser:
         raise HttpError(403, "Permission Denied")
     
    unit_type = get_object_or_404(UnitType, id = payload.unit_type_id)
    if payload.name:
        unit_type.name = payload.name

    unit_type.save()
    data = {
            "id": unit_type.id,
            "name": unit_type.name
        }
  
    return 200, APIResponse(
        success=True, message="unit type update successfully", data=data
    )

@router.post("/seed-permissions/", response={200: APIResponse, 403: APIResponse})
def seed_permissions(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    if not user.is_superuser:
        raise HttpError(403, "Permission Denied")

    to_create = []
    for module_name in dir(Permissions):
        if module_name.startswith("_"):
            continue
        module_cls = getattr(Permissions, module_name)
        if not inspect.isclass(module_cls):
            continue
        for attr_name, code in vars(module_cls).items():
            if attr_name.startswith("_") or not isinstance(code, str):
                continue
            to_create.append(Permission(
                code=code,
                name=f"{attr_name.replace('_', ' ').title()} {module_name}",
                module=module_name,
                description="",
            ))

    existing_codes = set(Permission.objects.values_list("code", flat=True))
    new_permissions = [p for p in to_create if p.code not in existing_codes]
    skipped = len(to_create) - len(new_permissions)

    Permission.objects.bulk_create(new_permissions)
    return 200, APIResponse(
        success=True,
        message=f"{len(new_permissions)} permission(s) seeded, {skipped} skipped (already exist)",
        data={"seeded": len(new_permissions), "skipped": skipped, "total": len(to_create)},
    )


# ─── Livestock Master Data ────────────────────────────────────────────────────

_SEED_DATA = {
    "Cattle": {
        "category": "ruminant",
        "breeds": [
            "White Fulani (Bunaji)", "Red Bororo (Rahaji)", "Sokoto Gudali",
            "Muturu", "N'Dama", "Holstein Friesian", "Jersey", "Brahman",
            "Angus", "Hereford", "Simmental",
        ],
        "unit_types": [
            "Barn", "Paddock", "Grazing Block", "Calf Pen",
            "Maternity Pen", "Isolation Pen", "Breeding Pen",
        ],
        "classifications": {
            "male": ["Bull", "Steer"],
            "female": ["Cow", "Heifer"],
        },
    },
    "Sheep": {
        "category": "ruminant",
        "breeds": ["Yankasa", "Uda", "Balami", "West African Dwarf", "Dorper", "Merino"],
        "unit_types": ["Sheep Pen", "Grazing Block", "Lambing Pen", "Isolation Pen"],
        "classifications": {"male": ["Ram"], "female": ["Ewe"]},
    },
    "Goat": {
        "category": "ruminant",
        "breeds": ["Red Sokoto (Maradi)", "West African Dwarf", "Sahel", "Boer", "Anglo-Nubian", "Saanen"],
        "unit_types": ["Goat Shed", "Goat Pen", "Grazing Block", "Kidding Pen", "Isolation Pen"],
        "classifications": {"male": ["Buck"], "female": ["Doe"]},
    },
    "Pig": {
        "category": "monogastric",
        "breeds": ["Large White", "Landrace", "Duroc", "Hampshire", "Berkshire", "Pietrain"],
        "unit_types": ["Pigsty", "Gestation Pen", "Farrowing Pen", "Grower Pen", "Isolation Pen"],
        "classifications": {"male": ["Boar"], "female": ["Sow"]},
    },
    "Rabbit": {
        "category": "small_livestock",
        "breeds": ["New Zealand White", "Californian", "Chinchilla", "Flemish Giant", "Dutch", "Rex"],
        "unit_types": ["Rabbitry", "Hutch", "Breeding Cage", "Grower Cage"],
        "classifications": {"male": ["Buck"], "female": ["Doe"]},
    },
    "Horse": {
        "category": "equine",
        "breeds": ["Arabian", "Thoroughbred", "Quarter Horse", "Barb", "Local Breed"],
        "unit_types": ["Stable", "Paddock", "Training Stable", "Isolation Stable"],
        "classifications": {"male": ["Stallion"], "female": ["Mare"]},
    },
    "Camel": {
        "category": "camelid",
        "breeds": ["Dromedary", "Bactrian", "Local Camel"],
        "unit_types": ["Camel Pen", "Grazing Area", "Shelter", "Isolation Pen"],
        "classifications": {"male": ["Bull Camel"], "female": ["Cow Camel"]},
    },
}


@router.post("/seed-livestock-master/", response={200: APIResponse, 403: APIResponse})
def seed_livestock_master(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    if not user.is_superuser:
        raise HttpError(403, "Permission Denied")

    stats = {"species": 0, "breeds": 0, "unit_types": 0, "classifications": 0}

    for species_name, data in _SEED_DATA.items():
        species, created = LivestockSpecies.objects.get_or_create(
            name=species_name,
            defaults={"category": data["category"], "is_system": True},
        )
        if created:
            stats["species"] += 1

        existing_breeds = set(
            LivestockBreed.objects.filter(species=species, farm=None)
            .values_list("name", flat=True)
        )
        new_breeds = [
            LivestockBreed(species=species, name=b, is_system=True)
            for b in data["breeds"] if b not in existing_breeds
        ]
        LivestockBreed.objects.bulk_create(new_breeds)
        stats["breeds"] += len(new_breeds)

        existing_unit_types = set(
            HousingUnitType.objects.filter(species=species)
            .values_list("name", flat=True)
        )
        new_unit_types = [
            HousingUnitType(species=species, name=u, is_system=True)
            for u in data["unit_types"] if u not in existing_unit_types
        ]
        HousingUnitType.objects.bulk_create(new_unit_types)
        stats["unit_types"] += len(new_unit_types)

        existing_cls = set(
            AnimalClassification.objects.filter(species=species)
            .values_list("sex", "name")
        )
        new_cls = []
        for sex, names in data["classifications"].items():
            for name in names:
                if (sex, name) not in existing_cls:
                    new_cls.append(AnimalClassification(
                        species=species, sex=sex, name=name, is_system=True
                    ))
        AnimalClassification.objects.bulk_create(new_cls)
        stats["classifications"] += len(new_cls)

    return 200, APIResponse(
        success=True,
        message="Livestock master data seeded successfully",
        data=stats,
    )


# ── Read endpoints ────────────────────────────────────────────────────────────

@router.get("/livestock/species/", response={200: APIResponse, 403: APIResponse})
def get_livestock_species(request):
    user_id = get_current_user(request)
    try:
        users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    data = list(
        LivestockSpecies.objects.filter(is_active=True)
        .values("id", "name", "category", "is_system")
    )
    return 200, APIResponse(success=True, message="Livestock species", data=data)


@router.get("/livestock/breeds/{species_id}/", response={200: APIResponse, 403: APIResponse})
def get_livestock_breeds(request, species_id: int, farm_id: Optional[int] = None):
    user_id = get_current_user(request)
    try:
        users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    species = get_object_or_404(LivestockSpecies, id=species_id, is_active=True)
    qs = LivestockBreed.objects.filter(species=species, is_active=True)
    # system breeds + this farm's custom breeds
    if farm_id:
        qs = qs.filter(Q(farm=None) | Q(farm_id=farm_id))
    else:
        qs = qs.filter(farm=None)

    data = list(qs.values("id", "name", "description", "origin", "is_system", "farm_id"))
    return 200, APIResponse(success=True, message="Livestock breeds", data=data)


@router.get("/livestock/housing-unit-types/{species_id}/", response={200: APIResponse, 403: APIResponse})
def get_housing_unit_types(request, species_id: int):
    user_id = get_current_user(request)
    try:
        users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    species = get_object_or_404(LivestockSpecies, id=species_id, is_active=True)
    data = list(
        HousingUnitType.objects.filter(species=species, is_active=True)
        .values("id", "name", "is_system")
    )
    return 200, APIResponse(success=True, message="Housing unit types", data=data)


@router.get("/livestock/housing-units/{farm_id}/", response={200: APIResponse, 403: APIResponse})
def get_farm_housing_units(request, farm_id: int, species_id: Optional[int] = None):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    farm = get_object_or_404(Farm, id=farm_id)
    qs = FarmHousingUnit.objects.filter(farm=farm, status="active").select_related("unit_type")
    if species_id:
        qs = qs.filter(
            Q(allowed_species__id=species_id) | Q(unit_type__species_id=species_id)
        ).distinct()

    data = []
    for u in qs:
        data.append({
            "id": u.id,
            "name": u.name,
            "unit_type": u.unit_type.name,
            "unit_type_id": u.unit_type_id,
            "capacity": u.capacity,
            "occupancy": u.occupancy,
            "location": u.location,
            "status": u.status,
            "allowed_species": list(u.allowed_species.values_list("name", flat=True)),
        })
    return 200, APIResponse(success=True, message="Farm housing units", data=data)


@router.get("/livestock/classifications/{species_id}/", response={200: APIResponse, 403: APIResponse})
def get_animal_classifications(request, species_id: int, sex: Optional[str] = None):
    user_id = get_current_user(request)
    try:
        users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    species = get_object_or_404(LivestockSpecies, id=species_id, is_active=True)
    qs = AnimalClassification.objects.filter(species=species, is_active=True)
    if sex:
        qs = qs.filter(sex=sex)
    data = list(qs.values("id", "name", "sex", "is_system"))
    return 200, APIResponse(success=True, message="Animal classifications", data=data)


# ── Write endpoints ───────────────────────────────────────────────────────────

@router.post("/livestock/breeds/", response={200: APIResponse, 403: APIResponse})
def create_farm_breed(request, payload: LivestockBreedIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(403, "Permission denied")

    species = get_object_or_404(LivestockSpecies, id=payload.species_id, is_active=True)

    # farm must belong to this org; use first farm if not specified
    farm = org.farms.first()
    if not farm:
        raise HttpError(404, "No farm found for this organisation")

    if LivestockBreed.objects.filter(
        species=species, name__iexact=payload.name,
    ).filter(Q(farm=None) | Q(farm=farm)).exists():
        raise HttpError(409, "Breed already exists for this species")

    breed = LivestockBreed.objects.create(
        species=species,
        farm=farm,
        name=payload.name,
        description=payload.description,
        origin=payload.origin,
        is_system=False,
    )
    return 200, APIResponse(
        success=True,
        message="Custom breed created",
        data={"id": breed.id, "name": breed.name, "species": species.name},
    )


@router.patch("/livestock/breeds/{breed_id}/", response={200: APIResponse, 403: APIResponse})
def update_farm_breed(request, breed_id: int, payload: LivestockBreedUpdate):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    breed = get_object_or_404(LivestockBreed, id=breed_id)
    if breed.is_system:
        raise HttpError(403, "System breeds cannot be modified")

    org = user.organization or user.organizations.first()
    if not org or not org.farms.filter(id=breed.farm_id).exists():
        raise HttpError(403, "Permission denied")

    if payload.name is not None:
        breed.name = payload.name
    if payload.description is not None:
        breed.description = payload.description
    if payload.origin is not None:
        breed.origin = payload.origin
    if payload.is_active is not None:
        breed.is_active = payload.is_active
    breed.save()

    return 200, APIResponse(
        success=True,
        message="Breed updated",
        data={"id": breed.id, "name": breed.name, "is_active": breed.is_active},
    )


@router.post("/livestock/housing-units/", response={200: APIResponse, 403: APIResponse})
def create_farm_housing_unit(request, payload: FarmHousingUnitIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(403, "Permission denied")

    unit_type = get_object_or_404(HousingUnitType, id=payload.unit_type_id, is_active=True)
    farm = org.farms.first()
    if not farm:
        raise HttpError(404, "No farm found for this organisation")

    unit = FarmHousingUnit.objects.create(
        farm=farm,
        unit_type=unit_type,
        name=payload.name,
        capacity=payload.capacity,
        location=payload.location,
    )
    if payload.allowed_species_ids:
        unit.allowed_species.set(
            LivestockSpecies.objects.filter(id__in=payload.allowed_species_ids)
        )

    return 200, APIResponse(
        success=True,
        message="Housing unit created",
        data={
            "id": unit.id,
            "name": unit.name,
            "unit_type": unit_type.name,
            "capacity": unit.capacity,
        },
    )


@router.patch("/livestock/housing-units/{unit_id}/", response={200: APIResponse, 403: APIResponse})
def update_farm_housing_unit(request, unit_id: int, payload: FarmHousingUnitUpdate):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    org = user.organization or user.organizations.first()
    unit = get_object_or_404(FarmHousingUnit, id=unit_id)

    if not org or not org.farms.filter(id=unit.farm_id).exists():
        raise HttpError(403, "Permission denied")

    if payload.name is not None:
        unit.name = payload.name
    if payload.capacity is not None:
        unit.capacity = payload.capacity
    if payload.location is not None:
        unit.location = payload.location
    if payload.status is not None:
        unit.status = payload.status
    unit.save()

    if payload.allowed_species_ids is not None:
        unit.allowed_species.set(
            LivestockSpecies.objects.filter(id__in=payload.allowed_species_ids)
        )

    return 200, APIResponse(
        success=True,
        message="Housing unit updated",
        data={"id": unit.id, "name": unit.name, "status": unit.status},
    )
