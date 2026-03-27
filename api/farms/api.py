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
from organization.models import (
    Farm,
    Organization
)
from common.permission_checker import user_has_permission
from common.permissions import Permissions
from admin_panel.models import UnitType
import uuid
from .models import (
    FarmUnit,
)
from subcriptions.models import SubscriptionPlan, Subscription
from common.utils import generate_ref
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.http import JsonResponse
from .schema import (
    ListResponseSchema,
    APIResponse,
    FarmSchemaIn
)
router = Router(tags=["Farm"])
@router.post(
    "/farm-unit/",
    response={200: APIResponse, 403: APIResponse},
)
def add_farm_unit(request, payload: FarmSchemaIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not user.organizations.first():
        perm = user_has_permission(user,Permissions.FarmUnit.CREATE)
        raise HttpError(404, f"you are not admin {perm}")
    raise HttpError(400, f"i am the owner of {org.name}")   
    org = get_object_or_404(Organization, id = payload.org_id)
    farm = get_object_or_404(Farm, id= payload.farm_id)
    unit_type = get_object_or_404(UnitType, id = payload.unit_type_id)
    if FarmUnit.objects.filter(name__iexact=payload.name).exists():
        raise HttpError(409, "farm unit already exists") 
    code = f"FU-{generate_ref()}" 
    farm_unit = FarmUnit.objects.create(
        organization = org,
        farm = farm,
        name = payload.name,
        code = code,
        unit_type = unit_type,
        capacity = payload.capacity
    )
    return 200, APIResponse(success=True, message=f"farm Unit added success", data=None)
