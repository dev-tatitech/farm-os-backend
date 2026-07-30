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
from admin_panel.models import UnitType, Species, Breed, LivestockSpecies, LivestockBreed, FarmHousingUnit, AnimalClassification
from subcriptions.models import SubscriptionPlan, Subscription
from common.utils import generate_ref
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.http import JsonResponse
from .models import (
    InseminationRecord,
    PregnancyRecord,
    BirthRecord,
    BirthOffspringRecord,
    BreedingEligibilityRule,
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
from .eligibility import check_breeding_eligibility, resolve_breeding_rule
from .seed import seed_breeding_rules
from admin_panel.models import LivestockSpecies, LivestockBreed
from animals.models import Animal
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

    is_override = bool(payload.override_reason)
    if is_override:
        override_perm = user_has_permission(user, Permissions.Reproduction.RESTRICTION_OVERRIDE)
        if not user.organizations.first():
            if not override_perm:
                raise HttpError(403, "Permission denied: overriding reproduction restrictions requires explicit authorization")
    else:
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
    if is_override:
        insemination._override_eligibility = True
    try:
        insemination.full_clean()
        insemination.save()
    except ValidationError as e:
        return JsonResponse({
        "errors": e.message_dict
        }, status=400)

    if is_override:
        from common.audit import log_audit
        log_audit(
            user=user, action="override_reproduction_restriction", source_module="reproduction",
            object_type="InseminationRecord", object_id=insemination.id,
            previous_value="blocked by breeding eligibility check", new_value="created via authorized override",
            reason=payload.override_reason,
        )

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
    insemination = InseminationRecord.objects.select_related(
        "animal__breed", "animal__livestock_breed", "created_by",
    ).filter(farm=farm)
    paginator = Paginator(insemination, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        a = data.animal
        serialized.append(
            {
                "id": data.id,
                "animal_tag": a.tag_id if a else None,
                "breed": (
                    (a.livestock_breed.name if a.livestock_breed else (a.breed.name if a.breed else None))
                    if a else None
                ),
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

    is_override = bool(payload.override_reason)
    if is_override:
        override_perm = user_has_permission(user, Permissions.Reproduction.RESTRICTION_OVERRIDE)
        if not user.organizations.first():
            if not override_perm:
                raise HttpError(403, "Permission denied: overriding reproduction restrictions requires explicit authorization")
    else:
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
    if is_override:
        pregnancy._override_eligibility = True
    try:
        pregnancy.full_clean()
        pregnancy.save()
    except ValidationError as e:
        return JsonResponse({
        "errors": e.message_dict
        }, status=400)

    if is_override:
        from common.audit import log_audit
        log_audit(
            user=user, action="override_reproduction_restriction", source_module="reproduction",
            object_type="PregnancyRecord", object_id=pregnancy.id,
            previous_value="blocked by breeding eligibility check", new_value="created via authorized override",
            reason=payload.override_reason,
        )

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
    pregnancy = PregnancyRecord.objects.select_related(
        "animal__species", "animal__livestock_species", "insemination", "created_by",
    ).filter(farm=farm)
    paginator = Paginator(pregnancy, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        a = data.animal
        serialized.append(
            {
                "id": data.id,
                "animal": (
                    (a.livestock_species.name if a.livestock_species else (a.species.name if a.species else None))
                    if a else None
                ),
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
    birth = BirthRecord.objects.select_related(
        "mother__species", "mother__breed",
        "mother__livestock_species", "mother__livestock_breed",
        "created_by",
    ).filter(farm=farm)
    paginator = Paginator(birth, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        m = data.mother
        serialized.append(
            {
                "id": data.id,
                "mother_tag": m.tag_id if m else None,
                "species": (
                    (m.livestock_species.name if m.livestock_species else (m.species.name if m.species else None))
                    if m else None
                ),
                "breed": (
                    (m.livestock_breed.name if m.livestock_breed else (m.breed.name if m.breed else None))
                    if m else None
                ),
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
    birth = BirthOffspringRecord.objects.select_related(
        "offspring_animal__species", "offspring_animal__breed",
        "offspring_animal__livestock_species", "offspring_animal__livestock_breed",
        "birth_record",
    ).filter(farm=farm)
    paginator = Paginator(birth, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        oa = data.offspring_animal
        serialized.append(
            {
                "id": data.id,
                "mother_tag": oa.tag_id if oa else None,
                "species": (
                    (oa.livestock_species.name if oa.livestock_species else (oa.species.name if oa.species else None))
                    if oa else None
                ),
                "breed": (
                    (oa.livestock_breed.name if oa.livestock_breed else (oa.breed.name if oa.breed else None))
                    if oa else None
                ),
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


# ── v2 endpoints ─────────────────────────────────────────────────────────────

@router.get(
    "/insemination/v2/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_insemination_v2(
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
    perm = user_has_permission(user, Permissions.Reproduction.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    insemination = InseminationRecord.objects.select_related(
        "animal__livestock_species",
        "animal__livestock_breed",
        "animal__species",
        "animal__breed",
        "created_by",
    ).filter(farm=farm)
    paginator = Paginator(insemination, page_size)
    page_obj = paginator.page(page)
    serialized = []
    for r in page_obj.object_list:
        serialized.append(
            {
                "id": r.id,
                "animal_tag": r.animal.tag_id,
                "species": r.animal.livestock_species.name if r.animal.livestock_species else (r.animal.species.name if r.animal.species else None),
                "breed": r.animal.livestock_breed.name if r.animal.livestock_breed else (r.animal.breed.name if r.animal.breed else None),
                "date": r.service_date,
                "method": r.method,
                "sire_reference": r.sire_reference,
                "technician_name": r.technician_name,
                "notes": r.notes,
                "created_at": r.created_at,
                "created_by": r.created_by.email,
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message="insemination fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )


@router.get(
    "/pregnancy/v2/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_pregnancy_v2(
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
    perm = user_has_permission(user, Permissions.Reproduction.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    pregnancy = PregnancyRecord.objects.select_related(
        "animal__livestock_species",
        "animal__livestock_breed",
        "animal__species",
        "animal__breed",
        "insemination",
        "created_by",
    ).filter(farm=farm)
    paginator = Paginator(pregnancy, page_size)
    page_obj = paginator.page(page)
    serialized = []
    for r in page_obj.object_list:
        serialized.append(
            {
                "id": r.id,
                "animal_tag": r.animal.tag_id,
                "species": r.animal.livestock_species.name if r.animal.livestock_species else (r.animal.species.name if r.animal.species else None),
                "breed": r.animal.livestock_breed.name if r.animal.livestock_breed else (r.animal.breed.name if r.animal.breed else None),
                "date": r.check_date,
                "result": r.result,
                "expected_delivery_date": r.expected_delivery_date,
                "notes": r.notes,
                "created_at": r.created_at,
                "created_by": r.created_by.email,
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message="pregnancy fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )


@router.get(
    "/birth/v2/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_birth_v2(
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
    perm = user_has_permission(user, Permissions.Reproduction.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    birth = BirthRecord.objects.select_related(
        "mother__livestock_species",
        "mother__livestock_breed",
        "mother__species",
        "mother__breed",
        "created_by",
    ).filter(farm=farm)
    paginator = Paginator(birth, page_size)
    page_obj = paginator.page(page)
    serialized = []
    for r in page_obj.object_list:
        serialized.append(
            {
                "id": r.id,
                "mother_tag": r.mother.tag_id,
                "species": r.mother.livestock_species.name if r.mother.livestock_species else (r.mother.species.name if r.mother.species else None),
                "breed": r.mother.livestock_breed.name if r.mother.livestock_breed else (r.mother.breed.name if r.mother.breed else None),
                "birth_date": r.birth_date,
                "number_of_offspring": r.number_of_offspring,
                "number_alive": r.number_alive,
                "number_dead": r.number_dead,
                "notes": r.notes,
                "created_at": r.created_at,
                "created_by": r.created_by.email,
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message="birth fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )


@router.post("/birth-offspring/v2/", response={200: APIResponse, 403: APIResponse},)
def birth_offspring_v2(
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
    perm = user_has_permission(user, Permissions.Reproduction.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")

    farm = get_object_or_404(Farm, id=payload.farm_id, organization=org)
    birth_details = get_object_or_404(
        BirthRecord.objects.select_related(
            "mother__unit",
            "mother__species",
            "mother__breed",
            "mother__livestock_species",
            "mother__livestock_breed",
            "mother__housing_unit",
        ),
        id=payload.birth_record_id,
    )
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
    if birth_details.mother.livestock_species:
        animal_data["livestock_species"] = birth_details.mother.livestock_species
    if birth_details.mother.livestock_breed:
        animal_data["livestock_breed"] = birth_details.mother.livestock_breed
    if birth_details.mother.housing_unit:
        animal_data["housing_unit"] = birth_details.mother.housing_unit
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
        "name": birth.offspring_animal.tag_id,
        "gender": birth.birth_weight
    }
    return 200, APIResponse(
        success=True,
        message="birth offspring create successfully",
        data=data
    )


@router.get(
    "/birth-offspring/v2/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_birth_offspring_v2(
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
    perm = user_has_permission(user, Permissions.Reproduction.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    birth = BirthOffspringRecord.objects.select_related(
        "offspring_animal__livestock_species",
        "offspring_animal__livestock_breed",
        "offspring_animal__species",
        "offspring_animal__breed",
        "birth_record",
    ).filter(farm=farm)
    paginator = Paginator(birth, page_size)
    page_obj = paginator.page(page)
    serialized = []
    for r in page_obj.object_list:
        serialized.append(
            {
                "id": r.id,
                "offspring_tag": r.offspring_animal.tag_id,
                "species": r.offspring_animal.livestock_species.name if r.offspring_animal.livestock_species else (r.offspring_animal.species.name if r.offspring_animal.species else None),
                "breed": r.offspring_animal.livestock_breed.name if r.offspring_animal.livestock_breed else (r.offspring_animal.breed.name if r.offspring_animal.breed else None),
                "gender": r.gender,
                "birth_weight": r.birth_weight,
                "created_at": r.created_at,
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message="birth offspring fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )


# ─── Breeding Eligibility Rules ───────────────────────────────────────────────

@router.post("/breeding-rule/seed/", response={200: APIResponse, 403: APIResponse})
def seed_breeding_rule(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    if not user.is_superuser:
        raise HttpError(403, "Permission Denied")

    created = seed_breeding_rules()
    return 200, APIResponse(success=True, message="Breeding rules seeded successfully", data={"created": created})


@router.get("/breeding-rule/{species_id}/", response={200: APIResponse, 403: APIResponse})
def get_breeding_rule(request, species_id: int, farm_id: int = None):
    user_id = get_current_user(request)
    try:
        users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    species = get_object_or_404(LivestockSpecies, id=species_id, is_active=True)
    qs = BreedingEligibilityRule.objects.filter(species=species, is_active=True)
    if farm_id:
        qs = qs.filter(Q(farm_id=farm_id) | Q(farm=None))
    else:
        qs = qs.filter(farm=None)
    data = list(qs.values(
        "id", "breed_id", "farm_id", "min_breeding_age_months", "recommended_breeding_age_months",
        "max_breeding_age_months", "min_breeding_weight_kg", "min_postpartum_interval_days",
        "max_births_lifetime", "allow_pregnant_and_lactating", "is_system",
    ))
    return 200, APIResponse(success=True, message="Breeding rules", data=data)


@router.post("/breeding-rule/", response={200: APIResponse, 403: APIResponse})
def create_farm_breeding_rule(
    request, farm_id: int, species_id: int, breed_id: int = None,
    min_breeding_age_months: float = None, recommended_breeding_age_months: float = None,
    max_breeding_age_months: float = None, min_breeding_weight_kg: float = None,
    min_postpartum_interval_days: int = None, max_births_lifetime: int = None,
    allow_pregnant_and_lactating: bool = True,
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(403, "Permission denied")
    perm = user_has_permission(user, Permissions.Reproduction.UPDATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied: configuring species breeding rules requires explicit authorization")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    species = get_object_or_404(LivestockSpecies, id=species_id, is_active=True)
    breed = get_object_or_404(LivestockBreed, id=breed_id) if breed_id else None

    previous_rule = BreedingEligibilityRule.objects.filter(species=species, breed=breed, farm=farm).first()
    previous_value = (
        f"min_age={previous_rule.min_breeding_age_months}, min_weight={previous_rule.min_breeding_weight_kg}"
        if previous_rule else None
    )

    rule, created = BreedingEligibilityRule.objects.update_or_create(
        species=species, breed=breed, farm=farm,
        defaults=dict(
            min_breeding_age_months=min_breeding_age_months,
            recommended_breeding_age_months=recommended_breeding_age_months,
            max_breeding_age_months=max_breeding_age_months,
            min_breeding_weight_kg=min_breeding_weight_kg,
            min_postpartum_interval_days=min_postpartum_interval_days,
            max_births_lifetime=max_births_lifetime,
            allow_pregnant_and_lactating=allow_pregnant_and_lactating,
            is_system=False,
        ),
    )

    from common.audit import log_audit
    log_audit(
        user=user, action="configure_species_rule", source_module="reproduction",
        object_type="BreedingEligibilityRule", object_id=rule.id,
        previous_value=previous_value,
        new_value=f"min_age={min_breeding_age_months}, min_weight={min_breeding_weight_kg}",
    )

    return 200, APIResponse(
        success=True,
        message="Farm breeding rule saved" if created else "Farm breeding rule updated",
        data={"id": rule.id},
    )


@router.get("/breeding-eligibility/{animal_id}/", response={200: APIResponse, 403: APIResponse})
def get_breeding_eligibility(request, animal_id: int, for_pregnancy: bool = False):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    animal = get_object_or_404(Animal, id=animal_id, farm__organization=org)
    is_eligible, reasons = check_breeding_eligibility(animal, farm=animal.farm, for_pregnancy=for_pregnancy)
    rule = resolve_breeding_rule(animal, farm=animal.farm)
    return 200, APIResponse(
        success=True,
        message="Breeding eligibility",
        data={
            "animal_id": animal.id,
            "is_eligible": is_eligible,
            "reasons": reasons,
            "rule_source": ("farm" if rule and rule.farm_id else "system") if rule else None,
        },
    )
