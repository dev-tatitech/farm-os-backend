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
    ContactEnquiry,
    NewsletterSubscriber,
    LifeStageDefinition,
    AnimalLifecycleHistory,
    WeightReferenceRange,
)
from .lifecycle import seed_life_stages, suggest_life_stage, apply_life_stage
from .weight_ranges import seed_weight_ranges, find_weight_reference_range
from animals.models import Animal
from subcriptions.models import SubscriptionPlan, Subscription
from common.utils import generate_ref
import inspect
from common.permissions import Permissions
from common.permission_checker import user_has_permission
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
    ContactEnquiryIn,
    ContactEnquiryStatusUpdate,
    NewsletterSubscribeIn,
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


# ─── Contact Enquiry Endpoints ────────────────────────────────────────────────

@router.post(
    "/contact/enquiry/",
    response={200: APIResponse, 400: APIResponse},
    auth=None,
    tags=["Contact"],
)
def submit_contact_enquiry(request, payload: ContactEnquiryIn):
    from dateutil.parser import parse as parse_dt
    from dateutil.parser import ParserError

    consultation_date = None
    if payload.consultation_date:
        try:
            consultation_date = parse_dt(payload.consultation_date)
        except (ParserError, ValueError):
            return 400, APIResponse(
                success=False,
                message="Invalid consultation_date format. Use ISO 8601 (e.g. 2025-08-01T10:00:00).",
                data=None,
            )

    enquiry = ContactEnquiry.objects.create(
        full_name=payload.full_name,
        farm_name=payload.farm_name,
        email=payload.email,
        phone=payload.phone,
        country=payload.country,
        region=payload.region,
        farm_type=payload.farm_type,
        farm_size=payload.farm_size,
        record_method=payload.record_method,
        modules_of_interest=payload.modules_of_interest or [],
        challenges=payload.challenges,
        preferred_contact_method=payload.preferred_contact_method,
        consultation_date=consultation_date,
    )

    return 200, APIResponse(
        success=True,
        message="Enquiry submitted successfully. Our team will be in touch shortly.",
        data={
            "id": enquiry.id,
            "full_name": enquiry.full_name,
            "email": enquiry.email,
            "status": enquiry.status,
            "created_at": str(enquiry.created_at),
        },
    )


@router.get(
    "/contact/enquiries/",
    response={200: ListResponseSchema, 403: APIResponse},
    tags=["Contact"],
)
def list_contact_enquiries(
    request,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(id=user_id)
    except users.DoesNotExist:
        raise HttpError(401, "User not found")
    if not user.is_superuser and not user.is_staff:
        return 403, APIResponse(success=False, message="Staff access required", data=None)

    qs = ContactEnquiry.objects.all()

    if status:
        qs = qs.filter(status=status)

    if search:
        qs = qs.filter(
            Q(full_name__icontains=search)
            | Q(email__icontains=search)
            | Q(farm_name__icontains=search)
            | Q(country__icontains=search)
        )

    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page)

    data = [
        {
            "id": e.id,
            "full_name": e.full_name,
            "farm_name": e.farm_name,
            "email": e.email,
            "phone": e.phone,
            "country": e.country,
            "region": e.region,
            "farm_type": e.farm_type,
            "farm_size": e.farm_size,
            "record_method": e.record_method,
            "modules_of_interest": e.modules_of_interest,
            "challenges": e.challenges,
            "preferred_contact_method": e.preferred_contact_method,
            "consultation_date": str(e.consultation_date) if e.consultation_date else None,
            "status": e.status,
            "notes": e.notes,
            "created_at": str(e.created_at),
        }
        for e in page_obj.object_list
    ]

    return 200, ListResponseSchema(
        success=True,
        message="Enquiries fetched",
        data=data,
        num_pages=paginator.num_pages,
        current_page=page,
        total_items=paginator.count,
        has_next=page_obj.has_next(),
        has_previous=page_obj.has_previous(),
    )


@router.get(
    "/contact/enquiry/{enquiry_id}/",
    response={200: APIResponse, 403: APIResponse, 404: APIResponse},
    tags=["Contact"],
)
def get_contact_enquiry(request, enquiry_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(id=user_id)
    except users.DoesNotExist:
        raise HttpError(401, "User not found")
    if not user.is_superuser and not user.is_staff:
        return 403, APIResponse(success=False, message="Staff access required", data=None)

    try:
        e = ContactEnquiry.objects.get(id=enquiry_id)
    except ContactEnquiry.DoesNotExist:
        return 404, APIResponse(success=False, message="Enquiry not found", data=None)

    return 200, APIResponse(
        success=True,
        message="Enquiry fetched",
        data={
            "id": e.id,
            "full_name": e.full_name,
            "farm_name": e.farm_name,
            "email": e.email,
            "phone": e.phone,
            "country": e.country,
            "region": e.region,
            "farm_type": e.farm_type,
            "farm_size": e.farm_size,
            "record_method": e.record_method,
            "modules_of_interest": e.modules_of_interest,
            "challenges": e.challenges,
            "preferred_contact_method": e.preferred_contact_method,
            "consultation_date": str(e.consultation_date) if e.consultation_date else None,
            "status": e.status,
            "notes": e.notes,
            "created_at": str(e.created_at),
            "updated_at": str(e.updated_at),
        },
    )


@router.patch(
    "/contact/enquiry/{enquiry_id}/status/",
    response={200: APIResponse, 404: APIResponse},
    tags=["Contact"],
    auth=None,
)
def update_enquiry_status(request, enquiry_id: int, payload: ContactEnquiryStatusUpdate):
    try:
        e = ContactEnquiry.objects.get(id=enquiry_id)
    except ContactEnquiry.DoesNotExist:
        return 404, APIResponse(success=False, message="Enquiry not found", data=None)

    e.status = payload.status
    if payload.notes is not None:
        e.notes = payload.notes
    e.save(update_fields=["status", "notes", "updated_at"])

    return 200, APIResponse(
        success=True,
        message="Enquiry status updated",
        data={"id": e.id, "status": e.status, "notes": e.notes},
    )


# ─── Newsletter Subscribe ─────────────────────────────────────────────────────

@router.post(
    "/subscribe/",
    response={200: APIResponse, 400: APIResponse},
    auth=None,
    tags=["Contact"],
)
def newsletter_subscribe(request, payload: NewsletterSubscribeIn):
    subscriber, created = NewsletterSubscriber.objects.get_or_create(
        email=payload.email,
        defaults={"is_active": True},
    )

    if not created and subscriber.is_active:
        return 200, APIResponse(
            success=True,
            message="You are already subscribed.",
            data={"email": subscriber.email, "already_subscribed": True},
        )

    if not created and not subscriber.is_active:
        subscriber.is_active = True
        subscriber.save(update_fields=["is_active"])

    return 200, APIResponse(
        success=True,
        message="Successfully subscribed.",
        data={"email": subscriber.email, "already_subscribed": False},
    )


# ─── Species Lifecycle ───────────────────────────────────────────────────────

@router.post("/lifecycle/seed/", response={200: APIResponse, 403: APIResponse})
def seed_lifecycle(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    if not user.is_superuser:
        raise HttpError(403, "Permission Denied")

    created = seed_life_stages()
    return 200, APIResponse(success=True, message="Life stages seeded successfully", data={"created": created})


@router.get("/lifecycle/stages/{species_id}/", response={200: APIResponse, 403: APIResponse})
def get_life_stages(request, species_id: int):
    user_id = get_current_user(request)
    try:
        users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    species = get_object_or_404(LivestockSpecies, id=species_id, is_active=True)
    data = list(
        LifeStageDefinition.objects.filter(species=species, is_active=True)
        .order_by("order")
        .values("id", "name", "order", "min_age_months", "max_age_months", "applicable_sex")
    )
    return 200, APIResponse(success=True, message="Life stages", data=data)


@router.get("/lifecycle/animal/{animal_id}/", response={200: APIResponse, 403: APIResponse})
def get_animal_lifecycle(request, animal_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    animal = get_object_or_404(Animal, id=animal_id, farm__organization=org)
    suggested = suggest_life_stage(animal)
    history = list(
        AnimalLifecycleHistory.objects.filter(animal=animal)
        .select_related("changed_by")
        .values("id", "previous_stage", "new_stage", "is_override", "override_reason", "changed_at", "changed_by__email")
    )
    data = {
        "animal_id": animal.id,
        "current_life_stage": animal.current_life_stage,
        "suggested_life_stage": suggested,
        "history": history,
    }
    return 200, APIResponse(success=True, message="Animal lifecycle", data=data)


@router.post("/lifecycle/animal/{animal_id}/refresh/", response={200: APIResponse, 403: APIResponse})
def refresh_animal_lifecycle(request, animal_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    animal = get_object_or_404(Animal, id=animal_id, farm__organization=org)
    stage = apply_life_stage(animal)
    return 200, APIResponse(success=True, message="Lifecycle stage refreshed", data={"current_life_stage": stage})


@router.post("/lifecycle/animal/{animal_id}/override/", response={200: APIResponse, 403: APIResponse})
def override_animal_lifecycle(request, animal_id: int, stage: str, reason: str):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Animal.UPDATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")

    animal = get_object_or_404(Animal, id=animal_id, farm__organization=org)
    if not reason:
        raise HttpError(400, "Override reason is required")

    new_stage = apply_life_stage(animal, user=user, override_stage=stage, override_reason=reason)
    return 200, APIResponse(success=True, message="Lifecycle stage overridden", data={"current_life_stage": new_stage})


# ─── Weight Reference Ranges ──────────────────────────────────────────────────

@router.post("/weight-range/seed/", response={200: APIResponse, 403: APIResponse})
def seed_weight_range(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    if not user.is_superuser:
        raise HttpError(403, "Permission Denied")

    created = seed_weight_ranges()
    return 200, APIResponse(success=True, message="Weight reference ranges seeded successfully", data={"created": created})


@router.post("/weight-range/", response={200: APIResponse, 403: APIResponse})
def create_farm_weight_range(
    request, farm_id: int, species_id: int, breed_id: int = None, sex: str = "any",
    min_age_months: float = None, max_age_months: float = None,
    min_weight_kg: float = None, max_weight_kg: float = None, target_daily_gain_kg: float = None,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(403, "Permission denied")
    perm = user_has_permission(user, Permissions.Animal.UPDATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied: configuring species weight ranges requires explicit authorization")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    species = get_object_or_404(LivestockSpecies, id=species_id, is_active=True)
    breed = get_object_or_404(LivestockBreed, id=breed_id) if breed_id else None

    existing = WeightReferenceRange.objects.filter(
        species=species, breed=breed, farm=farm, sex=sex,
        min_age_months=min_age_months, max_age_months=max_age_months,
    ).first()
    previous_range = None
    if existing:
        previous_range = f"{existing.min_weight_kg}-{existing.max_weight_kg}kg"
        existing.min_weight_kg = min_weight_kg
        existing.max_weight_kg = max_weight_kg
        existing.target_daily_gain_kg = target_daily_gain_kg
        existing.is_system = False
        existing.save()
        rng = existing
    else:
        rng = WeightReferenceRange.objects.create(
            species=species, breed=breed, farm=farm, sex=sex,
            min_age_months=min_age_months, max_age_months=max_age_months,
            min_weight_kg=min_weight_kg, max_weight_kg=max_weight_kg,
            target_daily_gain_kg=target_daily_gain_kg, is_system=False,
        )

    from common.audit import log_audit
    log_audit(
        user=user, action="configure_species_rule", source_module="admin_panel",
        object_type="WeightReferenceRange", object_id=rng.id,
        previous_value=previous_range, new_value=f"{min_weight_kg}-{max_weight_kg}kg",
    )

    return 200, APIResponse(
        success=True,
        message="Farm weight range saved" if not existing else "Farm weight range updated",
        data={"id": rng.id},
    )


@router.get("/weight-range/{species_id}/", response={200: APIResponse, 403: APIResponse})
def get_weight_ranges(request, species_id: int, farm_id: int = None):
    user_id = get_current_user(request)
    try:
        users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    species = get_object_or_404(LivestockSpecies, id=species_id, is_active=True)
    qs = WeightReferenceRange.objects.filter(species=species, is_active=True)
    qs = qs.filter(Q(farm_id=farm_id) | Q(farm=None)) if farm_id else qs.filter(farm=None)
    data = list(qs.values(
        "id", "breed_id", "farm_id", "sex", "min_age_months", "max_age_months",
        "min_weight_kg", "max_weight_kg", "target_daily_gain_kg", "is_system",
    ))
    return 200, APIResponse(success=True, message="Weight reference ranges", data=data)


@router.get("/weight-range/animal/{animal_id}/", response={200: APIResponse, 403: APIResponse})
def get_animal_weight_range(request, animal_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    animal = get_object_or_404(Animal, id=animal_id, farm__organization=org)
    rng = find_weight_reference_range(animal)
    if not rng:
        return 200, APIResponse(success=True, message="No weight reference range configured", data=None)
    return 200, APIResponse(
        success=True,
        message="Weight reference range",
        data={
            "animal_id": animal.id,
            "min_weight_kg": rng.min_weight_kg,
            "max_weight_kg": rng.max_weight_kg,
            "target_daily_gain_kg": rng.target_daily_gain_kg,
            "is_system": rng.is_system,
        },
    )
