from ninja import Router, Query, Form
from django.conf import settings
from ninja import File
from account.auth import get_current_user, validate_crftoken
from account.models import User as users
from django.db.models import Q
from ninja.files import UploadedFile
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
from .event import new_event
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
    AnimalGroupMember,
    AnimalEvent,
    AnimalWeight,
    MilkRecord
    )
from core.models import GroupType
from django.core.exceptions import ValidationError
from .schema import (
    ListResponseSchema,
    APIResponse,
    AnimalsSchemaIn,
    AnimalsSchemaInV2,
    AnimalProfileAttributeSchemaIn,
    AnimalGroupSchemaIn,
    AnimalGroupMemberSchemaIn,
    AnimalGroupUpdateSchema,
    AnimalGroupMemberFilterSchema,
    UpdateAnimalGroupMemberSchemaIn,
    AnimalsUpdateSchemaIn,
    AnimalsUpdateSchemaInV2,
    AnimalWeightIn,
    MilkRecordSchema,
    AnimalAcquisitionSchemaIn,
)
from .acquisition import save_animal_acquisition
from finance.services import get_financial_profile
from admin_panel.models import (
    LivestockSpecies,
    LivestockBreed,
    HousingUnitType,
    FarmHousingUnit,
)
from .growth import weight_gain, average_daily_gain, percentage_weight_change, weight_trend, cost_per_kg_gained
router = Router(tags=["Animals"])
@router.post("/animal/", response={200: APIResponse, 403: APIResponse})
def new_animal(
    request,
    payload: AnimalsSchemaIn,
    image: UploadedFile = File(None),
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
    perm = user_has_permission(user,Permissions.Animal.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")

    farm = get_object_or_404(Farm, id =payload.farm_id, organization = org)  
    if Animal.objects.filter(tag_id__iexact=payload.tag_id, farm = farm).exists():
        raise HttpError(409, "tag ID already exists")
    
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
        mother = get_object_or_404(Animal, id = payload.mother_id, farm = farm)
        animal_data["mother"] = mother
    if payload.dob:
        animal_data["dob"] = payload.dob
    if payload.estimated_age_months:
        animal_data["estimated_age_months"] = payload.estimated_age_months
    if payload.notes:
        animal_data["notes"] = payload.notes
    if image:
        animal_data["image"] = image
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
        "gender": animal.gender,
    }
    return 200,APIResponse(
        success=True,
        message="animal create successfully",
        data=data
    )
    
@router.get(
    "/animal/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
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
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Animal.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")

    farm = get_object_or_404(Farm, id =farm_id, organization = org)
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

@router.get(
    "/animal-by-id/{animal_id}",
    response={200: APIResponse, 403: APIResponse},
)
def get_animal_by_id(
    request,
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
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Animal.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")

    data = get_object_or_404(Animal, id = animal_id)
    serialized = {
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
    return 200,APIResponse(
        success=True,
        message="animal details successfully",
        data=serialized
    )

@router.post("/animal/image/{animal_id}", response={200: APIResponse, 403: APIResponse})
def update_animal_image(
    request,
    animal_id: int,
    image: UploadedFile = File(...),
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    animal = get_object_or_404(Animal, id=animal_id)

    if animal.image:
        try:
            animal.image.delete(save=False)
        except Exception:
            pass

    animal.image = image
    animal.save(update_fields=["image"])

    return 200, APIResponse(
        success=True,
        message="Animal image updated successfully",
        data={"id": animal.id, "image_url": animal.image.url},
    )


@router.patch("/animal/{animal_id}/{farm_id}", response={200: APIResponse, 403: APIResponse},)
def update_animal(
    request,
    payload:AnimalsUpdateSchemaIn,
    animal_id: int,
    farm_id: int
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
    perm = user_has_permission(user,Permissions.Animal.UPDATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")

    farm = get_object_or_404(Farm, id= farm_id, organization = org)
    animal = get_object_or_404(Animal.objects.select_related("farm", "unit"), id = animal_id, farm = farm)
    if payload.tag_id:
        if Animal.objects.filter(
            tag_id__iexact=payload.tag_id,
            farm=animal.farm
        ).exclude(id=animal.id).exists():
            raise HttpError(409, "tag ID already exists")
        animal.tag_id = payload.tag_id

    if payload.new_farm_id:
        animal.farm = get_object_or_404(Farm, id=payload.farm_id)

    if payload.unit_id:
        animal.unit = get_object_or_404(FarmUnit, id=payload.unit_id)

    if payload.species_id:
        animal.species = get_object_or_404(Species, id=payload.species_id)

    if payload.breed_id:
        animal.breed = get_object_or_404(Breed, id=payload.breed_id)

    if payload.mother_id:
        animal.mother = get_object_or_404(Animal, id=payload.mother_id)

    if payload.gender is not None:
        animal.gender = payload.gender

    if payload.source is not None:
        animal.source_type = payload.source

    if payload.dob is not None:
        animal.dob = payload.dob

    if payload.estimated_age_months is not None:
        animal.estimated_age_months = payload.estimated_age_months

    if payload.status is not None:
        animal.status = payload.status

    if payload.health_status is not None:
        animal.health_status = payload.health_status

    if payload.is_pregnant is not None:
        animal.is_pregnant = payload.is_pregnant

    if payload.is_lactating is not None:
        animal.is_lactating = payload.is_lactating

    if payload.is_quarantine is not None:
        animal.is_quarantine = payload.is_quarantine

    if payload.is_active is not None:
        animal.is_active = payload.is_active

    if payload.notes is not None:
        animal.notes = payload.notes

    animal.save()
    data={
        "name":animal.tag_id,
        "gender": animal.gender
    }
    return 200,APIResponse(
        success=True,
        message="animal updated successfully",
        data=data
    )
    
@router.post("/animal-profile-attribute/{farm_id}", response={200: APIResponse, 403: APIResponse},)
def animal_profile_attribute(
    request,
    payload:AnimalProfileAttributeSchemaIn,
    farm_id: int
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
    perm = user_has_permission(user,Permissions.Animal.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    animal = get_object_or_404(Animal, id=payload.animal_id, farm=farm)
    if AnimalProfileAttribute.objects.filter(attribute_key__iexact=payload.attribute_key, animal=animal).exists():
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
    response={200: ListResponseSchema, 403: APIResponse},
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
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Animal.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
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
    "/animal-profile-attribute/delete/{animal_attribute_id}",
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
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Animal.DELETE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
        
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
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Animal.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
        
    if not Farm.objects.filter(id=payload.farm_id, organization=org).exists():
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
    response={200: ListResponseSchema, 403: APIResponse},
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
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Animal.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id = farm_id, organization = org)
    group = AnimalGroup.objects.select_related("farm", "group_type").filter(farm = farm)
    paginator = Paginator(group, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "farm": data.farm.name,
                "group_type": data.group_type.name if data.group_type else None,
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
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Animal.UPDATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
        
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
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Animal.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
        
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
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Animal.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    
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
    response={200: ListResponseSchema, 403: APIResponse},
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
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Animal.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    
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
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Animal.UPDATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    
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
 
@router.get(
    "/animal-event/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_animal_event(
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
    perm = user_has_permission(user,Permissions.Animal.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    
    event = AnimalEvent.objects.select_related("group", "animal", "event_type", "created_by").filter(farm_id = farm_id)
    paginator = Paginator(event, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "group": data.group.name if data.group else None,
                "animal_id": data.animal.id if data.animal else None,
                "tag": data.animal.tag_id if data.animal else None,
                "species": data.animal.species.name if data.animal else None,
                "breed": data.animal.breed.name if data.animal else None,
                "event_type": data.event_type.name,
                "event_title": data.event_title,
                "event_summary": data.event_summary,
                "reference_table": data.reference_table,
                "reference_id": data.reference_id,
                "created_at": data.created_at,
                "created_by": data.created_by.email,
             
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"animal event fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )

@router.post("/animal-weight/", response={200: APIResponse, 403: APIResponse},)
def weight(
    request,
    payload:AnimalWeightIn
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
    perm = user_has_permission(user,Permissions.Animal.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    
    farm = get_object_or_404(Farm, id =payload.farm_id)
    animal = get_object_or_404(Animal, id = payload.animal_id, farm = farm)
    birth_data = {
    "farm": farm,
    "animal": animal,
    "weight": payload.weight,
    "date": payload.date
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
        "name":weight.weight,
        "gender": weight.date
    }
    return 200,APIResponse(
        success=True,
        message="weight create successfully",
        data=data
    )

@router.get(
    "/animal-weight/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_animal_weight(
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
    perm = user_has_permission(user,Permissions.Animal.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    weight = AnimalWeight.objects.select_related("animal").filter(farm_id = farm_id)
    paginator = Paginator(weight, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "animal_id": data.animal.id,
                "tag": data.animal.tag_id,
                "species": data.animal.species.name,
                "breed": data.animal.breed.name,
                "date": data.date,
                "weight": data.weight,
                "created_at": data.created_at,
            
             
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"animal weight fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )


@router.get(
    "/animal-weight/animal/{animal_id}",
    response={200: APIResponse, 403: APIResponse},
)
def get_animal_weight_by_animal(request, animal_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not user.organizations.first():
        perm = user_has_permission(user, Permissions.Animal.VIEW)
        raise HttpError(404, f"you are not admin {perm}")
    animal = get_object_or_404(Animal, id=animal_id)
    weights = AnimalWeight.objects.filter(animal=animal).order_by("-date")
    data = [
        {
            "id": w.id,
            "date": w.date,
            "weight": w.weight,
            "created_at": w.created_at,
        }
        for w in weights
    ]
    return 200, APIResponse(success=True, message="Animal weight records", data=data)


#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
@router.post("/milk/", response={200: APIResponse, 403: APIResponse},tags=["Production"])
def milk(
    request,
    payload:MilkRecordSchema
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
    perm = user_has_permission(user,Permissions.Production.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    

    farm = get_object_or_404(Farm, id =payload.farm_id, organization = org)
    animal = get_object_or_404(Animal, id = payload.animal_id, farm = farm)
    milk_data = {
    "farm": farm,
    "animal": animal,
    "record_date": payload.record_date,
    "session": payload.session,
    "quantity": payload.quantity,
    "created_by": user
    }
    if payload.notes:
        milk_data["notes"] = payload.notes
    milk = MilkRecord(
        **milk_data
    )
    try:
        milk.full_clean()
        milk.save()
    except ValidationError as e:
        return JsonResponse({
        "errors": e.message_dict
        }, status=400)
    """ 
   AnimalEvent.objects.create(
    farm=self.farm,
    animal=self.animal,
    event_type=event_type,  # quarantine
    event_date=self.start_date,
    event_title=f"Quarantine - {self.status}",
    event_summary=self.reason,
    reference_table="quarantine_record",
    reference_id=self.id,
    created_by=self.created_by,
)
)
    """
    new_event(
    milk.farm,
    milk.animal,
    "milk",
    milk.record_date,
    f"Milk Recorded - {milk.session}",
    f"{milk.quantity} liters",
    "milk_record",
    milk.id,
    user
)
    data={
        "session":milk.session,
        "start_date": milk.record_date
    }
    return 200,APIResponse(
        success=True,
        message="milk create successfully",
        data=data
    )

@router.get(
    "/milk/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
    tags=["Production"]
)
def get_milk(
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
    perm = user_has_permission(user,Permissions.Production.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    milk = MilkRecord.objects.select_related("animal__species", "created_by").filter(farm = farm)
    paginator = Paginator(milk, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "animal_id": data.animal.id if data.animal else None,
                "animal_tag": data.animal.tag_id if data.animal else None,
                "species": data.animal.species.name if data.animal else None,
                "breed": data.animal.breed.name if data.animal else None,
                "record_date": data.record_date,
                "session": data.session,
                "quantity": data.quantity,
                "created_at": data.created_at,
                "created_by": data.created_by.email,
             
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"milk fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )


@router.get("/animal-profile/{animal_id}", response={200: APIResponse, 403: APIResponse})
def animal_profile(request, animal_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")

    from reproduction.models import InseminationRecord, PregnancyRecord
    from health.models import VaccinationRecord, TreatmentRecord
    from feed.models import FeedIssuanceRecord, FeedPlan
    from movement_records.models import MovementRecord

    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Animal.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    
    animal = get_object_or_404(
        Animal.objects.select_related("species", "breed", "farm", "unit", "mother"),
        id=animal_id,
    )

    # ── Overview ───────────────────────────────────────────────────────────────
    overview = {
        "breed": animal.breed.name,
        "mother_tag": animal.mother.tag_id if animal.mother else None,
        "source": animal.get_source_type_display(),
        "unit": animal.unit.name if animal.unit else None,
        "farm": animal.farm.name,
        "entry_date": animal.created_at.date(),
    }

    # ── Reproduction ───────────────────────────────────────────────────────────
    last_insemination = (
        InseminationRecord.objects.filter(animal=animal)
        .order_by("-service_date")
        .values("service_date", "method")
        .first()
    )
    pregnancy = (
        PregnancyRecord.objects.filter(animal=animal)
        .order_by("-check_date")
        .values("result", "expected_delivery_date")
        .first()
    )

    if animal.is_lactating:
        pregnancy_status = "Lactating"
    elif animal.is_pregnant:
        pregnancy_status = "Pregnant"
    else:
        pregnancy_status = "Not Pregnant"

    reproduction = {
        "last_insemination_date": last_insemination["service_date"] if last_insemination else None,
        "expected_delivery_date": pregnancy["expected_delivery_date"] if pregnancy else None,
        "pregnancy_status": pregnancy_status,
    }

    # ── Production ─────────────────────────────────────────────────────────────
    today = timezone.localdate()
    milk_today = (
        MilkRecord.objects.filter(animal=animal, record_date=today)
        .aggregate(total=Sum("quantity"))["total"] or 0
    )
    production = {
        "lactation_status": "Lactating" if animal.is_lactating else "Not Lactating",
        "milk_production_today": milk_today,
    }

    # ── Health ─────────────────────────────────────────────────────────────────
    last_vaccination = (
        VaccinationRecord.objects.filter(animal=animal)
        .order_by("-date_given")
        .values("vaccine_name", "date_given", "next_due_date")
        .first()
    )
    last_treatment = (
        TreatmentRecord.objects.filter(animal=animal)
        .order_by("-treatment_date")
        .values("diagnosis", "treatment_date")
        .first()
    )
    health = {
        "vaccination_status": "Vaccinated" if last_vaccination else "Not Vaccinated",
        "last_vaccine": last_vaccination["vaccine_name"] if last_vaccination else None,
        "next_due_date": last_vaccination["next_due_date"] if last_vaccination else None,
        "last_treatment_date": last_treatment["treatment_date"] if last_treatment else None,
        "last_diagnosis": last_treatment["diagnosis"] if last_treatment else None,
    }

    # ── Feeding ────────────────────────────────────────────────────────────────
    last_issuance = (
        FeedIssuanceRecord.objects.filter(animal=animal)
        .order_by("-created_at")
        .first()
    )
    feed_plan = (
        FeedPlan.objects.filter(
            farm=animal.farm,
            species=animal.species,
            status="active",
        )
        .order_by("-start_date")
        .values("daily_feed_quantity", "unit")
        .first()
    )

    if last_issuance:
        delta = timezone.now() - last_issuance.created_at
        total_minutes = int(delta.total_seconds() // 60)
        if total_minutes < 60:
            last_feeding_ago = f"{total_minutes} min ago"
        elif total_minutes < 1440:
            last_feeding_ago = f"{total_minutes // 60} hours ago"
        else:
            last_feeding_ago = f"{total_minutes // 1440} days ago"
    else:
        last_feeding_ago = None

    feeding = {
        "last_feeding": last_feeding_ago,
        "last_feeding_date": last_issuance.issue_date if last_issuance else None,
        "feed_pattern": (
            f"{feed_plan['daily_feed_quantity']} {feed_plan['unit']} / day"
            if feed_plan else None
        ),
    }

    # ── Movement ───────────────────────────────────────────────────────────────
    current_location = animal.unit.name if animal.unit else None
    movement_history_qs = (
        MovementRecord.objects.select_related("to_unit")
        .filter(animal=animal)
        .order_by("-move_date")
        .values("to_unit__name", "move_date")
    )
    movement_history = [
        {
            "location": row["to_unit__name"],
            "date": row["move_date"].date() if row["move_date"] else None,
        }
        for row in movement_history_qs
    ]
    movement = {
        "current_location": current_location,
        "movement_history": movement_history,
    }

    # ── Card summary (top of profile) ──────────────────────────────────────────
    today = timezone.localdate()
    if animal.dob:
        age_months = (today.year - animal.dob.year) * 12 + (today.month - animal.dob.month)
    else:
        age_months = animal.estimated_age_months

    def lifecycle_stage(months):
        if months is None:
            return None
        if months < 3:
            return {"stage": 1, "label": "Newborn"}
        if months < 6:
            return {"stage": 2, "label": "Calf"}
        if months < 12:
            return {"stage": 3, "label": "Weaner"}
        if months < 24:
            return {"stage": 4, "label": "Yearling"}
        return {"stage": 5, "label": "Adult"}

    if animal.is_lactating:
        status_badge = "Lactating"
    elif animal.is_pregnant:
        status_badge = "Pregnant"
    elif animal.is_quarantine:
        status_badge = "Quarantine"
    elif animal.health_status != "healthy":
        status_badge = animal.health_status.replace("_", " ").title()
    else:
        status_badge = animal.status.title()

    request_host = request.build_absolute_uri("/").rstrip("/")
    image_url = f"{request_host}{animal.image.url}" if animal.image else None

    card = {
        "id": animal.id,
        "tag_id": animal.tag_id,
        "species": animal.species.name,
        "gender": animal.gender,
        "status_badge": status_badge,
        "age_months": age_months,
        "location": animal.unit.name if animal.unit else None,
        "lifecycle": lifecycle_stage(age_months),
        "image_url": image_url,
    }

    data = {
        "card": card,
        "overview": overview,
        "reproduction": reproduction,
        "production": production,
        "health": health,
        "feeding": feeding,
        "movement": movement,
    }
    return 200, APIResponse(success=True, message="Animal profile", data=data)
    

# ─── v2 Endpoints (Livestock Master Data) ────────────────────────────────────

@router.post("/animal/v2/", response={200: APIResponse, 403: APIResponse})
def new_animal_v2(
    request,
    payload: AnimalsSchemaInV2 = Form(...),
    image: UploadedFile = File(None),
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Animal.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")

    farm = get_object_or_404(Farm, id=payload.farm_id, organization=org)

    if Animal.objects.filter(tag_id__iexact=payload.tag_id, farm=farm).exists():
        raise HttpError(409, "Tag ID already exists")

    # ── Validate master data references ──────────────────────────────────────
    livestock_species = get_object_or_404(LivestockSpecies, id=payload.livestock_species_id, is_active=True)

    livestock_breed = get_object_or_404(LivestockBreed, id=payload.livestock_breed_id, is_active=True)
    if livestock_breed.species_id != livestock_species.id:
        raise HttpError(422, f"Breed '{livestock_breed.name}' does not belong to species '{livestock_species.name}'")
    if livestock_breed.farm and livestock_breed.farm_id != farm.id:
        raise HttpError(422, "This breed is not available for your farm")

    housing_unit = get_object_or_404(FarmHousingUnit, id=payload.housing_unit_id, farm=farm, status="active")
    if housing_unit.allowed_species.exists() and not housing_unit.allowed_species.filter(id=livestock_species.id).exists():
        raise HttpError(422, f"Housing unit '{housing_unit.name}' does not support species '{livestock_species.name}'")

    # ── Build animal ──────────────────────────────────────────────────────────
    animal_data = {
        "status": payload.status,
        "gender": payload.gender,
        "source_type": payload.source,
        "farm": farm,
        "tag_id": payload.tag_id,
        "health_status": payload.health_status,
        "is_pregnant": payload.is_pregnant,
        "is_lactating": payload.is_lactating,
        "is_quarantine": payload.is_quarantine,
        "is_active": payload.is_active,
        "livestock_species": livestock_species,
        "livestock_breed": livestock_breed,
        "housing_unit": housing_unit,
    }
    if payload.mother_id:
        mother = get_object_or_404(Animal, id=payload.mother_id, farm=farm)
        animal_data["mother"] = mother
    if payload.dob:
        animal_data["dob"] = payload.dob
    if payload.estimated_age_months:
        animal_data["estimated_age_months"] = payload.estimated_age_months
    if payload.notes:
        animal_data["notes"] = payload.notes
    if image:
        animal_data["image"] = image

    animal = Animal(**animal_data)
    try:
        animal.full_clean()
        animal.save()
    except ValidationError as e:
        return JsonResponse({"errors": e.message_dict}, status=400)

    return 200, APIResponse(
        success=True,
        message="Animal created successfully",
        data={
            "id": animal.id,
            "tag_id": animal.tag_id,
            "gender": animal.gender,
            "species": livestock_species.name,
            "breed": livestock_breed.name,
            "housing_unit": housing_unit.name,
        },
    )


@router.post("/animal/{animal_id}/acquisition/", response={200: APIResponse, 403: APIResponse})
def set_animal_acquisition(request, animal_id: int, payload: AnimalAcquisitionSchemaIn):
    """
    Records how an animal entered the farm (purchase/import/born/opening
    record) and turns that into the animal's cost baseline. Purchased and
    imported costs are posted as a single "Acquisition" Finance transaction;
    born-on-farm costs are internal production costs, so they're posted
    under their own categories (Breeding/Veterinary Service/Feed) instead of
    as an acquisition purchase, per spec 2.4. Safe to call more than once
    (e.g. to fill in a receipt after the fact) — it updates the same
    AnimalAcquisition row and only ever posts each cost transaction once.
    """
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
    acq = save_animal_acquisition(animal, payload, user)

    profile = get_financial_profile(animal)
    return 200, APIResponse(
        success=True,
        message="Animal acquisition recorded successfully",
        data={
            "animal_id": animal.id,
            "source_type": animal.source_type,
            "acquisition_cost": profile.acquisition_cost if profile else None,
            "opening_value": profile.opening_value if profile else None,
        },
    )


@router.get(
    "/animal/v2/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_animal_v2(request, page: int, page_size: int, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")

    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Animal.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    qs = Animal.objects.select_related(
        "livestock_species", "livestock_breed", "housing_unit", "mother",
    ).filter(farm=farm)

    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)

    serialized = []
    for a in page_obj.object_list:
        serialized.append({
            "id": a.id,
            "tag_id": a.tag_id,
            "gender": a.gender,
            "species": a.livestock_species.name if a.livestock_species else (a.species.name if a.species else None),
            "breed": a.livestock_breed.name if a.livestock_breed else (a.breed.name if a.breed else None),
            "housing_unit": a.housing_unit.name if a.housing_unit else (a.unit.name if a.unit else None),
            "mother_tag": a.mother.tag_id if a.mother else None,
            "source_type": a.source_type,
            "dob": a.dob,
            "estimated_age_months": a.estimated_age_months,
            "status": a.status,
            "health_status": a.health_status,
            "is_pregnant": a.is_pregnant,
            "is_lactating": a.is_lactating,
            "is_quarantine": a.is_quarantine,
            "is_active": a.is_active,
            "notes": a.notes,
        })

    return 200, ListResponseSchema(
        success=True,
        message="Animals fetched successfully",
        data=serialized,
        num_pages=paginator.num_pages,
        current_page=page_obj.number,
        total_items=paginator.count,
        has_next=page_obj.has_next,
        has_previous=page_obj.has_previous,
    )


@router.get("/animal-profile/v2/{animal_id}", response={200: APIResponse, 403: APIResponse})
def animal_profile_v2(request, animal_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")

    from reproduction.models import InseminationRecord, PregnancyRecord
    from health.models import VaccinationRecord, TreatmentRecord
    from feed.models import FeedIssuanceRecord
    from movement_records.models import MovementRecord

    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Animal.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")

    animal = get_object_or_404(
        Animal.objects.select_related(
            "livestock_species", "livestock_breed", "housing_unit",
            "species", "breed", "farm", "unit", "mother",
        ),
        id=animal_id,
    )

    # ── Age ────────────────────────────────────────────────────────────────────
    today = timezone.localdate()
    if animal.dob:
        from dateutil.relativedelta import relativedelta as rdelta
        diff = rdelta(today, animal.dob)
        age_months = diff.years * 12 + diff.months
    else:
        age_months = animal.estimated_age_months or 0

    if age_months <= 3:
        lifecycle_stage, lifecycle_label = 1, "Newborn"
    elif age_months <= 6:
        lifecycle_stage, lifecycle_label = 2, "Calf"
    elif age_months <= 12:
        lifecycle_stage, lifecycle_label = 3, "Weaner"
    elif age_months <= 24:
        lifecycle_stage, lifecycle_label = 4, "Yearling"
    else:
        lifecycle_stage, lifecycle_label = 5, "Adult"

    species_name = (animal.livestock_species.name if animal.livestock_species else (animal.species.name if animal.species else None))
    breed_name = (animal.livestock_breed.name if animal.livestock_breed else (animal.breed.name if animal.breed else None))
    unit_name = (animal.housing_unit.name if animal.housing_unit else (animal.unit.name if animal.unit else None))

    # ── Card ───────────────────────────────────────────────────────────────────
    image_url = None
    if animal.image:
        image_url = animal.image.url

    card = {
        "id": animal.id,
        "tag_id": animal.tag_id,
        "species": species_name,
        "breed": breed_name,
        "gender": animal.gender,
        "status": animal.status,
        "age_months": age_months,
        "lifecycle_stage": lifecycle_stage,
        "lifecycle_label": lifecycle_label,
        "housing_unit": unit_name,
        "image_url": image_url,
    }

    # ── Overview ───────────────────────────────────────────────────────────────
    overview = {
        "species": species_name,
        "breed": breed_name,
        "mother_tag": animal.mother.tag_id if animal.mother else None,
        "source": animal.get_source_type_display(),
        "housing_unit": unit_name,
        "farm": animal.farm.name,
        "entry_date": animal.created_at.date(),
    }

    # ── Reproduction ───────────────────────────────────────────────────────────
    last_insemination = (
        InseminationRecord.objects.filter(animal=animal)
        .order_by("-service_date")
        .values("service_date", "method")
        .first()
    )
    pregnancy = (
        PregnancyRecord.objects.filter(animal=animal)
        .order_by("-check_date")
        .values("result", "expected_delivery_date")
        .first()
    )
    if animal.is_lactating:
        preg_status = "Lactating"
    elif animal.is_pregnant:
        preg_status = "Pregnant"
    else:
        preg_status = "Not Pregnant"

    reproduction = {
        "last_insemination_date": last_insemination["service_date"] if last_insemination else None,
        "expected_delivery_date": pregnancy["expected_delivery_date"] if pregnancy else None,
        "pregnancy_status": preg_status,
    }

    # ── Production ─────────────────────────────────────────────────────────────
    milk_today = (
        MilkRecord.objects.filter(animal=animal, record_date=today)
        .aggregate(total=Sum("quantity"))["total"] or 0
    )
    production = {
        "lactation_status": "Lactating" if animal.is_lactating else "Not Lactating",
        "milk_production_today": milk_today,
    }

    # ── Health ─────────────────────────────────────────────────────────────────
    last_vaccination = (
        VaccinationRecord.objects.filter(animal=animal)
        .order_by("-date_given")
        .values("vaccine_name", "date_given", "next_due_date")
        .first()
    )
    last_treatment = (
        TreatmentRecord.objects.filter(animal=animal)
        .order_by("-treatment_date")
        .values("diagnosis", "treatment_date", "severity")
        .first()
    )
    health = {
        "health_status": animal.health_status,
        "is_quarantine": animal.is_quarantine,
        "last_vaccination": last_vaccination,
        "last_treatment": last_treatment,
    }

    # ── Feeding ────────────────────────────────────────────────────────────────
    last_feed = (
        FeedIssuanceRecord.objects.filter(animal=animal)
        .order_by("-issue_date")
        .values("issue_date", "quantity_issued")
        .first()
    )
    feeding = {"last_feed_issuance": last_feed}

    # ── Movement ───────────────────────────────────────────────────────────────
    last_movement = (
        MovementRecord.objects.filter(animal=animal)
        .select_related("from_housing_unit", "to_housing_unit", "from_unit", "to_unit")
        .order_by("-move_date")
        .first()
    )
    movement = {
        "last_move_date": last_movement.move_date if last_movement else None,
        "from_unit": (
            (last_movement.from_housing_unit.name if last_movement.from_housing_unit else None)
            or (last_movement.from_unit.name if last_movement.from_unit else None)
        ) if last_movement else None,
        "to_unit": (
            (last_movement.to_housing_unit.name if last_movement.to_housing_unit else None)
            or (last_movement.to_unit.name if last_movement.to_unit else None)
        ) if last_movement else None,
    }

    data = {
        "card": card,
        "overview": overview,
        "reproduction": reproduction,
        "production": production,
        "health": health,
        "feeding": feeding,
        "movement": movement,
    }
    return 200, APIResponse(success=True, message="Animal profile", data=data)


# ─── v2 Additional Endpoints ──────────────────────────────────────────────────

@router.get("/animal-by-id/v2/{animal_id}", response={200: APIResponse, 403: APIResponse})
def get_animal_by_id_v2(request, animal_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")

    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Animal.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")

    a = get_object_or_404(
        Animal.objects.select_related(
            "livestock_species", "livestock_breed",
            "housing_unit",
            "species", "breed", "unit", "mother",
        ),
        id=animal_id,
    )

    serialized = {
        "id": a.id,
        "tag_id": a.tag_id,
        "gender": a.gender,
        "source_type": a.source_type,
        "dob": a.dob,
        "estimated_age_months": a.estimated_age_months,
        "status": a.status,
        "health_status": a.health_status,
        "is_pregnant": a.is_pregnant,
        "is_lactating": a.is_lactating,
        "is_quarantine": a.is_quarantine,
        "is_active": a.is_active,
        "notes": a.notes,
        "mother": a.mother.tag_id if a.mother else None,
        "species": a.livestock_species.name if a.livestock_species else (a.species.name if a.species else None),
        "breed": a.livestock_breed.name if a.livestock_breed else (a.breed.name if a.breed else None),
        "housing_unit": a.housing_unit.name if a.housing_unit else (a.unit.name if a.unit else None),
        "livestock_species_id": a.livestock_species_id,
        "livestock_breed_id": a.livestock_breed_id,
        "housing_unit_id": a.housing_unit_id,
    }

    return 200, APIResponse(success=True, message="Animal details successfully", data=serialized)


@router.patch("/update-animal/v2/{animal_id}", response={200: APIResponse, 403: APIResponse})
def update_animal_v2(
    request,
    payload: AnimalsUpdateSchemaInV2,
    animal_id: int,
):
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
    animal = get_object_or_404(
        Animal.objects.select_related(
            "farm", "housing_unit", "livestock_species", "livestock_breed",
            "unit", "species", "breed",
        ),
        id=animal_id,
    )
    farm = animal.farm

    if payload.tag_id:
        if Animal.objects.filter(tag_id__iexact=payload.tag_id, farm=animal.farm).exclude(id=animal.id).exists():
            raise HttpError(409, "Tag ID already exists")
        animal.tag_id = payload.tag_id

    if payload.new_farm_id:
        farm = get_object_or_404(Farm, id=payload.new_farm_id)
        animal.farm = farm

    if payload.livestock_species_id:
        livestock_species = get_object_or_404(LivestockSpecies, id=payload.livestock_species_id, is_active=True)
        animal.livestock_species = livestock_species
        if payload.livestock_breed_id:
            livestock_breed = get_object_or_404(LivestockBreed, id=payload.livestock_breed_id, is_active=True)
            if livestock_breed.species_id != livestock_species.id:
                raise HttpError(422, f"Breed '{livestock_breed.name}' does not belong to species '{livestock_species.name}'")
            if livestock_breed.farm and livestock_breed.farm_id != farm.id:
                raise HttpError(422, "This breed is not available for your farm")
            animal.livestock_breed = livestock_breed
    elif payload.livestock_breed_id:
        livestock_breed = get_object_or_404(LivestockBreed, id=payload.livestock_breed_id, is_active=True)
        if livestock_breed.farm and livestock_breed.farm_id != farm.id:
            raise HttpError(422, "This breed is not available for your farm")
        animal.livestock_breed = livestock_breed

    if payload.housing_unit_id:
        housing_unit = get_object_or_404(FarmHousingUnit, id=payload.housing_unit_id, farm=farm, status="active")
        effective_species = animal.livestock_species
        if effective_species and housing_unit.allowed_species.exists() and not housing_unit.allowed_species.filter(id=effective_species.id).exists():
            raise HttpError(422, f"Housing unit '{housing_unit.name}' does not support species '{effective_species.name}'")
        animal.housing_unit = housing_unit

    if payload.mother_id:
        animal.mother = get_object_or_404(Animal, id=payload.mother_id, farm=farm)

    if payload.gender is not None:
        animal.gender = payload.gender

    if payload.source is not None:
        animal.source_type = payload.source

    if payload.dob is not None:
        animal.dob = payload.dob

    if payload.estimated_age_months is not None:
        animal.estimated_age_months = payload.estimated_age_months

    if payload.status is not None:
        animal.status = payload.status

    if payload.health_status is not None:
        animal.health_status = payload.health_status

    if payload.is_pregnant is not None:
        animal.is_pregnant = payload.is_pregnant

    if payload.is_lactating is not None:
        animal.is_lactating = payload.is_lactating

    if payload.is_quarantine is not None:
        animal.is_quarantine = payload.is_quarantine

    if payload.is_active is not None:
        animal.is_active = payload.is_active

    if payload.notes is not None:
        animal.notes = payload.notes

    try:
        animal.save()
    except ValidationError as e:
        return JsonResponse({"errors": e.message_dict}, status=400)

    return 200, APIResponse(
        success=True,
        message="Animal updated successfully",
        data={
            "id": animal.id,
            "tag_id": animal.tag_id,
            "gender": animal.gender,
            "species": animal.livestock_species.name if animal.livestock_species else (animal.species.name if animal.species else None),
            "breed": animal.livestock_breed.name if animal.livestock_breed else (animal.breed.name if animal.breed else None),
            "housing_unit": animal.housing_unit.name if animal.housing_unit else (animal.unit.name if animal.unit else None),
        },
    )


@router.get(
    "/animal-event/v2/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_animal_event_v2(request, page: int, page_size: int, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")

    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Animal.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")

    event = AnimalEvent.objects.select_related(
        "group", "event_type", "created_by",
        "animal", "animal__livestock_species", "animal__livestock_breed",
        "animal__species", "animal__breed",
    ).filter(farm_id=farm_id)

    paginator = Paginator(event, page_size)
    page_obj = paginator.page(page)

    serialized = []
    for data in page_obj.object_list:
        a = data.animal
        serialized.append({
            "id": data.id,
            "group": data.group.name if data.group else None,
            "animal_id": a.id if a else None,
            "tag": a.tag_id if a else None,
            "species": (
                (a.livestock_species.name if a.livestock_species else (a.species.name if a.species else None))
                if a else None
            ),
            "breed": (
                (a.livestock_breed.name if a.livestock_breed else (a.breed.name if a.breed else None))
                if a else None
            ),
            "livestock_species": a.livestock_species.name if a and a.livestock_species else None,
            "livestock_breed": a.livestock_breed.name if a and a.livestock_breed else None,
            "event_type": data.event_type.name,
            "event_title": data.event_title,
            "event_summary": data.event_summary,
            "reference_table": data.reference_table,
            "reference_id": data.reference_id,
            "created_at": data.created_at,
            "created_by": data.created_by.email,
        })

    return 200, ListResponseSchema(
        success=True,
        message="Animal events fetched successfully",
        data=serialized,
        num_pages=paginator.num_pages,
        current_page=page_obj.number,
        total_items=paginator.count,
        has_next=page_obj.has_next,
        has_previous=page_obj.has_previous,
    )


@router.get(
    "/animal-weight/v2/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_animal_weight_v2(request, page: int, page_size: int, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")

    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Animal.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")

    weight = AnimalWeight.objects.select_related(
        "animal", "animal__livestock_species", "animal__livestock_breed",
        "animal__species", "animal__breed",
    ).filter(farm_id=farm_id)

    paginator = Paginator(weight, page_size)
    page_obj = paginator.page(page)

    serialized = []
    for data in page_obj.object_list:
        a = data.animal
        serialized.append({
            "id": data.id,
            "animal_id": a.id,
            "tag": a.tag_id,
            "species": a.livestock_species.name if a.livestock_species else (a.species.name if a.species else None),
            "breed": a.livestock_breed.name if a.livestock_breed else (a.breed.name if a.breed else None),
            "livestock_species": a.livestock_species.name if a.livestock_species else None,
            "livestock_breed": a.livestock_breed.name if a.livestock_breed else None,
            "date": data.date,
            "weight": data.weight,
            "created_at": data.created_at,
        })

    return 200, ListResponseSchema(
        success=True,
        message="Animal weight fetched successfully",
        data=serialized,
        num_pages=paginator.num_pages,
        current_page=page_obj.number,
        total_items=paginator.count,
        has_next=page_obj.has_next,
        has_previous=page_obj.has_previous,
    )


@router.get(
    "/milk/v2/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
    tags=["Production"],
)
def get_milk_v2(request, page: int, page_size: int, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")

    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Production.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    milk = MilkRecord.objects.select_related(
        "animal", "animal__livestock_species", "animal__livestock_breed",
        "animal__species", "animal__breed", "created_by",
    ).filter(farm=farm)

    paginator = Paginator(milk, page_size)
    page_obj = paginator.page(page)

    serialized = []
    for data in page_obj.object_list:
        a = data.animal
        serialized.append({
            "id": data.id,
            "animal_id": a.id if a else None,
            "animal_tag": a.tag_id if a else None,
            "species": (
                (a.livestock_species.name if a.livestock_species else (a.species.name if a.species else None))
                if a else None
            ),
            "breed": (
                (a.livestock_breed.name if a.livestock_breed else (a.breed.name if a.breed else None))
                if a else None
            ),
            "livestock_species": a.livestock_species.name if a and a.livestock_species else None,
            "livestock_breed": a.livestock_breed.name if a and a.livestock_breed else None,
            "record_date": data.record_date,
            "session": data.session,
            "quantity": data.quantity,
            "created_at": data.created_at,
            "created_by": data.created_by.email,
        })

    return 200, ListResponseSchema(
        success=True,
        message="Milk records fetched successfully",
        data=serialized,
        num_pages=paginator.num_pages,
        current_page=page_obj.number,
        total_items=paginator.count,
        has_next=page_obj.has_next,
        has_previous=page_obj.has_previous,
    )


@router.get("/animal-growth/{animal_id}/", response={200: APIResponse, 403: APIResponse})
def get_animal_growth(request, animal_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    animal = get_object_or_404(Animal, id=animal_id, farm__organization=org)
    data = {
        "animal_id": animal.id,
        "weight_gain_kg": weight_gain(animal),
        "average_daily_gain_kg": average_daily_gain(animal),
        "percentage_weight_change": percentage_weight_change(animal),
        "cost_per_kg_gained": cost_per_kg_gained(animal),
        "weight_trend": weight_trend(animal),
    }
    return 200, APIResponse(success=True, message="Animal growth summary", data=data)
