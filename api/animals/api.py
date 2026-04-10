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
import uuid
from admin_panel.models import UnitType, Species, Breed
from subcriptions.models import SubscriptionPlan, Subscription
from common.utils import generate_ref
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.http import JsonResponse
from .models import Animal
from django.core.exceptions import ValidationError
from .schema import (
    ListResponseSchema,
    APIResponse,
    AnimalsSchemaIn
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
        perm = user_has_permission(user,Permissions.FarmUnit.CREATE)
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
        perm = user_has_permission(user,Permissions.FarmUnit.VIEW)
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
