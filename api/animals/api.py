from ninja import Router, Query, Form
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
    AnimalProfileAttributeSchemaIn,
    AnimalGroupSchemaIn,
    AnimalGroupMemberSchemaIn,
    AnimalGroupUpdateSchema,
    AnimalGroupMemberFilterSchema,
    UpdateAnimalGroupMemberSchemaIn,
    AnimalsUpdateSchemaIn,
    AnimalWeightIn,
    MilkRecordSchema
)
router = Router(tags=["Animals"])
@router.post("/animal/", response={200: APIResponse, 403: APIResponse})
def new_animal(
    request,
    payload: AnimalsSchemaIn = Form(...),
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
        "gender": animal.gender
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
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Animal.VIEW)
        raise HttpError(404, f"you are not admin {perm}")
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
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Animal.VIEW)
        raise HttpError(404, f"you are not admin {perm}")
  
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


@router.get("/dashboard/{farm_id}", response={200: APIResponse, 403: APIResponse})
def animal_dashboard(request, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not user.organizations.first():
        perm = user_has_permission(user, Permissions.Animal.VIEW)
        raise HttpError(404, f"you are not admin {perm}")

    # lazy import to avoid cycles
    from .models import AnimalDashboard
    from .signals import recalc_dashboard_for_farm
    from health.models import VaccinationRecord, TreatmentRecord

    dashboard = AnimalDashboard.objects.filter(farm_id=farm_id).first()
    if not dashboard:
        # create and calculate on demand
        recalc_dashboard_for_farm(farm_id)
        dashboard = AnimalDashboard.objects.get(farm_id=farm_id)

    upcoming_records = VaccinationRecord.objects.select_related("animal", "group").filter(
        farm_id=farm_id,
        next_due_date__isnull=False,
        next_due_date__gte=timezone.localdate(),
    ).order_by("next_due_date")[:5]

    vaccination_upcoming_records = [
        {
            "id": record.id,
            "animal_id": record.animal.id if record.animal else None,
            "animal_tag": record.animal.tag_id if record.animal else None,
            "group_id": record.group.id if record.group else None,
            "group_name": record.group.name if record.group else None,
            "vaccine_name": record.vaccine_name,
            "date_given": record.date_given,
            "next_due_date": record.next_due_date,
            "notes": record.notes,
        }
        for record in upcoming_records
    ]

    # Treatment follow-ups
    treatment_followups_qs = TreatmentRecord.objects.select_related("animal", "group").filter(
        farm_id=farm_id,
        next_follow_up_date__isnull=False,
    ).order_by("-next_follow_up_date")[:3]

    treatment_followups = [
        {
            "id": record.id,
            "animal_id": record.animal.id if record.animal else None,
            "animal_tag": record.animal.tag_id if record.animal else None,
            "group_id": record.group.id if record.group else None,
            "group_name": record.group.name if record.group else None,
            "diagnosis": record.diagnosis,
            "treatment": record.treatment,
            "severity": record.severity,
            "treatment_date": record.treatment_date,
            "next_follow_up_date": record.next_follow_up_date,
            "notes": record.notes,
        }
        for record in treatment_followups_qs
    ]

    # Species distribution
    from django.db.models import Count
    species_dist = Animal.objects.filter(
        farm_id=farm_id
    ).values('species__id', 'species__name').annotate(count=Count('id')).order_by('-count')

    species_distribution = [
        {
            "species_id": item['species__id'],
            "species_name": item['species__name'],
            "count": item['count'],
        }
        for item in species_dist
    ]

    data = {
        "total": dashboard.total_animals,
        "active": dashboard.active,
        "healthy": dashboard.healthy,
        "lactating": dashboard.lactating,
        "pregnant": dashboard.pregnant,
        "sick": dashboard.sick,
        "quarantine": dashboard.quarantine,
        "deaths": dashboard.deaths,
        "sales": dashboard.sales,
        "species_distribution": species_distribution,
        "treatment_followups": treatment_followups,
        "vaccination_upcoming_records": vaccination_upcoming_records,
        "updated_at": dashboard.updated_at,
    }
    return 200, APIResponse(success=True, message="Animal dashboard", data=data)

@router.patch("/animal/{animal_id}", response={200: APIResponse, 403: APIResponse},)
def update_animal(
    request,
    payload:AnimalsUpdateSchemaIn,
    animal_id: int
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
    animal = get_object_or_404(Animal.objects.select_related("farm", "unit"), id = animal_id)
    if payload.tag_id:
        if Animal.objects.filter(
            tag_id__iexact=payload.tag_id,
            farm=animal.farm
        ).exclude(id=animal.id).exists():
            raise HttpError(409, "tag ID already exists")
        animal.tag_id = payload.tag_id

    if payload.farm_id:
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
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Reproduction.VIEW)
        raise HttpError(404, f"you are not admin {perm}")
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
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Animal.CREATE)
        raise HttpError(404, f"you are not admin {perm}")
    
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
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Reproduction.VIEW)
        raise HttpError(404, f"you are not admin {perm}")
    weight = AnimalWeight.objects.select_related("animal").filter(farm_id = farm_id)
    paginator = Paginator(weight, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
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
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Health.CREATE)
        raise HttpError(404, f"you are not admin {perm}")
    
    farm = get_object_or_404(Farm, id =payload.farm_id)
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
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.Health.VIEW)
        raise HttpError(404, f"you are not admin {perm}")
    milk = MilkRecord.objects.select_related("animal__species", "created_by").filter(farm_id = farm_id)
    paginator = Paginator(milk, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
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
    if not user.organizations.first():
        raise HttpError(403, "Permission denied")

    from reproduction.models import InseminationRecord, PregnancyRecord
    from health.models import VaccinationRecord, TreatmentRecord
    from feed.models import FeedIssuanceRecord, FeedPlan
    from movement_records.models import MovementRecord

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
    