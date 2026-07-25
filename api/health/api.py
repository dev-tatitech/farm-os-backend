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
from admin_panel.models import UnitType, Species, Breed, LivestockSpecies, LivestockBreed, FarmHousingUnit, AnimalClassification
from subcriptions.models import SubscriptionPlan, Subscription
from common.utils import generate_ref
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.http import JsonResponse
from .models import (
    TreatmentRecord,
    VaccinationRecord,
    QuarantineRecord,
    MortalityRecord,
    HealthAlert,
    )
from core.models import GroupType
from django.core.exceptions import ValidationError
from .schema import (
    ListResponseSchema,
    APIResponse,
    TreatmentRecordSchema,
    VaccinationRecordSchema,
    QuarantineRecordSchema,
    MortalityRecordSchema,
    ExternalMedicationSchemaIn,
)
from .alerts import run_health_alert_scan
from animals.models import Animal
from pharmacy.models import Drug, DrugBatch
from animals.event import new_event
router = Router(tags=["Health"])

@router.post("/treatment/", response={200: APIResponse, 403: APIResponse},)
def treatment(
    request,
    payload:TreatmentRecordSchema
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
    perm = user_has_permission(user,Permissions.Health.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id =payload.farm_id, organization = org)
    group = None
    animal = None
    treatment_data = {
    "farm": farm,
    "diagnosis": payload.diagnosis,
    "treatment": payload.treatment,
    "severity": payload.severity,
    "treatment_date": payload.treatment_date,
    "created_by": user
    }
    if payload.animal_id:
        animal = get_object_or_404(Animal, id = payload.animal_id, farm = farm)
        treatment_data["animal"] = animal
    if payload.group_id:
        group = get_object_or_404(AnimalGroup, id = payload.group_id, farm = farm)
        treatment_data["group"] = group
    if payload.notes:
        treatment_data["notes"] = payload.notes
    if payload.next_follow_up_date:
        treatment_data["next_follow_up_date"] = payload.next_follow_up_date

    if payload.drug_id:
        treatment_data["drug"] = get_object_or_404(
            Drug.objects.filter(Q(farm=None) | Q(farm=farm)), id=payload.drug_id, is_active=True
        )
    if payload.drug_batch_id:
        treatment_data["drug_batch"] = get_object_or_404(DrugBatch, id=payload.drug_batch_id, farm=farm)
    if payload.quantity_administered:
        treatment_data["quantity_administered"] = payload.quantity_administered
    if payload.dose:
        treatment_data["dose"] = payload.dose
    if payload.frequency:
        treatment_data["frequency"] = payload.frequency
    if payload.duration_days:
        treatment_data["duration_days"] = payload.duration_days
    if payload.administration_route:
        treatment_data["administration_route"] = payload.administration_route
    if payload.administered_by_id:
        treatment_data["administered_by"] = get_object_or_404(users, id=payload.administered_by_id)
    if payload.prescribed_by_id:
        treatment_data["prescribed_by"] = get_object_or_404(users, id=payload.prescribed_by_id)
    if payload.next_dose_date:
        treatment_data["next_dose_date"] = payload.next_dose_date
    if payload.withdrawal_end_date:
        treatment_data["withdrawal_end_date"] = payload.withdrawal_end_date

    treatment = TreatmentRecord(
        **treatment_data
    )
    try:
        treatment.full_clean()
        treatment.save()
    except ValidationError as e:
        if hasattr(e, "message_dict"):
            return JsonResponse({"errors": e.message_dict}, status=400)
        return JsonResponse({"errors": e.messages}, status=400)
    """ 
    AnimalEvent.objects.create(
        farm=instance.farm,
        animal=instance.animal,
        group=instance.group,
        event_type_id=1,  # or fetch dynamically (see below)
        event_date=instance.treatment_date,
        event_title=f"Treatment - {instance.severity}",
        event_summary=instance.diagnosis,
        reference_table="treatment_record",
        reference_id=instance.id,
        created_by=instance.created_by,
    )
    """
    new_event(
        farm, # farm
        animal, # animal 
        "treatment", # event_type
        treatment.treatment_date, # event_date
        f"Treatment - {treatment.severity}", # event_title
        treatment.diagnosis, # event_summary
        "treatment", # reference_table
        treatment.id, # reference_id
        user, # created_by
        group # group
        )
    data={
        "treatment":treatment.treatment,
        "gender": treatment.severity
    }
    return 200,APIResponse(
        success=True,
        message="treatment create successfully",
        data=data
    )

@router.get(
    "/treatment/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_treatment(
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
    perm = user_has_permission(user,Permissions.Health.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    birth = TreatmentRecord.objects.select_related("animal__species", "animal__breed", "animal__livestock_species", "animal__livestock_breed", "created_by", "group__group_type").filter(farm=farm)
    paginator = Paginator(birth, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "animal_tag": data.animal.tag_id if data.animal else None,
                "species": (
                    (data.animal.livestock_species.name if data.animal.livestock_species else (data.animal.species.name if data.animal.species else None))
                    if data.animal else None
                ),
                "breed": (
                    (data.animal.livestock_breed.name if data.animal.livestock_breed else (data.animal.breed.name if data.animal.breed else None))
                    if data.animal else None
                ),
                "group": data.group.name if data.group else None,
                "group_type": data.group.group_type.name if data.group else None,
                "diagnosis": data.diagnosis,
                "treatment": data.treatment,
                "severity": data.severity,
                "treatment_date": data.treatment_date,
                "next_follow_up_date": data.next_follow_up_date,
                "notes": data.notes,
                "created_at": data.created_at,
                "created_by": data.created_by.email,
             
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"treatment fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )
@router.post("/vaccination/", response={200: APIResponse, 403: APIResponse},)
def vaccination(
    request,
    payload:VaccinationRecordSchema
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
    perm = user_has_permission(user,Permissions.Health.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
        
    farm = get_object_or_404(Farm, id =payload.farm_id, organization = org)
    group = None
    animal = None
    vaccination_data = {
    "farm": farm,
    "vaccine_name": payload.vaccine_name,
    "date_given": payload.date_given,
    "created_by": user
    }
    if payload.animal_id:
        animal = get_object_or_404(Animal, id = payload.animal_id, farm = farm)
        vaccination_data["animal"] = animal
    if payload.group_id:
        group = get_object_or_404(AnimalGroup, id = payload.group_id, farm = farm)
        vaccination_data["group"] = group
    if payload.notes:
        vaccination_data["notes"] = payload.notes
    if payload.next_due_date:
        vaccination_data["next_due_date"] = payload.next_due_date
    vaccin = VaccinationRecord(
        **vaccination_data
    )
    try:
        vaccin.full_clean()
        vaccin.save()
    except ValidationError as e:
        return JsonResponse({
        "errors": e.message_dict
        }, status=400)
    """ 
   AnimalEvent.objects.create(
    farm=instance.farm,
    animal=instance.animal,
    group=instance.group,
    event_type_id=2,  # vaccination (example)
    event_date=instance.date_given,
    event_title=f"Vaccination - {instance.vaccine_name}",
    event_summary=instance.notes,
    reference_table="vaccination_record",
    reference_id=instance.id,
    created_by=instance.created_by,
)
    """
    new_event(
        farm, # farm
        animal, # animal 
        "vaccination", # event_type
        vaccin.date_given, # event_date
        f"Vaccination - {vaccin.vaccine_name}", # event_title
        vaccin.notes, # event_summary
        "vaccination", # reference_table
        vaccin.id, # reference_id
        user, # created_by
        group # group
        )
    data={
        "vaccine_name":vaccin.vaccine_name,
        "date_given": vaccin.date_given
    }
    return 200,APIResponse(
        success=True,
        message="VaccinationRecord create successfully",
        data=data
    )

@router.get(
    "/vaccination/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_vaccination(
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
    perm = user_has_permission(user,Permissions.Health.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    vaccin = VaccinationRecord.objects.select_related("animal__species", "animal__breed", "animal__livestock_species", "animal__livestock_breed", "created_by", "group__group_type").filter(farm=farm)
    paginator = Paginator(vaccin, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "animal_tag": data.animal.tag_id if data.animal else None,
                "species": (
                    (data.animal.livestock_species.name if data.animal.livestock_species else (data.animal.species.name if data.animal.species else None))
                    if data.animal else None
                ),
                "breed": (
                    (data.animal.livestock_breed.name if data.animal.livestock_breed else (data.animal.breed.name if data.animal.breed else None))
                    if data.animal else None
                ),
                "group": data.group.name if data.group else None,
                "group_type": data.group.group_type.name if data.group else None,
                "vaccine_name": data.vaccine_name,
                "date_given": data.date_given,
                "next_due_date": data.next_due_date,
                "notes": data.notes,
                "created_at": data.created_at,
                "created_by": data.created_by.email,
             
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"vaccination fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )
    
@router.post("/quarantine/", response={200: APIResponse, 403: APIResponse},)
def quarantine(
    request,
    payload:QuarantineRecordSchema
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
    perm = user_has_permission(user,Permissions.Health.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id =payload.farm_id, organization = org)
    animal = get_object_or_404(Animal, id = payload.animal_id, farm = farm)
    vaccination_data = {
    "farm": farm,
    "animal": animal,
    "reason": payload.reason,
    "start_date": payload.start_date,
    "created_by": user
    }
    if payload.notes:
        vaccination_data["notes"] = payload.notes
    quarantine = QuarantineRecord(
        **vaccination_data
    )
    try:
        quarantine.full_clean()
        quarantine.save()
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
        farm, # farm
        animal, # animal 
        "quarantine", # event_type
        quarantine.start_date, # event_date
        f"Quarantine - {quarantine.status}", # event_title
        quarantine.reason, # event_summary
        "quarantine", # reference_table
        quarantine.id, # reference_id
        user, # created_by

        )
    data={
        "reason":quarantine.reason,
        "start_date": quarantine.start_date
    }
    return 200,APIResponse(
        success=True,
        message="Quarantine create successfully",
        data=data
    )

@router.get(
    "/quarantine/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_quarantine(
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
    perm = user_has_permission(user,Permissions.Health.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    qr = QuarantineRecord.objects.select_related("animal__species", "animal__breed", "animal__livestock_species", "animal__livestock_breed", "created_by").filter(farm=farm)
    paginator = Paginator(qr, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "animal_tag": data.animal.tag_id if data.animal else None,
                "species": (
                    (data.animal.livestock_species.name if data.animal.livestock_species else (data.animal.species.name if data.animal.species else None))
                    if data.animal else None
                ),
                "breed": (
                    (data.animal.livestock_breed.name if data.animal.livestock_breed else (data.animal.breed.name if data.animal.breed else None))
                    if data.animal else None
                ),
                "reason": data.reason,
                "start_date": data.start_date,
                "end_date": data.end_date,
                "status": data.status,
                "notes": data.notes,
                "created_at": data.created_at,
                "created_by": data.created_by.email,
             
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"QuarantineRecord fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )
    
@router.post("/mortality/", response={200: APIResponse, 403: APIResponse},)
def mortality(
    request,
    payload:MortalityRecordSchema
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
    perm = user_has_permission(user,Permissions.Health.CREATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id =payload.farm_id, organization = org)
    animal = get_object_or_404(Animal, id = payload.animal_id, farm = farm)
    mortality_data = {
    "farm": farm,
    "animal": animal,
    "cause": payload.cause,
    "death_date": payload.death_date,
    "created_by": user
    }
    if payload.notes:
        mortality_data["notes"] = payload.notes
    mortality = MortalityRecord(
        **mortality_data
    )
    try:
        mortality.full_clean()
        mortality.save()
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
    farm,  # farm
    animal,  # animal
    "mortality",  # event_type
    mortality.death_date,  # event_date
    f"Death Recorded - {animal.tag_id}",  # event_title
    mortality.cause,  # event_summary
    "mortality",  # reference_table
    mortality.id,  # reference_id
    user,  # created_by
    group=None  # optional
)
    data={
        "reason":mortality.cause,
        "start_date": mortality.death_date
    }
    return 200,APIResponse(
        success=True,
        message="mortality create successfully",
        data=data
    )

@router.get(
    "/mortality/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_mortality(
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
    perm = user_has_permission(user,Permissions.Health.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    mt = MortalityRecord.objects.select_related("animal__species", "animal__breed", "animal__livestock_species", "animal__livestock_breed", "created_by").filter(farm=farm)
    paginator = Paginator(mt, page_size)
    page_obj = paginator.page(page)
    # Serialization
    serialized = []
    for data in page_obj.object_list:
        serialized.append(
            {
                "id":data.id,
                "animal_tag": data.animal.tag_id if data.animal else None,
                "species": (
                    (data.animal.livestock_species.name if data.animal.livestock_species else (data.animal.species.name if data.animal.species else None))
                    if data.animal else None
                ),
                "breed": (
                    (data.animal.livestock_breed.name if data.animal.livestock_breed else (data.animal.breed.name if data.animal.breed else None))
                    if data.animal else None
                ),
                "cause": data.cause,
                "death_date": data.death_date,
                "notes": data.notes,
                "created_at": data.created_at,
                "created_by": data.created_by.email,
             
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message=f"Mortality fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )


# ── v2 endpoints ─────────────────────────────────────────────────────────────

@router.get(
    "/treatment/v2/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_treatment_v2(
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
    perm = user_has_permission(user, Permissions.Health.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    records = TreatmentRecord.objects.select_related(
        "animal__livestock_species",
        "animal__livestock_breed",
        "animal__classification",
        "animal__species",
        "animal__breed",
        "created_by",
        "group__group_type",
    ).filter(farm=farm)
    paginator = Paginator(records, page_size)
    page_obj = paginator.page(page)
    serialized = []
    for r in page_obj.object_list:
        serialized.append(
            {
                "id": r.id,
                "animal_tag": r.animal.tag_id if r.animal else None,
                "species": (r.animal.livestock_species.name if r.animal.livestock_species else (r.animal.species.name if r.animal.species else None)) if r.animal else None,
                "breed": (r.animal.livestock_breed.name if r.animal.livestock_breed else (r.animal.breed.name if r.animal.breed else None)) if r.animal else None,
                "classification": (r.animal.classification.name if r.animal.classification else None) if r.animal else None,
                "group": r.group.name if r.group else None,
                "group_type": r.group.group_type.name if r.group else None,
                "diagnosis": r.diagnosis,
                "treatment": r.treatment,
                "severity": r.severity,
                "treatment_date": r.treatment_date,
                "next_follow_up_date": r.next_follow_up_date,
                "notes": r.notes,
                "created_at": r.created_at,
                "created_by": r.created_by.email,
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message="treatment fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )


@router.get(
    "/vaccination/v2/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_vaccination_v2(
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
    perm = user_has_permission(user, Permissions.Health.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    records = VaccinationRecord.objects.select_related(
        "animal__livestock_species",
        "animal__livestock_breed",
        "animal__classification",
        "animal__species",
        "animal__breed",
        "created_by",
        "group__group_type",
    ).filter(farm=farm)
    paginator = Paginator(records, page_size)
    page_obj = paginator.page(page)
    serialized = []
    for r in page_obj.object_list:
        serialized.append(
            {
                "id": r.id,
                "animal_tag": r.animal.tag_id if r.animal else None,
                "species": (r.animal.livestock_species.name if r.animal.livestock_species else (r.animal.species.name if r.animal.species else None)) if r.animal else None,
                "breed": (r.animal.livestock_breed.name if r.animal.livestock_breed else (r.animal.breed.name if r.animal.breed else None)) if r.animal else None,
                "classification": (r.animal.classification.name if r.animal.classification else None) if r.animal else None,
                "group": r.group.name if r.group else None,
                "group_type": r.group.group_type.name if r.group else None,
                "vaccine_name": r.vaccine_name,
                "date_given": r.date_given,
                "next_due_date": r.next_due_date,
                "notes": r.notes,
                "created_at": r.created_at,
                "created_by": r.created_by.email,
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message="vaccination fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )


@router.get(
    "/quarantine/v2/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_quarantine_v2(
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
    perm = user_has_permission(user, Permissions.Health.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    records = QuarantineRecord.objects.select_related(
        "animal__livestock_species",
        "animal__livestock_breed",
        "animal__classification",
        "animal__species",
        "animal__breed",
        "created_by",
    ).filter(farm=farm)
    paginator = Paginator(records, page_size)
    page_obj = paginator.page(page)
    serialized = []
    for r in page_obj.object_list:
        serialized.append(
            {
                "id": r.id,
                "animal_tag": r.animal.tag_id if r.animal else None,
                "species": (r.animal.livestock_species.name if r.animal.livestock_species else (r.animal.species.name if r.animal.species else None)) if r.animal else None,
                "breed": (r.animal.livestock_breed.name if r.animal.livestock_breed else (r.animal.breed.name if r.animal.breed else None)) if r.animal else None,
                "classification": (r.animal.classification.name if r.animal.classification else None) if r.animal else None,
                "reason": r.reason,
                "start_date": r.start_date,
                "end_date": r.end_date,
                "status": r.status,
                "notes": r.notes,
                "created_at": r.created_at,
                "created_by": r.created_by.email,
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message="QuarantineRecord fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )


@router.get(
    "/mortality/v2/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_mortality_v2(
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
    perm = user_has_permission(user, Permissions.Health.VIEW)
    if not user.organizations.first():
        if not perm:
            raise HttpError(404, f"Permission denied")
    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    records = MortalityRecord.objects.select_related(
        "animal__livestock_species",
        "animal__livestock_breed",
        "animal__classification",
        "animal__species",
        "animal__breed",
        "created_by",
    ).filter(farm=farm)
    paginator = Paginator(records, page_size)
    page_obj = paginator.page(page)
    serialized = []
    for r in page_obj.object_list:
        serialized.append(
            {
                "id": r.id,
                "animal_tag": r.animal.tag_id if r.animal else None,
                "species": (r.animal.livestock_species.name if r.animal.livestock_species else (r.animal.species.name if r.animal.species else None)) if r.animal else None,
                "breed": (r.animal.livestock_breed.name if r.animal.livestock_breed else (r.animal.breed.name if r.animal.breed else None)) if r.animal else None,
                "classification": (r.animal.classification.name if r.animal.classification else None) if r.animal else None,
                "cause": r.cause,
                "death_date": r.death_date,
                "notes": r.notes,
                "created_at": r.created_at,
                "created_by": r.created_by.email,
            }
        )
    return 200, ListResponseSchema(
            success=True,
            message="Mortality fetch successfully",
            data=serialized,
            num_pages=paginator.num_pages,
            current_page=page_obj.number,
            total_items=paginator.count,
            has_next=page_obj.has_next,
            has_previous=page_obj.has_previous,
        )


# ─── Health & Performance Alerts ──────────────────────────────────────────────

@router.post("/health-alert/scan/{animal_id}/", response={200: APIResponse, 403: APIResponse})
def scan_animal_health_alerts(request, animal_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    animal = get_object_or_404(Animal, id=animal_id, farm__organization=org)
    triggered = run_health_alert_scan(animal)
    data = [
        {
            "id": a.id, "alert_type": a.alert_type, "severity": a.severity,
            "evidence": a.evidence, "recommended_review": a.recommended_review,
        }
        for a in triggered
    ]
    return 200, APIResponse(success=True, message="Health alert scan complete", data=data)


@router.get(
    "/health-alert/{page}/{page_size}/{farm_id}",
    response={200: ListResponseSchema, 403: APIResponse},
)
def get_health_alerts(request, page: int, page_size: int, farm_id: int, status: str = None, severity: str = None):
    user_id = get_current_user(request)
    try:
        user = users.objects.select_related("organization").prefetch_related("organizations").get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Login Failed")
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")

    farm = get_object_or_404(Farm, id=farm_id, organization=org)
    qs = HealthAlert.objects.select_related("animal", "assigned_user", "resolved_by").filter(farm=farm)
    if status:
        qs = qs.filter(status=status)
    if severity:
        qs = qs.filter(severity=severity)

    paginator = Paginator(qs, page_size)
    page_obj = paginator.page(page)
    serialized = [
        {
            "id": a.id,
            "animal_id": a.animal_id,
            "animal_tag": a.animal.tag_id if a.animal else None,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "detected_date": a.detected_date,
            "evidence": a.evidence,
            "recommended_review": a.recommended_review,
            "assigned_user": a.assigned_user.email if a.assigned_user else None,
            "status": a.status,
            "resolution_notes": a.resolution_notes,
            "resolved_by": a.resolved_by.email if a.resolved_by else None,
            "resolution_date": a.resolution_date,
            "created_at": a.created_at,
        }
        for a in page_obj.object_list
    ]
    return 200, ListResponseSchema(
        success=True,
        message="health alerts fetch successfully",
        data=serialized,
        num_pages=paginator.num_pages,
        current_page=page_obj.number,
        total_items=paginator.count,
        has_next=page_obj.has_next,
        has_previous=page_obj.has_previous,
    )


@router.post("/health-alert/{alert_id}/resolve/", response={200: APIResponse, 403: APIResponse})
def resolve_health_alert(request, alert_id: int, resolution_notes: str = ""):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Health.UPDATE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied: resolving health alerts requires explicit authorization")

    alert = get_object_or_404(HealthAlert, id=alert_id, farm__organization=org)
    alert.status = "resolved"
    alert.resolution_notes = resolution_notes
    alert.resolved_by = user
    alert.resolution_date = timezone.localdate()
    alert.save(update_fields=["status", "resolution_notes", "resolved_by", "resolution_date"])

    return 200, APIResponse(success=True, message="Health alert resolved", data={"id": alert.id, "status": alert.status})


# ─── External / Emergency Medication (spec 3.4) ───────────────────────────────

@router.post("/treatment/external/", response={200: APIResponse, 403: APIResponse})
def record_external_medication(request, payload: ExternalMedicationSchemaIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Pharmacy.EXTERNAL_OVERRIDE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied: external medication requires explicit authorization")

    farm = get_object_or_404(Farm, id=payload.farm_id, organization=org)

    treatment_data = dict(
        farm=farm,
        diagnosis=payload.diagnosis,
        treatment=f"External/emergency administration: {payload.external_drug_name}",
        severity=payload.severity,
        treatment_date=payload.treatment_date,
        created_by=user,
        is_external_administration=True,
        external_drug_name=payload.external_drug_name,
        quantity_administered=payload.quantity_administered,
        external_unit=payload.unit,
        external_unit_cost=payload.external_unit_cost,
        external_source=payload.external_source,
        external_reason=payload.external_reason,
        notes=payload.notes or "",
    )
    if payload.animal_id:
        treatment_data["animal"] = get_object_or_404(Animal, id=payload.animal_id, farm=farm)
    if payload.group_id:
        treatment_data["group"] = get_object_or_404(AnimalGroup, id=payload.group_id, farm=farm)
    if payload.drug_id:
        treatment_data["drug"] = get_object_or_404(
            Drug.objects.filter(Q(farm=None) | Q(farm=farm)), id=payload.drug_id, is_active=True
        )

    treatment = TreatmentRecord(**treatment_data)
    try:
        treatment.full_clean()
        treatment.save()
    except ValidationError as e:
        if hasattr(e, "message_dict"):
            return JsonResponse({"errors": e.message_dict}, status=400)
        return JsonResponse({"errors": e.messages}, status=400)

    return 200, APIResponse(
        success=True,
        message="External medication recorded successfully",
        data={
            "id": treatment.id,
            "external_drug_name": treatment.external_drug_name,
            "treatment_cost": treatment.treatment_cost,
        },
    )


@router.post("/treatment/{treatment_id}/reconcile-to-inventory/", response={200: APIResponse, 403: APIResponse})
def reconcile_external_medication(request, treatment_id: int, batch_number: str, minimum_stock_level: float = None):
    """
    Formally adds a previously-external/emergency administration to the
    pharmacy batch ledger after the fact — the batch is created already
    fully consumed (quantity_available=0), since the dose was administered
    before it entered inventory. This is for audit/traceability only; it
    does not re-charge the cost (already posted when the treatment was
    recorded).
    """
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = user.organization or user.organizations.first()
    if not org:
        raise HttpError(404, "Permission denied")
    perm = user_has_permission(user, Permissions.Pharmacy.EXTERNAL_OVERRIDE)
    if not user.organizations.first():
        if not perm:
            raise HttpError(403, "Permission denied: external medication requires explicit authorization")

    treatment = get_object_or_404(TreatmentRecord, id=treatment_id, farm__organization=org, is_external_administration=True)
    if treatment.reconciled_to_batch_id:
        raise HttpError(409, "This external medication has already been reconciled to inventory")
    if not treatment.drug_id:
        raise HttpError(400, "This external medication is not linked to a registered Drug — register the drug first")

    batch = DrugBatch.objects.create(
        drug=treatment.drug, farm=treatment.farm, batch_number=batch_number,
        quantity_received=treatment.quantity_administered, quantity_available=0,
        purchase_price=(treatment.external_unit_cost or 0) * (treatment.quantity_administered or 0),
        supplier=treatment.external_source, purchase_date=treatment.treatment_date,
        expiry_date=treatment.treatment_date, status="depleted", created_by=user,
    )
    treatment.reconciled_to_batch = batch
    treatment.save(update_fields=["reconciled_to_batch"])

    return 200, APIResponse(
        success=True,
        message="External medication reconciled to inventory",
        data={"treatment_id": treatment.id, "batch_id": batch.id},
    )
