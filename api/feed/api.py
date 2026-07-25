from ninja import Router, Query
from typing import Optional
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
from admin_panel.models import UnitType, Species, Breed, LivestockSpecies
from subcriptions.models import SubscriptionPlan, Subscription
from common.utils import generate_ref
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.http import JsonResponse
from .models import (
    FeedInventory,
    FeedPlan,
    FeedIssuanceRecord,
    FeedConfirmationRecord,
    FeedCategory,
    FeedUnit,
    FeedType,
    FeedBatch,
    )
from core.models import GroupType
from django.core.exceptions import ValidationError
from .schema import (
    ListResponseSchema,
    APIResponse,
    FeedInventorySchema,
    FeedPlanSchema,
    FeedPlanSchemaV2,
    FeedIssuanceRecordSchema,
    FeedConfirmationRecordSchema,
    FeedUnitSchemaIn,
    FeedTypeSchemaIn,
    FeedTypeUpdateSchemaIn,
    FeedInventorySchemaV3,
    FeedBatchSchemaIn,
)
from animals.event import new_event
router = Router(tags=["Feed"])

@router.post("/feed-inventory/", response={200: APIResponse, 403: APIResponse},)
def feed_inventory(
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
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Feed.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")

    farm = get_object_or_404(Farm, id =payload.farm_id, organization = org)
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
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Feed.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    fi = FeedInventory.objects.filter(farm=farm)
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
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Feed.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id =payload.farm_id, organization = org)
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
        group = get_object_or_404(AnimalGroup, id = payload.group_id, farm=farm)
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
    if not org:
        raise HttpError(404, f"Permission denied")
    perm = user_has_permission(user,Permissions.Feed.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    fp = FeedPlan.objects.filter(farm=farm)
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

@router.post("/feed-issue/", response={200: APIResponse, 403: APIResponse},)
def feed_issue(
    request,
    payload:FeedIssuanceRecordSchema
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
    perm = user_has_permission(user,Permissions.Feed.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id =payload.farm_id, organization = org)
    feed_inventory = get_object_or_404(FeedInventory, id =payload.feed_inventory_id)
    feed_data = {
    "farm": farm,
    "target_type": payload.target_type,
    "feed_inventory":feed_inventory,
    "quantity_issued": payload.quantity_issued,
    "issue_date": payload.issue_date,
    "issued_by": user
    }
    if payload.animal_id:
        animal = get_object_or_404(Animal, id = payload.animal_id, farm = farm)
        feed_data["animal"] = animal
    if payload.group_id:
        group = get_object_or_404(AnimalGroup, id = payload.group_id, farm=farm)
        feed_data["group"] = group

    if payload.notes:
        feed_data["notes"] = payload.notes
    if payload.feed_batch_id:
        feed_data["feed_batch"] = get_object_or_404(FeedBatch, id=payload.feed_batch_id, farm=farm)
    if payload.feeding_period:
        feed_data["feeding_period"] = payload.feeding_period
    if payload.fed_by_id:
        feed_data["fed_by"] = get_object_or_404(users, id=payload.fed_by_id)
    if payload.allocation_method:
        feed_data["allocation_method"] = payload.allocation_method

    feed = FeedIssuanceRecord(
        **feed_data
    )
    if payload.manual_allocations:
        feed._manual_allocations = [e.dict() for e in payload.manual_allocations]
    try:
        feed.full_clean()
        feed.save()
    except ValidationError as e:
        if hasattr(e, "message_dict"):
            return JsonResponse({
            "errors": e.message_dict
            }, status=400)
        else:
            return JsonResponse({
            "errors": e.messages
            }, status=400)

    new_event(
    feed.farm,
    feed.animal,
    "feeding",
    feed.issue_date,
    f"Feed Issued - {feed.quantity_issued}",
    feed.notes,
    "feed_issuance_record",
    feed.id,
    feed.issued_by,
    group=feed.group
)
    data={
        "target_type":feed.target_type,
        "quantity_issued": feed.quantity_issued,
        "cost": feed.cost,
    }
    return 200,APIResponse(
        success=True,
        message="Feed issue create successfully",
        data=data
    )

@router.get(
    "/feed-issue/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_feed_issue(
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
    perm = user_has_permission(user,Permissions.Feed.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    fp = FeedIssuanceRecord.objects.filter(farm=farm)
    paginator = Paginator(fp, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "target_type": data.target_type,
                "animal": (
                    (data.animal.livestock_species.name if data.animal.livestock_species else (data.animal.species.name if data.animal.species else None))
                    if data.animal else None
                ),
                "quantity_issued": data.quantity_issued,
                "group": data.group.name if data.group else None,
                "feed_inventory": data.feed_inventory.feed_name,
                "issue_date": data.issue_date,
                "notes": data.notes,
                "issued_by": data.issued_by.email,
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

@router.post("/feed-confirmation/", response={200: APIResponse, 403: APIResponse},)
def feed_confirmation(
    request,
    payload:FeedConfirmationRecordSchema
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
    perm = user_has_permission(user,Permissions.Feed.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")

    farm = get_object_or_404(Farm, id =payload.farm_id, organization = org)
    feed_issue = get_object_or_404(FeedIssuanceRecord, id =payload.issuance_id)
    feed_data = {
    "farm": farm,
    "actual_used_quantity": payload.actual_used_quantity,
    "issuance":feed_issue,
    "confirmation_date": payload.confirmation_date,
    "confirmed_by": user,
    "status": payload.status
    }
    if payload.notes:
        feed_data["notes"] = payload.notes
    feed = FeedConfirmationRecord(
        **feed_data
    )
    try:
        feed.full_clean()
        feed.save()
    except ValidationError as e:
        if hasattr(e, "message_dict"):
            return JsonResponse({
            "errors": e.message_dict
            }, status=400)
        else:
            return JsonResponse({
            "errors": e.messages
            }, status=400)

    new_event(
    feed.farm,
    feed.issuance.animal,
    "feeding",
    feed.confirmation_date,
    "Feed Confirmation",
    f"Used: {feed.actual_used_quantity}, Variance: {feed.variance_quantity}",
    "feed_confirmation_record",
    feed.id,
    feed.confirmed_by,
    group=feed.issuance.group
)
    data={
        "actual_used_quantity":feed.actual_used_quantity,
        "confirmation_date": feed.confirmation_date
    }
    return 200,APIResponse(
        success=True,
        message="Confirm create successfully",
        data=data
    )

@router.get(
    "/feed-confirmation/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_feed_confirmatione(
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
    perm = user_has_permission(user,Permissions.Feed.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    fp = FeedConfirmationRecord.objects.select_related("issuance__feed_inventory").filter(farm=farm)
    paginator = Paginator(fp, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "feed_name": data.issuance.feed_inventory.feed_name,
                "quantity_issued": data.issuance.quantity_issued,
                "target_type": data.issuance.target_type,
                "actual_used_quantity": data.actual_used_quantity,
                "confirmation_date": data.confirmation_date,
                "variance_quantity": data.variance_quantity,
                "status": data.status,
                "confirmed_by": data.confirmed_by.email,
                "created_at": data.created_at,


            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"feed confirm fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )


# ---------------------------------------------------------------------------
# v2 endpoints
# ---------------------------------------------------------------------------

@router.post("/feed-plan/v2/", response={200: APIResponse, 403: APIResponse})
def feed_plan_v2(request, payload: FeedPlanSchemaV2):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Feed.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, "Permission denied")
    farm = get_object_or_404(Farm, id=payload.farm_id, organization=org)
    feed_inventory = get_object_or_404(FeedInventory, id=payload.feed_inventory_id)
    feed_data = {
        "farm": farm,
        "plan_type": payload.plan_type,
        "feed_inventory": feed_inventory,
        "daily_feed_quantity": payload.daily_feed_quantity,
        "unit": payload.unit,
        "start_date": payload.start_date,
        "created_by": user,
    }
    if payload.species_id:
        species = get_object_or_404(Species, id=payload.species_id)
        feed_data["species"] = species
    if payload.livestock_species_id:
        livestock_species = get_object_or_404(LivestockSpecies, id=payload.livestock_species_id)
        feed_data["livestock_species"] = livestock_species
    if payload.group_id:
        group = get_object_or_404(AnimalGroup, id=payload.group_id, farm=farm)
        feed_data["group"] = group
    if payload.end_date:
        feed_data["end_date"] = payload.end_date
    if payload.notes:
        feed_data["notes"] = payload.notes
    feed = FeedPlan(**feed_data)
    try:
        feed.full_clean()
        feed.save()
    except ValidationError as e:
        return JsonResponse({"errors": e.message_dict}, status=400)
    data = {
        "daily_feed_quantity": feed.daily_feed_quantity,
        "unit": feed.unit,
    }
    return 200, APIResponse(success=True, message="Feed plan created successfully", data=data)


@router.get(
    "/feed-plan/v2/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_feed_plan_v2(request, page: int, page_size: int, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Feed.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, "Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    fp = FeedPlan.objects.select_related(
        "livestock_species", "species", "group", "feed_inventory", "created_by"
    ).filter(farm=farm)
    paginator = Paginator(fp, page_size)
    page_obj = paginator.page(page)
    serialized = []
    for p in page_obj.object_list:
        serialized.append(
            {
                "id": p.id,
                "plan_type": p.plan_type,
                "livestock_species": (
                    p.livestock_species.name if p.livestock_species
                    else (p.species.name if p.species else None)
                ),
                "unit": p.unit,
                "group": p.group.name if p.group else None,
                "feed_inventory": p.feed_inventory.feed_name,
                "daily_feed_quantity": p.daily_feed_quantity,
                "start_date": p.start_date,
                "end_date": p.end_date,
                "notes": p.notes,
                "created_by": p.created_by.email,
                "status": p.status,
                "created_at": p.created_at,
            }
        )
    return 200, ListResponseSchema(
        success=True,
        message="feed plan fetch successfully",
        data=serialized,
        num_pages=paginator.num_pages,
        current_page=page_obj.number,
        total_items=paginator.count,
        has_next=page_obj.has_next,
        has_previous=page_obj.has_previous,
    )


@router.get(
    "/feed-issue/v2/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_feed_issue_v2(request, page: int, page_size: int, farm_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization
    if not org:
        org = user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Feed.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, "Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    fp = FeedIssuanceRecord.objects.select_related(
        "animal__livestock_species",
        "animal__livestock_breed",
        "animal__classification",
        "animal__species",
        "animal__breed",
        "group",
        "feed_inventory",
        "issued_by",
    ).filter(farm=farm)
    paginator = Paginator(fp, page_size)
    page_obj = paginator.page(page)
    serialized = []
    for r in page_obj.object_list:
        animal = r.animal
        if animal:
            animal_data = {
                "id": animal.id,
                "tag_id": getattr(animal, "tag_id", None),
                "species": (
                    animal.livestock_species.name if animal.livestock_species
                    else (animal.species.name if animal.species else None)
                ),
                "breed": (
                    animal.livestock_breed.name if animal.livestock_breed
                    else (animal.breed.name if animal.breed else None)
                ),
                "classification": animal.classification.name if animal.classification else None,
            }
        else:
            animal_data = None
        serialized.append(
            {
                "id": r.id,
                "target_type": r.target_type,
                "animal": animal_data,
                "quantity_issued": r.quantity_issued,
                "group": r.group.name if r.group else None,
                "feed_inventory": r.feed_inventory.feed_name,
                "issue_date": r.issue_date,
                "notes": r.notes,
                "issued_by": r.issued_by.email,
                "created_at": r.created_at,
            }
        )
    return 200, ListResponseSchema(
        success=True,
        message="feed issue fetch successfully",
        data=serialized,
        num_pages=paginator.num_pages,
        current_page=page_obj.number,
        total_items=paginator.count,
        has_next=page_obj.has_next,
        has_previous=page_obj.has_previous,
    )


# ---------------------------------------------------------------------------
# v3 endpoints — Feed Master Data Framework
# ---------------------------------------------------------------------------
# Species-based feed library. Feed names that repeat across species (e.g. Hay,
# Mineral Supplement) are stored as a single FeedType record and linked to
# every compatible species via the M2M field, per the shared-feed-type rule.

_FEED_CATEGORY_NAMES = [
    "Forage",
    "Concentrate",
    "Supplement",
    "Mineral",
    "Roughage",
    "By-products",
]

_FEED_UNIT_SEED = [
    ("Kilogram", "kg"),
    ("Gram", "g"),
    ("Ton", "t"),
    ("Bag", None),
    ("Bale", None),
    ("Bundle", None),
    ("Sack", None),
    ("Litre", "L"),
    ("Millilitre", "ml"),
]

_SPECIES_FEED_LIBRARY = {
    "Cattle": [
        "Fresh Pasture", "Hay", "Silage", "Elephant Grass", "Napier Grass",
        "Rhodes Grass", "Alfalfa Hay", "Maize Stover", "Sorghum Stover",
        "Dairy Meal", "Beef Concentrate", "Wheat Bran", "Rice Bran", "Maize Bran",
        "Cottonseed Cake", "Groundnut Cake", "Palm Kernel Cake", "Molasses",
        "Mineral Supplement", "Salt Lick",
    ],
    "Sheep": [
        "Pasture Grass", "Hay", "Silage", "Alfalfa", "Sheep Concentrate",
        "Wheat Bran", "Rice Bran", "Groundnut Cake", "Cottonseed Cake",
        "Mineral Supplement", "Salt Lick",
    ],
    "Goat": [
        "Browse Leaves", "Pasture Grass", "Hay", "Silage", "Goat Concentrate",
        "Wheat Bran", "Maize Bran", "Groundnut Cake", "Cottonseed Cake",
        "Mineral Supplement", "Salt Lick",
    ],
    "Pig": [
        "Pig Starter Feed", "Pig Grower Feed", "Pig Finisher Feed", "Sow Feed",
        "Boar Feed", "Maize Meal", "Cassava Meal", "Soybean Meal", "Wheat Bran",
        "Rice Bran", "Palm Kernel Cake",
    ],
    "Rabbit": [
        "Rabbit Pellets", "Fresh Grass", "Hay", "Lucerne (Alfalfa)", "Vegetables",
        "Rabbit Concentrate", "Mineral Supplement",
    ],
    "Horse": [
        "Pasture Grass", "Hay", "Alfalfa Hay", "Horse Pellets", "Sweet Feed",
        "Oats", "Barley", "Bran Mash", "Mineral Supplement", "Salt Block",
    ],
    "Camel": [
        "Desert Browse", "Shrubs", "Pasture", "Hay", "Alfalfa", "Camel Concentrate",
        "Dates Supplement", "Mineral Supplement", "Salt Block",
    ],
}

_FEED_TYPE_CATEGORY_MAP = {
    # Forage — fresh/green feed
    "Fresh Pasture": "Forage", "Pasture Grass": "Forage", "Pasture": "Forage",
    "Fresh Grass": "Forage", "Browse Leaves": "Forage", "Desert Browse": "Forage",
    "Shrubs": "Forage", "Elephant Grass": "Forage", "Napier Grass": "Forage",
    "Rhodes Grass": "Forage", "Vegetables": "Forage",
    # Roughage — dried bulky fibrous feed
    "Hay": "Roughage", "Silage": "Roughage", "Alfalfa Hay": "Roughage",
    "Alfalfa": "Roughage", "Lucerne (Alfalfa)": "Roughage",
    "Maize Stover": "Roughage", "Sorghum Stover": "Roughage",
    # Concentrate — formulated / energy-dense feeds
    "Dairy Meal": "Concentrate", "Beef Concentrate": "Concentrate",
    "Sheep Concentrate": "Concentrate", "Goat Concentrate": "Concentrate",
    "Rabbit Concentrate": "Concentrate", "Camel Concentrate": "Concentrate",
    "Pig Starter Feed": "Concentrate", "Pig Grower Feed": "Concentrate",
    "Pig Finisher Feed": "Concentrate", "Sow Feed": "Concentrate",
    "Boar Feed": "Concentrate", "Horse Pellets": "Concentrate",
    "Sweet Feed": "Concentrate", "Rabbit Pellets": "Concentrate",
    "Oats": "Concentrate", "Barley": "Concentrate",
    # By-products — milling / processing residues
    "Wheat Bran": "By-products", "Rice Bran": "By-products",
    "Maize Bran": "By-products", "Cottonseed Cake": "By-products",
    "Groundnut Cake": "By-products", "Palm Kernel Cake": "By-products",
    "Molasses": "By-products", "Maize Meal": "By-products",
    "Cassava Meal": "By-products", "Soybean Meal": "By-products",
    "Bran Mash": "By-products",
    # Mineral
    "Mineral Supplement": "Mineral", "Salt Lick": "Mineral", "Salt Block": "Mineral",
    # Supplement — non-mineral additive
    "Dates Supplement": "Supplement",
}


@router.post("/feed-master/seed/v3/", response={200: APIResponse, 403: APIResponse})
def seed_feed_master_v3(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    if not user.is_superuser:
        raise HttpError(403, "Permission Denied")

    stats = {"categories": 0, "units": 0, "feed_types": 0}

    categories = {}
    for name in _FEED_CATEGORY_NAMES:
        cat, created = FeedCategory.objects.get_or_create(
            name=name, defaults={"is_system": True}
        )
        categories[name] = cat
        if created:
            stats["categories"] += 1

    for name, abbr in _FEED_UNIT_SEED:
        _, created = FeedUnit.objects.get_or_create(
            name=name, farm=None, defaults={"abbreviation": abbr, "is_system": True}
        )
        if created:
            stats["units"] += 1

    species_cache = {
        s.name: s for s in LivestockSpecies.objects.filter(name__in=_SPECIES_FEED_LIBRARY.keys())
    }

    feed_species_map = {}
    for species_name, feed_names in _SPECIES_FEED_LIBRARY.items():
        species = species_cache.get(species_name)
        if not species:
            continue
        for feed_name in feed_names:
            feed_species_map.setdefault(feed_name, set()).add(species.id)

    existing_feed_types = {
        ft.name: ft for ft in FeedType.objects.filter(farm=None, name__in=feed_species_map.keys())
    }

    for feed_name, species_ids in feed_species_map.items():
        category_name = _FEED_TYPE_CATEGORY_MAP.get(feed_name, "Concentrate")
        feed_type = existing_feed_types.get(feed_name)
        if not feed_type:
            feed_type = FeedType.objects.create(
                name=feed_name,
                category=categories[category_name],
                farm=None,
                is_system=True,
            )
            stats["feed_types"] += 1
        feed_type.species.set(species_ids)

    return 200, APIResponse(
        success=True,
        message="Feed master data seeded successfully",
        data=stats,
    )


@router.get("/feed-category/v3/", response={200: APIResponse, 403: APIResponse})
def get_feed_categories_v3(request):
    user_id = get_current_user(request)
    try:
        users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    data = list(
        FeedCategory.objects.filter(is_active=True).values("id", "name", "is_system")
    )
    return 200, APIResponse(success=True, message="Feed categories", data=data)


@router.get("/feed-unit/v3/", response={200: APIResponse, 403: APIResponse})
def get_feed_units_v3(request, farm_id: Optional[int] = None):
    user_id = get_current_user(request)
    try:
        users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    qs = FeedUnit.objects.filter(is_active=True)
    qs = qs.filter(Q(farm=None) | Q(farm_id=farm_id)) if farm_id else qs.filter(farm=None)

    data = list(qs.values("id", "name", "abbreviation", "is_system", "farm_id"))
    return 200, APIResponse(success=True, message="Feed units", data=data)


@router.post("/feed-unit/v3/", response={200: APIResponse, 403: APIResponse})
def create_farm_feed_unit_v3(request, farm_id: int, payload: FeedUnitSchemaIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(403, "Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)

    if FeedUnit.objects.filter(
        name__iexact=payload.name
    ).filter(Q(farm=None) | Q(farm=farm)).exists():
        raise HttpError(409, "Feed unit already exists")

    unit = FeedUnit.objects.create(
        farm=farm,
        name=payload.name,
        abbreviation=payload.abbreviation,
        is_system=False,
    )
    return 200, APIResponse(
        success=True,
        message="Custom feed unit created",
        data={"id": unit.id, "name": unit.name, "abbreviation": unit.abbreviation},
    )


@router.get(
    "/feed-type/v3/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_feed_types_v3(
    request, page: int, page_size: int, farm_id: int, species_id: Optional[int] = None
):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)

    qs = (
        FeedType.objects.filter(Q(farm=None) | Q(farm=farm), is_active=True)
        .select_related("category")
        .prefetch_related("species")
        .distinct()
    )
    if species_id:
        qs = qs.filter(species__id=species_id)

    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)
    serialized = []
    for ft in page_obj.object_list:
        serialized.append(
            {
                "id": ft.id,
                "name": ft.name,
                "category": ft.category.name,
                "category_id": ft.category_id,
                "species": list(ft.species.values_list("name", flat=True)),
                "description": ft.description,
                "manufacturer": ft.manufacturer,
                "is_system": ft.is_system,
                "is_active": ft.is_active,
                "farm_id": ft.farm_id,
            }
        )
    return 200, ListResponseSchema(
        success=True,
        message="feed types fetch successfully",
        data=serialized,
        num_pages=paginator.num_pages,
        current_page=page_obj.number,
        total_items=paginator.count,
        has_next=page_obj.has_next,
        has_previous=page_obj.has_previous,
    )


@router.post("/feed-type/v3/", response={200: APIResponse, 403: APIResponse})
def create_farm_feed_type_v3(request, farm_id: int, payload: FeedTypeSchemaIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(403, "Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    perm = user_has_permission(user, Permissions.Feed.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied")

    if not payload.species_ids:
        raise HttpError(400, "At least one compatible livestock species must be selected")

    category = get_object_or_404(FeedCategory, id=payload.category_id, is_active=True)

    if FeedType.objects.filter(
        name__iexact=payload.name
    ).filter(Q(farm=None) | Q(farm=farm)).exists():
        raise HttpError(409, "Feed type already exists")

    species = LivestockSpecies.objects.filter(id__in=payload.species_ids, is_active=True)
    if species.count() != len(set(payload.species_ids)):
        raise HttpError(400, "One or more livestock species is invalid")

    feed_type = FeedType.objects.create(
        farm=farm,
        name=payload.name,
        category=category,
        description=payload.description,
        manufacturer=payload.manufacturer,
        is_system=False,
        created_by=user,
    )
    feed_type.species.set(species)

    return 200, APIResponse(
        success=True,
        message="Custom feed type created",
        data={
            "id": feed_type.id,
            "name": feed_type.name,
            "category": category.name,
            "species": list(species.values_list("name", flat=True)),
        },
    )


@router.patch("/feed-type/v3/{feed_type_id}/", response={200: APIResponse, 403: APIResponse})
def update_farm_feed_type_v3(request, feed_type_id: int, payload: FeedTypeUpdateSchemaIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    feed_type = get_object_or_404(FeedType, id=feed_type_id)
    if feed_type.is_system:
        raise HttpError(403, "System feed types cannot be modified")

    org = user.organization or user.organizations.first()
    if not org or not org.farms.filter(id=feed_type.farm_id).exists():
        raise HttpError(403, "Permission denied")

    if payload.name is not None:
        if FeedType.objects.filter(
            name__iexact=payload.name
        ).filter(Q(farm=None) | Q(farm_id=feed_type.farm_id)).exclude(id=feed_type.id).exists():
            raise HttpError(409, "Feed type already exists")
        feed_type.name = payload.name
    if payload.category_id is not None:
        feed_type.category = get_object_or_404(FeedCategory, id=payload.category_id, is_active=True)
    if payload.description is not None:
        feed_type.description = payload.description
    if payload.manufacturer is not None:
        feed_type.manufacturer = payload.manufacturer
    if payload.is_active is not None:
        feed_type.is_active = payload.is_active
    feed_type.save()

    if payload.species_ids is not None:
        if not payload.species_ids:
            raise HttpError(400, "At least one compatible livestock species must be selected")
        species = LivestockSpecies.objects.filter(id__in=payload.species_ids, is_active=True)
        if species.count() != len(set(payload.species_ids)):
            raise HttpError(400, "One or more livestock species is invalid")
        feed_type.species.set(species)

    return 200, APIResponse(
        success=True,
        message="Feed type updated",
        data={"id": feed_type.id, "name": feed_type.name, "is_active": feed_type.is_active},
    )


@router.post("/feed-type/v3/{feed_type_id}/deactivate/", response={200: APIResponse, 403: APIResponse})
def deactivate_farm_feed_type_v3(request, feed_type_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)

    feed_type = get_object_or_404(FeedType, id=feed_type_id)
    if feed_type.is_system:
        raise HttpError(403, "System feed types cannot be deactivated")

    org = user.organization or user.organizations.first()
    if not org or not org.farms.filter(id=feed_type.farm_id).exists():
        raise HttpError(403, "Permission denied")

    feed_type.is_active = False
    feed_type.save(update_fields=["is_active"])

    return 200, APIResponse(
        success=True,
        message="Feed type deactivated",
        data={"id": feed_type.id, "is_active": feed_type.is_active},
    )


@router.post("/feed-inventory/v3/", response={200: APIResponse, 403: APIResponse})
def feed_inventory_v3(request, payload: FeedInventorySchemaV3):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Feed.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, "Permission denied")

    farm = get_object_or_404(Farm, id=payload.farm_id, organization=org)
    feed_type = get_object_or_404(
        FeedType.objects.filter(Q(farm=None) | Q(farm=farm)), id=payload.feed_type_id, is_active=True
    )
    feed_unit = get_object_or_404(
        FeedUnit.objects.filter(Q(farm=None) | Q(farm=farm)), id=payload.feed_unit_id, is_active=True
    )

    if FeedInventory.objects.filter(farm=farm, feed_type=feed_type).exists():
        raise HttpError(409, "Inventory record already exists for this feed type")

    feed = FeedInventory(
        farm=farm,
        feed_name=feed_type.name,
        feed_type=feed_type,
        quantity_available=payload.quantity_available,
        unit=feed_unit.abbreviation or feed_unit.name,
        feed_unit=feed_unit,
        reorder_level=payload.reorder_level,
    )
    try:
        feed.full_clean()
        feed.save()
    except ValidationError as e:
        return JsonResponse({"errors": e.message_dict}, status=400)

    data = {
        "id": feed.id,
        "feed_type": feed_type.name,
        "category": feed_type.category.name,
        "quantity_available": feed.quantity_available,
        "unit": feed_unit.name,
    }
    return 200, APIResponse(success=True, message="Feed inventory created successfully", data=data)


@router.get(
    "/feed/v3/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_feed_v3(request, page: int, page_size: int, farm_id: int, species_id: Optional[int] = None):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Feed.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, "Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    qs = FeedInventory.objects.select_related("feed_type__category", "feed_unit").filter(farm=farm)
    if species_id:
        qs = qs.filter(feed_type__species__id=species_id)

    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id": data.id,
                "feed_name": data.feed_name,
                "feed_type_id": data.feed_type_id,
                "category": data.feed_type.category.name if data.feed_type else None,
                "quantity_available": data.quantity_available,
                "unit": data.unit,
                "feed_unit_id": data.feed_unit_id,
                "reorder_level": data.reorder_level,
                "status": data.status,
                "last_restocked_at": data.last_restocked_at,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
            }
        )
    return 200, ListResponseSchema(
        success=True,
        message="feed fetch successfully",
        data=serialized,
        num_pages=paginator.num_pages,
        current_page=page_obj.number,
        total_items=paginator.count,
        has_next=page_obj.has_next,
        has_previous=page_obj.has_previous,
    )


# ---------------------------------------------------------------------------
# Feed batch inventory (spec 4.1 / 4.2)
# ---------------------------------------------------------------------------

@router.post("/feed-batch/", response={200: APIResponse, 403: APIResponse})
def create_feed_batch(request, payload: FeedBatchSchemaIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Feed.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, "Permission denied")

    farm = get_object_or_404(Farm, id=payload.farm_id, organization=org)
    feed_type = get_object_or_404(FeedType.objects.filter(Q(farm=None) | Q(farm=farm)), id=payload.feed_type_id, is_active=True)
    base_unit = get_object_or_404(FeedUnit.objects.filter(Q(farm=None) | Q(farm=farm)), id=payload.base_unit_id, is_active=True)

    if FeedBatch.objects.filter(feed_type=feed_type, farm=farm, batch_number=payload.batch_number).exists():
        raise HttpError(409, "This batch number already exists for this feed type")

    batch = FeedBatch(
        feed_type=feed_type, farm=farm, batch_number=payload.batch_number, purchase_unit=payload.purchase_unit,
        package_size=payload.package_size, number_of_packages=payload.number_of_packages, base_unit=base_unit,
        purchase_price=payload.purchase_price, supplier=payload.supplier, purchase_date=payload.purchase_date,
        expiry_date=payload.expiry_date, storage_location=payload.storage_location,
        minimum_stock_level=payload.minimum_stock_level, created_by=user,
    )
    try:
        batch.save()
    except ValidationError as e:
        return JsonResponse({"errors": e.message_dict}, status=400)

    return 200, APIResponse(
        success=True, message="Feed batch created successfully",
        data={
            "id": batch.id, "feed_type": feed_type.name, "batch_number": batch.batch_number,
            "total_quantity_base_unit": batch.total_quantity_base_unit,
            "cost_per_base_unit": batch.cost_per_base_unit, "cost_per_package": batch.cost_per_package,
        },
    )


@router.get(
    "/feed-batch/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_feed_batches(request, page: int, page_size: int, farm_id: int, feed_type_id: int = None, status: str = None):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    qs = FeedBatch.objects.select_related("feed_type", "base_unit").filter(farm=farm)
    if feed_type_id:
        qs = qs.filter(feed_type_id=feed_type_id)
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)
    serialized = [
        {
            "id": b.id, "feed_type": b.feed_type.name, "feed_type_id": b.feed_type_id, "batch_number": b.batch_number,
            "purchase_unit": b.purchase_unit, "package_size": b.package_size, "number_of_packages": b.number_of_packages,
            "base_unit": b.base_unit.name, "total_quantity_base_unit": b.total_quantity_base_unit,
            "quantity_available": b.quantity_available, "cost_per_package": b.cost_per_package,
            "cost_per_base_unit": b.cost_per_base_unit, "supplier": b.supplier, "expiry_date": b.expiry_date,
            "storage_location": b.storage_location, "minimum_stock_level": b.minimum_stock_level, "status": b.status,
        }
        for b in page_obj.object_list
    ]
    return 200, ListResponseSchema(
        success=True, message="feed batches fetch successfully", data=serialized,
        num_pages=paginator.num_pages, current_page=page_obj.number,
        total_items=paginator.count, has_next=page_obj.has_next, has_previous=page_obj.has_previous,
    )
