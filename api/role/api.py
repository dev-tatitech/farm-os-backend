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
    RolePermission,
    Role,
    UserRole,
    Permission
)
from organization.models import Organization, Farm
from common.utils import generate_ref
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.http import JsonResponse
from .schema import (
    APIResponse,
    RoleIn
)
router = Router(tags=["User and Role management"])
@router.get(
    "/get-industry/",
    response={200: APIResponse, 403: APIResponse},
)
def get_industry(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    
    plans = Permission.objects.all()
    data = [
        {
         "id": plan.id,
         "code": plan.code  ,
         "name": plan.name  ,   
         "module": plan.module  ,
          "description": plan.description  ,   
        }
        for plan in plans
    ]
    return 200, APIResponse(
        success=True, message="permission fetch successfully", data=data
    )

@router.post(
    "/role/",
    response={200: APIResponse, 403: APIResponse},
)
def role(request, payload: RoleIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
 
    org = get_object_or_404(Organization, user = user)
    if Role.objects.filter(name__iexact=payload.name,organization = org ).exists():
        raise HttpError(409, "Role already exists") 
    code = f"RL-{generate_ref()}"
    role = Role.objects.create(
        organization = org,
        name = payload.name,
        code = code,
        description =  payload.description
    )
    data = {
     "id": role.id,
     "nae": role.name   
    }
    return 200, APIResponse(
        success=True, message="Role created successfully", data=data
    )