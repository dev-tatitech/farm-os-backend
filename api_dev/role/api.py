from common.mutations import atomic_mutation
from ninja import Router, Query
from django.conf import settings
from ninja import File
from account.auth import get_current_user, validate_crftoken
from account.models import User as users, User, EmailValidation
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
from django.contrib.auth.hashers import make_password, check_password
from collections import defaultdict
from ninja.errors import HttpError
from django.core.exceptions import ValidationError
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
from account.helper import generate_unique_username, email_sender, send_sub_account_otp_email, get_cookie_domain, get_app_type, save_uploaded_file
from common.utils import generate_strong_password
from django.db.models.functions import Round
from django.db.models import Value
from django.http import HttpResponse
from django.contrib.auth.password_validation import validate_password
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
    RoleIn,
    RoleUpdateSchema,
    NewUserIn,
    NewUserActivateAccountIn,
    NewUserRoleIn,
    UserRolePatchIn,
    RolePermissionIn
)
from common.access import organization_for, owner
from common.audit import security_event
from contract.authz import require_permission
from contract.exceptions import ContractError
from contract.codes import ErrorCode

router = Router(tags=["User and Role management"])


def _authority(request, capability):
    actor = User.objects.get(pk=get_current_user(request))
    org = organization_for(actor)
    if org is None:
        raise ContractError(404, ErrorCode.ORGANIZATION_NOT_FOUND, "Organization could not be found.")
    require_permission(actor, org, capability)
    return org


def _assignment_state(row):
    return {"user_id": str(row.user_id), "role_id": row.role_id, "farm_id": row.farm_id, "status": row.status}


def _validate_assignment(org, user, role, farm):
    if owner(user, org) or user.organization_id != org.id or user.account_status != "active" or not user.is_active:
        raise ContractError(422, ErrorCode.INVALID_ROLE_ASSIGNMENT, "An active staff member is required.")
    if role.organization_id != org.id or not role.active:
        raise ContractError(422, ErrorCode.INVALID_ROLE_ASSIGNMENT, "An active organization role is required.")
    if farm.organization_id != org.id or farm.status != "active":
        raise ContractError(422, ErrorCode.INVALID_FARM_ASSIGNMENT, "An active organization farm is required.")



def _paged_rows(queryset, page, page_size, serializer, message):
    page = max(int(page or 1), 1)
    page_size = min(max(int(page_size or 20), 1), 100)
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)
    return APIResponse(
        success=True,
        message=message,
        data=[serializer(row) for row in page_obj.object_list],
        meta={
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total_items": paginator.count,
                "total_pages": paginator.num_pages,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
            }
        },
    )
@router.get(
    "/permission/",
    response={200: APIResponse, 403: APIResponse},
)
def get_permission(request, page: int = 1, page_size: int = 20):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    
    org = _authority(request, "view_roles")
    plans = Permission.objects.all()
    return 200, _paged_rows(plans, page, page_size, lambda plan: {
         "id": plan.id,
         "code": plan.code  ,
         "name": plan.name  ,   
         "module": plan.module  ,
          "description": plan.description  ,   
        }, "permission fetch successfully")

@router.post(
    "/role/",
    response={200: APIResponse, 403: APIResponse},
)
@atomic_mutation
def role(request, payload: RoleIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
 
    org = _authority(request, "create_role")
    if not payload.name.strip():
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Role name is required.")
    normalized = " ".join(payload.name.split()).casefold()
    if Role.objects.filter(normalized_name=normalized, organization=org).exists():
        raise ContractError(409, ErrorCode.ROLE_NAME_ALREADY_EXISTS, "Role name must be unique within this organization.")
    code = f"RL-{generate_ref()}"
    role = Role.objects.create(
        organization = org,
        name = " ".join(payload.name.split()),
        normalized_name = normalized,
        code = code,
        description = payload.description,
        web_access=payload.web_access, mobile_access=payload.mobile_access,
    )
    security_event("ROLE_CREATED", user, target=role, org=org, new={"name": role.name})
    data = {
     "id": role.id,
     "nae": role.name   
    }
    return 200, APIResponse(
        success=True, message="Role created successfully", data=data
    )
    
@router.get(
    "/role/",
    response={200: APIResponse, 403: APIResponse},
)
def get_role(request, page: int = 1, page_size: int = 20):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = _authority(request, "view_roles")
    plans = Role.objects.filter(organization = org)
    return 200, _paged_rows(plans, page, page_size, lambda plan: {
         "id": plan.id,
         "code": plan.code  ,
         "name": plan.name  ,   
          "description": plan.description  ,   
        }, "Role fetch successfully")

@router.patch(
    "/role/",
    response={200: APIResponse, 403: APIResponse},
)
@atomic_mutation
def update_role(request, payload:RoleUpdateSchema):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = _authority(request, "update_role")
    role = get_object_or_404(Role, id = payload.role_id, organization=org)
    previous = {"name": role.name, "description": role.description}
    if payload.name is not None:
        if not payload.name.strip():
            raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Role name is required.")
        normalized = " ".join(payload.name.split()).casefold()
        if Role.objects.filter(
            organization=role.organization,
            normalized_name=normalized,
        ).exclude(id=role.id).exists():
            raise HttpError(409, "Role name must be unique within this organization.")
        role.name = " ".join(payload.name.split())
        role.normalized_name = normalized
    if payload.description is not None:
        role.description = payload.description
    for field in ("active", "web_access", "mobile_access"):
        if getattr(payload, field) is not None:
            setattr(role, field, getattr(payload, field))
    role.save()
    security_event("ROLE_UPDATED", user, target=role, org=org, previous=previous,
                   new={"name": role.name, "description": role.description, "active": role.active,
                        "web_access": role.web_access, "mobile_access": role.mobile_access})
    data ={
         "id": role.id,
         "code": role.code  ,
         "name": role.name  ,   
          "description": role.description  ,   
        }
  
    return 200, APIResponse(
        success=True, message="Role update successfully", data=data
    )
    
@router.delete(
    "/role/{role_id}",
    response={200: APIResponse, 403: APIResponse},
)
@atomic_mutation
def delete_role(request, role_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = _authority(request, "update_role")
    role = get_object_or_404(Role, id = role_id, organization=org)
    if UserRole.objects.filter(role=role).exists():
        raise ContractError(409, ErrorCode.ROLE_IN_USE, "Role has assignment history; deactivate it instead.")
    role.active = False
    role.save(update_fields=["active"])
    security_event("ROLE_UPDATED", user, target=role, org=org, previous={"active": True}, new={"active": False})
    return 200, APIResponse(
        success=True, message="Role archived successfully", data=None
    )
    

@router.post(
    "/user/",
    response={200: APIResponse, 403: APIResponse},
)
@atomic_mutation
def add_user(request, payload: NewUserIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    
    if User.objects.filter(email=payload.email).exists():
       raise HttpError(400, "Email already exists.")
    org = _authority(request, "invite_user")

    username = generate_unique_username()
    password = generate_strong_password()
    client = User.objects.create(
        username=username, 
        password=make_password(password), 
        email=payload.email,
        organization = org,
        account_status = "invited"
    )
    db_transaction.on_commit(lambda: send_sub_account_otp_email(client, client.email))
    return 200, APIResponse(
        success=True, message="New User added successfully", data=None
    )
    
@router.post(
    "/new/user/activate/",
    response={200: APIResponse, 403: APIResponse},
)
def acitate_user(request, payload: NewUserActivateAccountIn):
    """ 
    a user who added by admin only can use this endpoint
    """
    if payload.password != payload.confirm_password:
        raise HttpError(400, "Passwords do not match")
    user = get_object_or_404(User, email = payload.email)
    if user.account_status != "invited":
        raise HttpError(400, "account already active")
    try:
        otp=payload.otp.strip()  
        otp_record = EmailValidation.objects.get(
            email=payload.email,
            code=otp,
            is_used=False,
            expires_at__gte=datetime.now(),
        )
    except EmailValidation.DoesNotExist:
        return JsonResponse({"detail": "Invalid OTP or Email"}, status=400)
    with db_transaction.atomic():
        otp_record.is_used = True
        otp_record.save()
        user.password = make_password(payload.password)
        user.account_status = "active"
        user. save()
    return 200,APIResponse(
        success=True,
        message="account activated successfully",
        data=None
    )
    
@router.get(
    "/new/user/activate/{email}",
    response={200: APIResponse, 403: APIResponse},
)
def resent_otp_new_user(request, email: EmailStr):
    """ 
    new otp request for new user added by admin only
    """
    user = get_object_or_404(User, email = email)
    if user.account_status != "invited":
        raise HttpError(400, "account already active")
    send_sub_account_otp_email(user,user.email)

    return 200,APIResponse(
        success=True,
        message="new otp send successfully",
        data=None
    )
    
@router.get(
    "/user/",
    response={200: APIResponse, 403: APIResponse},
)
def get_user(request, page: int = 1, page_size: int = 20):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    org = _authority(request, "view_people")
    all_user = User.objects.filter(organization =org)
    return 200, _paged_rows(all_user, page, page_size, lambda user: {
        "id": user.id,
        "email": user.email
    }, "user fetch successfully")
    
@router.post(
    "/user-role/",
    response={200: APIResponse},
)
@atomic_mutation
def assign_user_role(request, payload: NewUserRoleIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    org = _authority(request, "manage_user_assignment")
    my_user = get_object_or_404(User, organization= org, id = payload.user_id)
    role = get_object_or_404(Role, organization = org, id =payload.role_id)
    farm = get_object_or_404(Farm, organization = org, id = payload.farm_id)
    if my_user.id == org.user_id:
        raise HttpError(403, "Organization ownership cannot be replaced by a role assignment.")
    _validate_assignment(org, my_user, role, farm)
    if UserRole.objects.filter(
        user = my_user,
        role = role,
        farm = farm,
        status="active",
       ).exists():
       raise HttpError(400, "Role already exists.")

    # A user has one active staff role per farm. Reassigning the user keeps
    # the old assignment as history, but it must stop granting access.
    now = timezone.now()
    previous_assignments = list(
        UserRole.objects.select_for_update()
        .filter(user=my_user, farm=farm, status="active")
        .select_related("role")
    )
    for previous_assignment in previous_assignments:
        previous_state = _assignment_state(previous_assignment)
        previous_assignment.status = "revoked"
        previous_assignment.revoked_at = now
        previous_assignment.revoked_by = user
        previous_assignment.save(update_fields=["status", "revoked_at", "revoked_by", "updated_at"])
        security_event(
            "USER_ASSIGNMENT_REVOKED",
            user,
            target=previous_assignment,
            org=org,
            farm=farm,
            previous=previous_state,
            new={**previous_state, "status": "revoked"},
        )

    user_role = UserRole.objects.create(
        user = my_user,
        role = role,
        farm = farm,
        assigned_by = user
    )
    security_event("USER_ASSIGNMENT_CREATED", user, target=user_role, org=org, farm=farm,
                   new=_assignment_state(user_role))
    data = {"assignment": {
        "id": user_role.id,
        "user_id": str(user_role.user_id),
        "farm_id": user_role.farm_id,
        "role_id": user_role.role_id,
        "status": user_role.status,
    }}
    return 200,APIResponse(
        success=True,
        message="role assign added successfully",
        data=data
    )


@router.patch("/user-role/{assignment_id}/", response={200: APIResponse, 403: APIResponse})
@atomic_mutation
def update_user_role(request, assignment_id: int, payload: UserRolePatchIn):
    actor_id = get_current_user(request)
    actor = get_object_or_404(User, id=actor_id)
    org = _authority(request, "manage_user_assignment")
    assignment = get_object_or_404(
        UserRole.objects.select_related("user", "role", "farm"),
        id=assignment_id,
        farm__organization=org,
        status="active",
    )
    if assignment.user_id == org.user_id:
        raise HttpError(403, "Organization owner assignments cannot be changed.")
    previous = _assignment_state(assignment)
    if payload.farm_id is not None:
        assignment.farm = get_object_or_404(Farm, id=payload.farm_id, organization=org)
    if payload.role_id is not None:
        assignment.role = get_object_or_404(Role, id=payload.role_id, organization=org)
    if payload.farm_id is None and payload.role_id is None:
        raise HttpError(422, "farm_id or role_id is required.")
    _validate_assignment(org, assignment.user, assignment.role, assignment.farm)
    if UserRole.objects.filter(user=assignment.user, role=assignment.role, farm=assignment.farm, status="active").exclude(pk=assignment.pk).exists():
        raise ContractError(409, ErrorCode.CONFLICT, "Assignment already exists.")
    assignment.save(update_fields=["farm", "role", "updated_at"])
    security_event("USER_ASSIGNMENT_UPDATED", actor, target=assignment, org=org, farm=assignment.farm,
                   previous=previous, new=_assignment_state(assignment))
    return 200, APIResponse(
        success=True,
        message="User assignment updated successfully.",
        data={"assignment": {
            "id": assignment.id,
            "user_id": str(assignment.user_id),
            "farm_id": assignment.farm_id,
            "role_id": assignment.role_id,
            "status": assignment.status,
        }},
    )


@router.delete("/user-role/{assignment_id}/", response={200: APIResponse, 403: APIResponse})
@atomic_mutation
def revoke_user_role(request, assignment_id: int):
    actor_id = get_current_user(request)
    actor = get_object_or_404(User, id=actor_id)
    org = _authority(request, "manage_user_assignment")
    assignment = get_object_or_404(
        UserRole.objects.select_related("user", "farm"),
        id=assignment_id,
        farm__organization=org,
    )
    if assignment.status == "revoked":
        raise ContractError(409, ErrorCode.ASSIGNMENT_ALREADY_REVOKED, "Assignment already revoked.")
    if assignment.user_id == org.user_id:
        raise HttpError(403, "Organization owner access cannot be revoked.")
    previous = _assignment_state(assignment)
    assignment.status = "revoked"
    assignment.revoked_at = timezone.now()
    assignment.revoked_by = actor
    assignment.save(update_fields=["status", "revoked_at", "revoked_by", "updated_at"])
    security_event("USER_ASSIGNMENT_REVOKED", actor, target=assignment, org=org, farm=assignment.farm,
                   previous=previous, new=_assignment_state(assignment))
    return 200, APIResponse(
        success=True,
        message="Farm assignment removed successfully.",
        data={"assignment_id": assignment.id, "status": assignment.status},
    )
    
@router.get("/user-role/", response={200: APIResponse, 403: APIResponse})
def get_user_role(request, page: int = 1, page_size: int = 20):
    user_id = get_current_user(request)

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        raise HttpError(403, "Permission denied")

    org = _authority(request, "view_people")
    all_users = (
        User.objects
        .filter(organization=org)
        .prefetch_related(
            "user_roles__role",
            "user_roles__farm"
        )
    )
    role_permissions = RolePermission.objects.select_related("permission", "role")

    permission_map = defaultdict(list)
    for rp in role_permissions:
        permission_map[rp.role_id].append(rp.permission.name)

    data = []

    for usa in all_users:
        role_map = {}

        for ur in usa.user_roles.filter(status="active"):
            role_id = ur.role.id

            if role_id not in role_map:
                role_map[role_id] = {
                    "id": role_id,
                    "role": ur.role.name,
                    "farms": [],
                    "permissions": permission_map.get(role_id, [])
                }
            if ur.farm:
                role_map[role_id]["farms"].append(ur.farm.name)

        data.append({
            "id": usa.id,
            "email": usa.email,
            "roles": list(role_map.values())
        })

    return 200, _paged_rows(
        data, page, page_size, lambda row: row, "User roles fetched successfully"
    )
@router.post(
    "/role-permission/",
    response={200: APIResponse},
)
@atomic_mutation
def assign_role_permission(request, payload: RolePermissionIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    org = _authority(request, "manage_role_permissions")
    role = get_object_or_404(Role, organization=org, id=payload.role_id)

    permissions = Permission.objects.filter(id__in=payload.permission_ids)
    found_ids = set(permissions.values_list("id", flat=True))
    missing = set(payload.permission_ids) - found_ids
    if missing:
        raise HttpError(404, f"Permission(s) not found: {sorted(missing)}")

    previous = list(RolePermission.objects.filter(role=role).values_list("permission_id", flat=True))
    with db_transaction.atomic():
        Role.objects.select_for_update().get(pk=role.pk)
        RolePermission.objects.filter(role=role).delete()
        RolePermission.objects.bulk_create(
            [RolePermission(role=role, permission=p) for p in permissions]
        )
    authoritative_ids = list(
        RolePermission.objects.filter(role=role)
        .order_by("permission_id")
        .values_list("permission_id", flat=True)
    )
    security_event("ROLE_PERMISSIONS_UPDATED", user, target=role, org=org,
                   previous={"permission_ids": previous}, new={"permission_ids": authoritative_ids})
    data = {"role_id": role.id, "permission_ids": authoritative_ids}
    return 200, APIResponse(
        success=True,
        message=f"Role permissions updated successfully.",
        data=data,
    )
    
@router.get(
    "/role-permission/",
    response={200: APIResponse, 403: APIResponse},
)
def get_role_permission(request, page: int = 1, page_size: int = 20):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    org = _authority(request, "view_roles")
    roles = Role.objects.prefetch_related("roles_permission__permission").filter(organization= org)
    data = []
    for role in roles:
        data.append(
            {
                "id": role.id,
                "name": role.name,
                "permission":[
                    {
                        "id":perm.permission.id,
                        "code": perm.permission.code,
                        "name":perm.permission.name,
                        "module": perm.permission.module,
                    }
                    for perm in role.roles_permission.all()
                ]
            }
        )
        
    return 200, _paged_rows(
        data, page, page_size, lambda row: row, "role permission fetch successfully"
    )
