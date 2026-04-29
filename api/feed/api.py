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
from animals.models import Animal, AnimalWeight, AnimalGroup
from django.db import IntegrityError
import uuid
from admin_panel.models import UnitType, Species, Breed
from subcriptions.models import SubscriptionPlan, Subscription
from common.utils import generate_ref
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.http import JsonResponse
from .models import (
    FeedInventory,
    FeedPlan
    )
from core.models import GroupType
from django.core.exceptions import ValidationError
from .schema import (
    ListResponseSchema,
    APIResponse,
    FeedInventorySchema,
    FeedPlanSchema,
    
)
from animals.event import new_event
router = Router(tags=["Feed"])

@router.post("/mortality/", response={200: APIResponse, 403: APIResponse},)
def mortality(
    request,
    payload:FeedInventorySchema
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
    feed_data = {
    "farm": farm,
    "feed_name": payload.feed_name,
    "quantity_available": payload.quantity_available,
    "unit": payload.unit,
    "reorder_level": payload.reorder_level
    }
    feed = FeedInventory(
        **feed_data
    )
    try:
        feed.full_clean()
        feed.save()
    except ValidationError as e:
        return JsonResponse({
        "errors": e.message_dict
        }, status=400)
    data={
        "feed_name":feed.feed_name,
        "quantity_available": feed.quantity_available
    }
    return 200,APIResponse(
        success=True,
        message="Feed create successfully",
        data=data
    )

@router.get(
    "/feed/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_feed(
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
    fi = FeedInventory.objects.filter(farm_id = farm_id)
    paginator = Paginator(fi, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "feed_name": data.feed_name,
                "quantity_available": data.quantity_available,
                "unit": data.unit,
                "reorder_level": data.reorder_level,
                "status": data.status,
                "last_restocked_at": data.last_restocked_at,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
             
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"feed fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )
    
@router.post("/feed-plan/", response={200: APIResponse, 403: APIResponse},)
def feed_plan(
    request,
    payload:FeedPlanSchema
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
    feed_inventory = get_object_or_404(FeedInventory, id =payload.feed_inventory_id)
    feed_data = {
    "farm": farm,
    "plan_type": payload.plan_type,
    "feed_inventory":feed_inventory,
    "daily_feed_quantity": payload.daily_feed_quantity,
    "unit": payload.unit,
    "start_date": payload.start_date,
    "created_by": user
    }
    if payload.species_id:
        species = get_object_or_404(Species, id = payload.species_id)
        feed_data["species"] = species
    if payload.group_id:
        group = get_object_or_404(AnimalGroup, id = payload.group_id)
        feed_data["group"] = group
    if payload.end_date:
        feed_data["end_date"] = payload.end_date
    if payload.notes:
        feed_data["notes"] = payload.notes
    feed = FeedPlan(
        **feed_data
    )
    try:
        feed.full_clean()
        feed.save()
    except ValidationError as e:
        return JsonResponse({
        "errors": e.message_dict
        }, status=400)
    data={
        "daily_feed_quantity":feed.daily_feed_quantity,
        "unit": feed.unit
    }
    return 200,APIResponse(
        success=True,
        message="Feed create successfully",
        data=data
    )


@router.get(
    "/feed-plan/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_feed_plan(
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
    fp = FeedPlan.objects.filter(farm_id = farm_id)
    paginator = Paginator(fp, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "plan_type": data.plan_type,
                "species": data.species.name if data.species else None,
                "unit": data.unit,
                "group": data.group.name if data.group else None,
                "feed_inventory": data.feed_inventory.feed_name,
                "daily_feed_quantity": data.daily_feed_quantity,
                "start_date": data.start_date,
                "end_date": data.end_date,
                "notes": data.notes,
                "created_by": data.created_by.email,
                "status": data.status,
                "created_at": data.created_at,
        
             
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"feed plan fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )
    