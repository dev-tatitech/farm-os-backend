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
    AdminLevel1,
    AdminLevel2,
)
import uuid
from .models import (
    Industry,
    Organization,
    FarmType,
    Farm
)
from role.models import Role, UserRole
from subcriptions.models import SubscriptionPlan, Subscription
from common.utils import generate_ref
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.http import JsonResponse
from .schema import (
    ListResponseSchema,
    APIResponse,
   OranizationSchemaIn,
   FarmInSchema
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
    
    plans = Industry.objects.all()
    data = [
        {
         "id": plan.id,
         "code": plan.short_nme  ,
         "name": plan.name  ,   
        }
        for plan in plans
    ]
    return 200, APIResponse(
        success=True, message="industries successfully", data=data
    )

@router.get(
    "/get-countries/",
    response={200: APIResponse, 403: APIResponse},
)
def get_counttries(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    
    plans = Country.objects.all()
    data = [
        {
         "id": plan.id,
         "name": plan.name  ,   
        }
        for plan in plans
    ]
    return 200, APIResponse(
        success=True, message="countries successfully", data=data
    )

@router.get(
    "/get-stateregion/{country_id}",
    response={200: APIResponse, 403: APIResponse},
)
def get_state(request, country_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    country = get_object_or_404(Country, id =country_id)
    plans = AdminLevel1.objects.filter(country =country)
    data = [
        {
         "id": plan.id,
         "name": plan.name,
         "timezone": plan.timezone   
        }
        for plan in plans
    ]
    return 200, APIResponse(
        success=True, message="stateregion successfully", data=data
    )

@router.get(
    "/get-lga/{state_region_id}",
    response={200: APIResponse, 403: APIResponse},
)
def get_lga(request, state_region_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    state = get_object_or_404(AdminLevel1, id=state_region_id)
    rows = AdminLevel2.objects.filter(admin_level1=state).order_by("name")
    data = [{"id": row.id, "name": row.name} for row in rows]
    return 200, APIResponse(success=True, message="lga fetched successfully", data=data)

@router.post(
    "/organization/",
    response={200: APIResponse, 403: APIResponse},
)
def organiation(request, payload: OranizationSchemaIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    if Organization.objects.filter(user=user).exists():
        raise HttpError(409, "User already has an organization.")
    
    industry = get_object_or_404(Industry, id = payload.industry_id)
    country = get_object_or_404(Country, id = payload.country_id)
    state = get_object_or_404(AdminLevel1, id = payload.state_region_id)
    org = f"ORG-{generate_ref()}"
    with db_transaction.atomic():
        plan, created = SubscriptionPlan.objects.get_or_create(
                name="Trial Plan",
            )
        plan.code =f"Plan-{generate_ref()}"
        plan.monthly_price = 0
        plan.annual_price = 0
        plan.max_users = 2
        plan.max_farms = 1
        plan.max_batches = 1
        plan.save()
        organization = Organization.objects.create(
            user = user,
            name = payload.name,
            code = org,
            industry_type = industry,
            country = country,
            state_region = state,
        )
        sub = Subscription.objects.create(
            plan = plan,
            organization = organization,
            billing_cycle = "monthly",
            price = 0,
        )
        sub.end_date = sub.start_date + relativedelta(months=1)
        sub.save()
        
    return 200, APIResponse(
        success=True, message="organization create successfully", data=None
    )
    
@router.get(
    "/oganization/",
    response={200: APIResponse, 403: APIResponse},
)
def get_organization(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    #org = get_object_or_404(Organization, user =user)
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, f"Permission denied")
    request_host = request.build_absolute_uri("/").rstrip("/")
    data = {
         "id": org.id,
         "name": org.name,
         "code": org.code,
         "industry_type": org.industry_type.name if org.industry_type else None,
         "country": org.country.name if org.country else None,
         "state_region": org.state_region.name if org.state_region else None,
         "status": org.status,
         "logo_url": f"{request_host}{org.logo.url}" if org.logo else None,
        }


    return 200, APIResponse(
        success=True, message="oranization fetch successfully", data=data
    )


@router.post(
    "/organization/logo/",
    response={200: APIResponse, 403: APIResponse},
)
def update_organization_logo(
    request,
    logo: UploadedFile = File(...),
):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    if org.logo:
        try:
            org.logo.delete(save=False)
        except Exception:
            pass

    org.logo = logo
    org.save(update_fields=["logo"])

    request_host = request.build_absolute_uri("/").rstrip("/")
    return 200, APIResponse(
        success=True,
        message="Organization logo updated successfully",
        data={"id": org.id, "logo_url": f"{request_host}{org.logo.url}"},
    )
    
@router.get(
    "/farm-type/",
    response={200: APIResponse, 403: APIResponse},
)
def farm_type(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    
    farm_type = FarmType.objects.all()
    data = [
        {
         "id": f_type.id,
         "name": f_type.name  ,   
         "code": f_type.code  ,   
        }
        for f_type in farm_type
    ]
    return 200, APIResponse(
        success=True, message="farm type successfully", data=data
    )
    
@router.post(
    "/farm/",
    response={200: APIResponse, 403: APIResponse},
)
def farm(request, payload: FarmInSchema):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    if Farm.objects.filter(name__iexact=payload.name).exists():
        raise HttpError(409, "Farm already exists") 
    org = get_object_or_404(Organization, id = payload.organization_id)
    country = get_object_or_404(Country, id = payload.country_id)
    state = get_object_or_404(AdminLevel1, id = payload.state_region_id)
    farm_type = get_object_or_404(FarmType, id = payload.farm_type_id)
    
    farm_code= f"FRM-{generate_ref()}"
    farm = Farm.objects.create(
        organization = org,
        name = payload.name,
        farm_code= farm_code,
        country = country,
        state_region = state,
        city = payload.city,
        location_address = payload.location_address,
        latitude = payload.latitude,
        longitude = payload.longitude,
        farm_type = farm_type,
        is_primary = payload.is_primary
    )
    data = {
        "name": farm.name,
        "city": farm.city,
        "location_address":farm.location_address
    }
    return 200, APIResponse(
        success=True, message="farm created successfully", data=data
    )
    
@router.get(
    "/farm/",
    response={200: APIResponse, 403: APIResponse},
)
def get_farm(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization
    farms = Farm.objects.filter(
    userrole__user=user
    ).distinct()
    if not org:
        org = user.organizations.first()
        farms = Farm.objects.filter(organization=org)
    if not org:
        raise HttpError(404, f"Permission denied")
    
    data = [
        {
            "id": farm.id,
            "name": farm.name,
            "farm_code": farm.farm_code,
            "country": farm.country.name if farm.country else None,
            "state_region": farm.state_region.name if farm.state_region else None,
            "farm_type": farm.farm_type.name if farm.farm_type else None,
            "city": farm.city,
            "location_address": farm.location_address,
            "latitude": farm.latitude,
            "longitude": farm.longitude,
            "is_primary": farm.is_primary,
            "status": farm.status,
            
        }
        for farm in farms
    ]
    return 200, APIResponse(
        success=True, message="farm fetch successfully", data=data
    )


@router.get(
    "/organization/dashboard/",
    response={200: APIResponse, 403: APIResponse},
)
def organization_dashboard(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related(
            "organization__industry_type", "organization__country", "organization__state_region"
        ).get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    org =  user.organizations.select_related(
        "industry_type", "country", "state_region"
    ).first()
    if not org:
        raise HttpError(403, "Permission denied")

    farms = Farm.objects.filter(organization=org).select_related("farm_type", "country", "state_region")

    all_users = users.objects.filter(
        Q(organization=org) | Q(id=org.user_id)
    ).distinct().prefetch_related("user_roles__role", "user_roles__farm")

    roles = Role.objects.filter(organization=org).annotate(user_count=Count("userrole", distinct=True))

    subscription = Subscription.objects.select_related("plan").filter(organization=org).order_by("-start_date").first()

    farm_type_counts = (
        farms.values("farm_type__id", "farm_type__name", "farm_type__code")
        .annotate(farm_count=Count("id"))
        .order_by("-farm_count")
    )

    farms_data = [
        {
            "id": f.id,
            "name": f.name,
            "farm_code": f.farm_code,
            "farm_type": f.farm_type.name if f.farm_type else None,
            "farm_type_id": f.farm_type_id,
            "country": f.country.name if f.country else None,
            "state_region": f.state_region.name if f.state_region else None,
            "city": f.city,
            "is_primary": f.is_primary,
            "status": f.status,
            "created_at": f.created_at,
        }
        for f in farms
    ]

    users_data = []
    for u in all_users:
        assignments = [
            {
                "role": ur.role.name,
                "farm": ur.farm.name if ur.farm else None,
                "farm_id": ur.farm_id,
            }
            for ur in u.user_roles.all()
        ]
        users_data.append({
            "id": u.id,
            "email": u.email,
            "username": u.username,
            "account_status": u.account_status,
            "is_owner": u.id == org.user_id,
            "assignments": assignments,
        })

    roles_data = [
        {
            "id": r.id,
            "name": r.name,
            "code": r.code,
            "description": r.description,
            "user_count": r.user_count,
        }
        for r in roles
    ]

    farm_types_data = [
        {
            "id": row["farm_type__id"],
            "name": row["farm_type__name"],
            "code": row["farm_type__code"],
            "farm_count": row["farm_count"],
        }
        for row in farm_type_counts
        if row["farm_type__id"] is not None
    ]

    subscription_data = None
    if subscription:
        subscription_data = {
            "plan": subscription.plan.name,
            "billing_cycle": subscription.billing_cycle,
            "price": subscription.price,
            "status": subscription.status,
            "start_date": subscription.start_date,
            "end_date": subscription.end_date,
            "auto_renew": subscription.auto_renew,
            "max_users": subscription.plan.max_users,
            "max_farms": subscription.plan.max_farms,
            "max_batches": subscription.plan.max_batches,
        }

    request_host = request.build_absolute_uri("/").rstrip("/")
    data = {
        "organization": {
            "id": org.id,
            "name": org.name,
            "code": org.code,
            "industry_type": org.industry_type.name if org.industry_type else None,
            "country": org.country.name if org.country else None,
            "state_region": org.state_region.name if org.state_region else None,
            "status": org.status,
            "logo_url": f"{request_host}{org.logo.url}" if org.logo else None,
            "created_at": org.created_at,
        },
        "subscription": subscription_data,
        "summary": {
            "total_farms": len(farms_data),
            "active_farms": sum(1 for f in farms_data if f["status"] == "active"),
            "total_users": len(users_data),
            "active_users": sum(1 for u in users_data if u["account_status"] not in ("inactive", "Deleted")),
            "total_roles": len(roles_data),
        },
        "farms": farms_data,
        "farm_types": farm_types_data,
        "users": users_data,
        "roles": roles_data,
    }

    return 200, APIResponse(
        success=True, message="organization dashboard fetch successfully", data=data
    )

