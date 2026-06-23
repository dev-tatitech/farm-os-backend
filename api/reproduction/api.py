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
from common.permission_checker import user_has_permission
from common.permissions import Permissions
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
from organization.models import Farm
from farms.models import FarmUnit
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
from animals.models import Animal, AnimalWeight
from django.db import IntegrityError
import uuid
from admin_panel.models import UnitType, Species, Breed
from subcriptions.models import SubscriptionPlan, Subscription
from common.utils import generate_ref
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.http import JsonResponse
from .models import (
    InseminationRecord,
    PregnancyRecord,
    BirthRecord,
    BirthOffspringRecord
    )
from core.models import GroupType
from django.core.exceptions import ValidationError
from .schema import (
    ListResponseSchema,
    APIResponse,
    InseminationRecordSchema,
    PregnancyRecordIn,
    BirthRecordIn,
    BirthOffspringRecordIn
 
)
from animals.event import new_event
router = Router(tags=["Reproduction"])
@router.post("/insemination/", response={200: APIResponse, 403: APIResponse},)
def insemination(
    request,
    payload:InseminationRecordSchema
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Reproduction.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
        
    farm = get_object_or_404(Farm, id =payload.farm_id, organization = org)
    animal = get_object_or_404(Animal, id = payload.animal_id, farm = farm)
    if InseminationRecord.objects.filter(farm=farm,animal=animal).exists():
        raise HttpError(409, "this record already exists")
    if animal.gender !="female":
        raise HttpError(400, "Insemination can only be performed on female animals.")
    if animal.is_pregnant:
        raise HttpError(400,"This animal is already pregnant")
    insemination_data = {
    "farm": farm,
    "animal": animal,
    "service_date": payload.service_date,
    "method": payload.method,
    "created_by": user
    }
    if payload.sire_reference:
        insemination_data["sire_reference"] = payload.sire_reference
    if payload.technician_name:
        insemination_data["technician_name"] = payload.technician_name
    if payload.notes:
        insemination_data["notes"] = payload.notes
    insemination = InseminationRecord(
        **insemination_data
    )
    try:
        insemination.full_clean()
        insemination.save()
    except ValidationError as e:
        return JsonResponse({
        "errors": e.message_dict
        }, status=400)
    new_event(
        insemination.farm, 
        insemination.animal,
        "insemination", 
        insemination.service_date,
        "Insemination recorded",
        insemination.method,
        "insemination",
        insemination.id,
        user
        )
    data={
        "name":insemination.animal.tag_id,
        "gender": insemination.animal.gender
    }
    return 200,APIResponse(
        success=True,
        message="insemination create successfully",
        data=data
    )
    
@router.get(
    "/insemination/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_insemination(
    request,
    page: int,
    page_size: int,
    farm_id: int
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Reproduction.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    insemination = InseminationRecord.objects.select_related("animal__breed").filter(farm=farm)
    paginator = Paginator(insemination, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "animal_tag": data.animal.tag_id,
                "breed": data.animal.breed.name,
                "date": data.service_date,
                "method": data.method,
                "sire_reference": data.sire_reference,
                "technician_name": data.technician_name,
                "notes": data.notes,
                "created_at": data.created_at,
                "created_by": data.created_by.email,
             
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"insemination fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )

@router.post("/pregnancy/", response={200: APIResponse, 403: APIResponse},)
def pregnancy(
    request,
    payload:PregnancyRecordIn
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Reproduction.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
        
    farm = get_object_or_404(Farm, id =payload.farm_id, organization = org)
    animal = get_object_or_404(Animal, id = payload.animal_id, farm = farm)
    if animal.gender !="female":
        raise HttpError(400, "Insemination can only be performed on female animals.")
    if animal.is_pregnant:
        raise HttpError(400,"This animal is already pregnant")
    pregnancy_data = {
    "farm": farm,
    "animal": animal,
    "result": payload.result,
    "check_date": payload.check_date,
    "created_by": user
    }
    if payload.insemination_id:
        insemination = get_object_or_404(InseminationRecord, id = payload.insemination_id, animal = animal)
        pregnancy_data["insemination"] = insemination
    if payload.expected_delivery_date:
        pregnancy_data["expected_delivery_date"] = payload.expected_delivery_date
    if payload.notes:
        pregnancy_data["notes"] = payload.notes
    pregnancy = PregnancyRecord(
        **pregnancy_data
    )
    try:
        pregnancy.full_clean()
        pregnancy.save()
    except ValidationError as e:
        return JsonResponse({
        "errors": e.message_dict
        }, status=400)
    new_event(
        pregnancy.farm, 
        pregnancy.animal,
        "pregnancy", 
        pregnancy.check_date,
        "pregnancy recorded",
        pregnancy.result,
        "pregnancy",
        pregnancy.id,
        user
        )
    data={
        "name":pregnancy.animal.tag_id,
        "gender": pregnancy.result
    }
    return 200,APIResponse(
        success=True,
        message="pregnancy create successfully",
        data=data
    )


@router.get(
    "/pregnancy/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_pregnancy(
    request,
    page: int,
    page_size: int,
    farm_id: int
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Reproduction.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    pregnancy = PregnancyRecord.objects.select_related("animal__species", "insemination", "created_by").filter(farm=farm)
    paginator = Paginator(pregnancy, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "animal": data.animal.species.name,
                "date": data.check_date,
                "result": data.result,
                "expected_delivery_date": data.expected_delivery_date,
                "notes": data.notes,
                "created_at": data.created_at,
                "created_by": data.created_by.email,
             
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"pregnancy fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )

@router.post("/birth/", response={200: APIResponse, 403: APIResponse},)
def birth(
    request,
    payload:BirthRecordIn
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Reproduction.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    
    farm = get_object_or_404(Farm, id =payload.farm_id, organization = org)
    animal = get_object_or_404(Animal, id = payload.mother_id, farm = farm)
    if animal.gender !="female":
        raise HttpError(400, "Insemination can only be performed on female animals.")
    if not animal.is_pregnant:
        raise HttpError(400,"mother must be pregnant")
    birth_data = {
    "farm": farm,
    "mother": animal,
    "birth_date": payload.birth_date,
    "number_of_offspring": payload.number_of_offspring,
    "number_alive": payload.number_alive,
    "number_dead": payload.number_dead,
    "created_by": user
    }
    if payload.notes:
        birth_data["notes"] = payload.notes
    birth = BirthRecord(
        **birth_data
    )
    try:
        birth.clean()
        birth.save()
        birth.mother.set_lactating()
    except ValidationError as e:
        return JsonResponse({
        "errors": e.message_dict
        }, status=400)
    new_event(
        birth.farm, 
        birth.mother,
        "birth", 
        birth.birth_date,
        "birth recorded",
        birth.number_of_offspring,
        "birth",
        birth.id,
        user
        )
    data={
        "name":birth.mother.tag_id,
        "gender": birth.number_of_offspring
    }
    return 200,APIResponse(
        success=True,
        message="birth create successfully",
        data=data
    )

@router.get(
    "/birth/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_birth(
    request,
    page: int,
    page_size: int,
    farm_id: int
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Reproduction.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    birth = BirthRecord.objects.select_related("mother__species", "created_by").filter(farm=farm)
    paginator = Paginator(birth, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "mother_tag": data.mother.tag_id,
                "species": data.mother.species.name,
                "breed": data.mother.breed.name,
                "birth_date": data.birth_date,
                "number_of_offspring": data.number_of_offspring,
                "number_alive": data.number_alive,
                "number_dead": data.number_dead,
                "notes": data.notes,
                "created_at": data.created_at,
                "created_by": data.created_by.email,
             
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"birth fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )

@router.post("/birth-offspring/", response={200: APIResponse, 403: APIResponse},)
def birth_offspring(
    request,
    payload:BirthOffspringRecordIn
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Reproduction.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
        
    farm = get_object_or_404(Farm, id =payload.farm_id, organization = org)
    birth_details = get_object_or_404(BirthRecord.objects.select_related("mother__unit", "mother__species", "mother__breed"), id = payload.birth_record_id)
    animal_data = {
        "status": "active",
        "gender": payload.gender,
        "source_type": "born",
        "farm": farm,
        "unit": birth_details.mother.unit,
        "tag_id": payload.tag_id,
        "species": birth_details.mother.species,
        "breed": birth_details.mother.breed,
        "mother": birth_details.mother,
        "dob": birth_details.birth_date,
        "health_status": payload.health_status,
        "is_pregnant": False,
        "is_lactating": False,
        "is_quarantine": False,
        "is_active": True,
    }
    with db_transaction.atomic():
        animal = Animal(
            **animal_data
        )
        try:
            animal.full_clean()
            animal.save()
        except ValidationError as e:
            return JsonResponse({
            "errors": e.message_dict
            }, status=400)
        
        birth_data = {
        "farm": farm,
        "offspring_animal": animal,
        "birth_record": birth_details,
        "gender": payload.gender,
        "birth_weight": payload.birth_weight,
        }
        birth = BirthOffspringRecord(
            **birth_data
        )
        try:
            birth.clean()
            birth.save()
        except ValidationError as e:
            return JsonResponse({
            "errors": e.message_dict
            }, status=400)
            
        birth_data = {
            "farm": farm,
            "animal": animal,
            "weight": payload.birth_weight,
            "date": birth_details.birth_date
         }

    try:
        weight = AnimalWeight(
        **birth_data
    )
        weight.full_clean()
        weight.save()

    except ValidationError as e:
        return JsonResponse({
        "errors": e.message_dict
        }, status=400)
  
    data={
        "name":birth.offspring_animal.tag_id,
        "gender": birth.birth_weight
    }
    return 200,APIResponse(
        success=True,
        message="birth offspring create successfully",
        data=data
    )

@router.get(
    "/birth-offspring/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_birth_offspring(
    request,
    page: int,
    page_size: int,
    farm_id: int
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Reproduction.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    birth = BirthOffspringRecord.objects.select_related("offspring_animal", "birth_record").filter(farm=farm)
    paginator = Paginator(birth, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "mother_tag": data.offspring_animal.tag_id,
                "species": data.offspring_animal.species.name,
                "breed": data.offspring_animal.breed.name,
                "gender": data.gender,
                "birth_weight": data.birth_weight,
                "created_at": data.created_at,
       
             
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"birth offspring fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )
