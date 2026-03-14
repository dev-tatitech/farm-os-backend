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
import hmac
import hashlib
import json
import os
from django.db.models.functions import Round
from django.db.models import Value
from django.http import HttpResponse

import uuid
from .models import (
    SubscriptionPlan,
    Industry,
    Organization
)
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.http import JsonResponse
from .schema import (
    ListResponseSchema,
    APIResponse,
   
)
router = Router(tags=["Oganization module"])
@router.get(
    "/get-plan/",
    response={200: APIResponse, 403: APIResponse},
)
def get_plan(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    
    plans = SubscriptionPlan.objects.all()
    data = [
        {
         "id": plan.id,
         "name": plan.name  ,
         "monthly_price": plan.monthly_price  ,
         "annual_price": plan.annual_price  ,
         "max_users": plan.max_users  ,
         "max_farms": plan.max_farms  ,
         "max_batches": plan.max_batches  
          
        }
        for plan in plans
    ]
    return 200, APIResponse(
        success=True, message="subcription plans successfully", data=data
    )
