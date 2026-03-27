from ninja import Router, Query
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
    UnitType
)
from subcriptions.models import SubscriptionPlan, Subscription
from common.utils import generate_ref
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.http import JsonResponse
from .schema import (
    ListResponseSchema,
    APIResponse,
    SpeciesSchemaIn,
    SpecieUpdateSchema,
    BreedSchemaIn,
    BreedUpdateSchema,
    UnitTypeSchemaIn,
    UnitTypeUpdateSchema
)
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
    
    if not user.is_superuser:
         raise HttpError(403, "Permission Denied")
     
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
    
    if not user.is_superuser:
         raise HttpError(403, "Permission Denied")
     
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