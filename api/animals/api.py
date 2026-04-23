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
from django.db import IntegrityError
import uuid
from admin_panel.models import UnitType, Species, Breed
from subcriptions.models import SubscriptionPlan, Subscription
from common.utils import generate_ref
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.http import JsonResponse
from .models import (
    Animal, 
    AnimalProfileAttribute,
    AnimalGroup,
    AnimalGroupMember
    )
from core.models import GroupType
from django.core.exceptions import ValidationError
from .schema import (
    ListResponseSchema,
    APIResponse,
    AnimalsSchemaIn,
    AnimalProfileAttributeSchemaIn,
    AnimalGroupSchemaIn,
    AnimalGroupMemberSchemaIn,
    AnimalGroupUpdateSchema,
    AnimalGroupMemberFilterSchema,
    UpdateAnimalGroupMemberSchemaIn
)
router = Router(tags=["Animals"])
@router.post("/animal/", response={200: APIResponse, 403: APIResponse},)
def new_animal(
    request,
    payload:AnimalsSchemaIn
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Animal.CREATE)
        raise HttpError(404, f"you are not admin {perm}")
    if Animal.objects.filter(tag_id__iexact=payload.tag_id).exists():
        raise HttpError(409, "tag ID already exists")
    farm = get_object_or_404(Farm, id =payload.farm_id)
    unit = get_object_or_404(FarmUnit, id = payload.unit_id)
    species = get_object_or_404(Species, id = payload.species_id)
    breed = get_object_or_404(Breed, id = payload.breed_id)
   
    animal_data = {
        "status": payload.status,
        "gender": payload.gender,
        "source_type": payload.source,
        "farm": farm,
        "unit": unit,
        "tag_id": payload.tag_id,
        "species": species,
        "breed": breed,
        "health_status": payload.health_status,
        "is_pregnant": payload.is_pregnant,
        "is_lactating": payload.is_lactating,
        "is_quarantine": payload.is_quarantine,
        "is_active": payload.is_active,
    }
    if payload.mother_id:
        mother = get_object_or_404(Animal, id = payload.mother_id)
        animal_data["mother"] = mother
    if payload.dob:
        animal_data["dob"] = payload.dob
    if payload.estimated_age_months:
        animal_data["estimated_age_months"] = payload.estimated_age_months
    if payload.notes:
        animal_data["notes"] = payload.notes 
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
    data={
        "name":animal.tag_id,
        "gender": animal.gender
    }
    return 200,APIResponse(
        success=True,
        message="animal create successfully",
        data=data
    )
    
@router.get(
    "/animal/{page}/{page_size}/{farm_id}",
    response={200: APIResponse, 403: APIResponse},
)
def get_animal(
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
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Animal.VIEW)
        raise HttpError(404, f"you are not admin {perm}")
    farm = get_object_or_404(Farm, id =farm_id)
    animals = Animal.objects.filter(farm = farm)
    paginator = Paginator(animals, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "unit": data.unit.name if data.unit else None,
                "species": data.species.name if data.species else None,
                "breed": data.breed.name if data.breed else None,
                "mother": data.mother.tag_id if data.mother else None,
                "tag_id": data.tag_id,
                "gender": data.gender,
                "source_type": data.source_type,
                "dob": data.dob,
                "estimated_age_months": data.estimated_age_months,
                "status": data.status,
                "health_status": data.health_status,
                "is_pregnant": data.is_pregnant,
                "is_lactating": data.is_lactating,
                "is_quarantine": data.is_quarantine,
                "is_active": data.is_active,
                "notes": data.notes
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"animals fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )

@router.post("/animal-profile-attribute/", response={200: APIResponse, 403: APIResponse},)
def animal_profile_attribute(
    request,
    payload:AnimalProfileAttributeSchemaIn
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Animal.CREATE)
        raise HttpError(404, f"you are not admin {perm}")
 
    animal = get_object_or_404(Animal, id = payload.animal_id)
    if AnimalProfileAttribute.objects.filter(attribute_key__iexact=payload.attribute_key, animal = animal).exists():
        raise HttpError(409, "attribute key already exists")
    profile = AnimalProfileAttribute.objects.create(
        animal = animal,
        attribute_key = payload.attribute_key,
        attribute_value = payload.attribute_value
    )
    data={
        "attribute_key":profile.attribute_key,
        "attribute_value": profile.attribute_value
    }
    return 200,APIResponse(
        success=True,
        message="animal profile attribute create successfully",
        data=data
    )
    
@router.get(
    "/animal-profile-attribute/{page}/{page_size}/{animal_id}",
    response={200: APIResponse, 403: APIResponse},
)
def get_animal_at_proile(
    request,
    page: int,
    page_size: int,
    animal_id: int
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Animal.VIEW)
        raise HttpError(404, f"you are not admin {perm}")
    animal = AnimalProfileAttribute.objects.filter(animal_id = animal_id)
    paginator = Paginator(animal, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "attribute_key": data.attribute_key,
                "attribute_value": data.attribute_value,
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"animal attribute fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )

@router.delete(
    "/animal-profile-attribute/{animal_attribute_id}",
    response={200: APIResponse, 403: APIResponse},
)
def delete_animal_at_proile(
    request,
    animal_attribute_id: int
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Animal.DELETE)
        raise HttpError(404, f"you are not admin {perm}")
    attr = get_object_or_404(AnimalProfileAttribute, id = animal_attribute_id)
    attr.delete()
    return 200,APIResponse(
        success=True,
        message="animal profile attribute deleted successfully",
        data=None
    )
    
@router.post(
    "/animal-group/",
    response={200: APIResponse, 403: APIResponse},
)
def animal_group(
    request,
    payload: AnimalGroupSchemaIn
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Animal.VIEW)
        raise HttpError(404, f"you are not admin {perm}")
    if not Farm.objects.filter(id=payload.farm_id).exists():
        raise HttpError(400, "Invalid farm_id")
    if not GroupType.objects.filter(id=payload.group_type_id).exists():
        raise HttpError(400, "Invalid group_type_id")
    try:
        group = AnimalGroup.objects.create(**payload.dict())
        return 200,APIResponse(
        success=True,
        message="animal group added successfully",
        data=None
    )
    except IntegrityError as e:
        raise HttpError(409, "Group with this name already exists in this farm")
    
    
@router.get(
    "/animal-group/{page}/{page_size}/{farm_id}",
    response={200: APIResponse, 403: APIResponse},
)
def get_animal_group(
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
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Animal.VIEW)
        raise HttpError(404, f"you are not admin {perm}")
    group = AnimalGroup.objects.select_related("farm", "group_type").filter(farm_id = farm_id)
    paginator = Paginator(group, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "farm": data.farm.name,
                "group_type": data.group_type.name,
                "name": data.name,
                "description": data.description,
                "status": data.status,
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"animal group fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )

@router.patch(
    "/update-animal-group/{group_id}",
    response={200: APIResponse, 403: APIResponse},
)
def update_animal_group(
    request,
    payload: AnimalGroupUpdateSchema,
    group_id:int
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Animal.UPDATE)
        raise HttpError(404, f"you are not admin {perm}")
    group = get_object_or_404(AnimalGroup, id=group_id)
    update_data = payload.dict(exclude_unset=True)
    for attr, value in update_data.items():
        setattr(group, attr, value)
    try:
        group.save()
        return 200,APIResponse(
        success=True,
        message="animal group updatd successfully",
        data=None
    )
    except IntegrityError:
        raise HttpError(409, "Duplicate group name for this farm")
    
@router.post(
    "/animal-group/",
    response={200: APIResponse, 403: APIResponse},
)
def animal_group(
    request,
    payload: AnimalGroupSchemaIn
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Animal.VIEW)
        raise HttpError(404, f"you are not admin {perm}")
    if not Farm.objects.filter(id=payload.farm_id).exists():
        raise HttpError(400, "Invalid farm_id")
    if not GroupType.objects.filter(id=payload.group_type_id).exists():
        raise HttpError(400, "Invalid group_type_id")
    try:
        group = AnimalGroup.objects.create(**payload.dict())
        return 200,APIResponse(
        success=True,
        message="animal group added successfully",
        data=None
    )
    except IntegrityError as e:
        raise HttpError(409, "Group with this name already exists in this farm")
    
@router.post(
    "/animal-group-member/",
    response={200: APIResponse, 403: APIResponse},
)
def animal_group_member(
    request,
    payload: AnimalGroupMemberSchemaIn
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Animal.VIEW)
        raise HttpError(404, f"you are not admin {perm}")
    if not Animal.objects.filter(id=payload.animal_id).exists():
        raise HttpError(400, "Invalid animal_id")
    if not AnimalGroup.objects.filter(id=payload.group_id).exists():
        raise HttpError(400, "Invalid group_id")
    try:
        member = AnimalGroupMember.objects.create(**payload.dict())
        return 200,APIResponse(
        success=True,
        message="animal group member added successfully",
        data=None
    )
    except IntegrityError as e:
        raise HttpError(409, "Group with this animal already exists in this group members")
    
@router.get(
    "/animal-group-member/{page}/{page_size}",
    response={200: APIResponse, 403: APIResponse},
)
def get_animal_group_member(
    request,
    page: int,
    page_size: int,
    filters:AnimalGroupMemberFilterSchema= Query(...)
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Animal.VIEW)
        raise HttpError(404, f"you are not admin {perm}")
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    query = Q()
    if filters.group_id is not None:
        query &= Q(group_id=filters.group_id)
    if filters.animal_id is not None:
        query &= Q(animal_id=filters.animal_id)
    if filters.status:
        query &= Q(status=filters.status)
    if filters.joined_after:
        query &= Q(joined_at__gte=filters.joined_after)
    if filters.joined_before:
        query &= Q(joined_at__lte=filters.joined_before)
    if filters.search:
        search_query = (
        Q(animal__tag_id__icontains=filters.search) |
        Q(status__icontains=filters.search) |
        Q(group__name__icontains=filters.search)
    )
        query &= search_query
    member = AnimalGroupMember.objects.select_related(
        "animal", "group"
    ).filter(query)
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #group = AnimalGroup.objects.select_related("farm", "group_type").filter(farm_id = farm_id)
    paginator = Paginator(member, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "group":{
                    "id":data.group.id,
                    "name": data.group.name,
                    "description": data.group.description
                    },
                "animal":{
                    "id": data.animal.id,
                    "tag": data.animal.tag_id
                },
                "joined_at": data.joined_at.strftime("%Y-%m-%d %H:%M:%S") if data.joined_at else None,
                "removed_at": data.removed_at.strftime("%Y-%m-%d %H:%M:%S") if data.removed_at else None,
                "status": data.status,
       
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"animal group member fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )

@router.patch(
    "/update-animal-group-member/{member_id}",
    response={200: APIResponse, 403: APIResponse},
)
def update_animal_group_member(
    request,
    payload: UpdateAnimalGroupMemberSchemaIn,
    member_id:int
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Animal.UPDATE)
        raise HttpError(404, f"you are not admin {perm}")
    group = get_object_or_404(AnimalGroupMember, id=member_id)
    if payload.status==AnimalGroupMember.Status.REMOVED:
        group.remove()
        return 200,APIResponse(
        success=True,
        message="animal group member updatd successfully",
        data=None)
    update_data = payload.dict(exclude_unset=True)
    update_data.pop("status", None)
    for attr, value in update_data.items():
        setattr(group, attr, value)
    try:
        group.save()
        return 200,APIResponse(
        success=True,
        message="animal group member updatd successfully",
        data=None
    )
    except IntegrityError:
        raise HttpError(409, "Duplicate group name for this farm")
 