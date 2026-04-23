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
from admin_panel.models import UnitType
from subcriptions.models import SubscriptionPlan, Subscription
from common.utils import generate_ref
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.http import JsonResponse
from .models import GroupType, EventType
from .schema import (
    ListResponseSchema,
    APIResponse,
    GroupTypeSchmaIn,
    EventTypeSchemaIn
)
router = Router(tags=["Global"])
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
    
@router.post(
    "/group-type/",
    response={200: APIResponse, 403: APIResponse},
)
def addgroup_type(request, payload: GroupTypeSchmaIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    org = user.organizations
    if not org:
        raise HttpError(403, "must have an organizations")
    if GroupType.objects.filter( name = payload.name).exists():
        raise HttpError(400, "name is already exist")
    group = GroupType.objects.create(
        user = user,
        name = payload.name
    )
    data = {
        "id":group.id,
        "name": group.name
    }
    return 200,APIResponse(
        success=True,
        message="group type create successfully",
        data=data
    )
    
@router.get("/group-type/{page}/{page_size}", response={200: APIResponse, 403: APIResponse},)
def get_group_type(
    request,  
    page: int,
    page_size: int,
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    
  
    group_type = GroupType.objects.all()
    paginator = Paginator(group_type, page_size)
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
        message=f"group type fetch successfully",
        data=serialized,
        num_pages=paginator.num_pages,
        current_page=page_obj.number,
        total_items=paginator.count,
        has_next=page_obj.has_next,
        has_previous=page_obj.has_previous,
    )
    
@router.post(
    "/event-type/",
    response={200: APIResponse, 403: APIResponse},
)
def event_type(request, payload: GroupTypeSchmaIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    org = user.organizations
    if not org:
        raise HttpError(403, "must have an organizations")
    if EventType.objects.filter( name = payload.name).exists():
        raise HttpError(400, "name is already exist")
    event_type = EventType.objects.create(
        user = user,
        name = payload.name
    )
    data = {
        "id":event_type.id,
        "name": event_type.name
    }
    return 200,APIResponse(
        success=True,
        message="event type create successfully",
        data=data
    )
    
@router.get("/event-type/{page}/{page_size}", response={200: APIResponse, 403: APIResponse},)
def get_event_type(
    request,  
    page: int,
    page_size: int,
    ):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    
  
    event_type = EventType.objects.all()
    paginator = Paginator(event_type, page_size)
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
        message=f"event type fetch successfully",
        data=serialized,
        num_pages=paginator.num_pages,
        current_page=page_obj.number,
        total_items=paginator.count,
        has_next=page_obj.has_next,
        has_previous=page_obj.has_previous,
    )
    