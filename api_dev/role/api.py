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
router = Router(tags=["User and Role management"])
@router.get(
    "/permission/",
    response={200: APIResponse, 403: APIResponse},
)
def get_permission(request):
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
    normalized = " ".join(payload.name.split()).casefold()
    if Role.objects.filter(normalized_name=normalized, organization=org).exists():
        raise HttpError(409, "Role name must be unique within this organization.")
    code = f"RL-{generate_ref()}"
    role = Role.objects.create(
        organization = org,
        name = " ".join(payload.name.split()),
        normalized_name = normalized,
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
    
@router.get(
    "/role/",
    response={200: APIResponse, 403: APIResponse},
)
def get_role(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    org = get_object_or_404(Organization, user = user)
    plans = Role.objects.filter(organization = org)
    data = [
        {
         "id": plan.id,
         "code": plan.code  ,
         "name": plan.name  ,   
          "description": plan.description  ,   
        }
        for plan in plans
    ]
    return 200, APIResponse(
        success=True, message="Role fetch successfully", data=data
    )

@router.patch(
    "/role/",
    response={200: APIResponse, 403: APIResponse},
)
def update_role(request, payload:RoleUpdateSchema):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    role = get_object_or_404(Role, id = payload.role_id)
    if payload.name:
        normalized = " ".join(payload.name.split()).casefold()
        if Role.objects.filter(
            organization=role.organization,
            normalized_name=normalized,
        ).exclude(id=role.id).exists():
            raise HttpError(409, "Role name must be unique within this organization.")
        role.name = " ".join(payload.name.split())
        role.normalized_name = normalized
    if payload.description:
        role.description = payload.description
    role.save()
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
def delete_role(request, role_id: int):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        return 403, APIResponse(success=False, message="Permission denied", data=None)
    role = get_object_or_404(Role, id = role_id)
    role.delete()
    return 200, APIResponse(
        success=True, message="Role deleted successfully", data=None
    )
    

@router.post(
    "/user/",
    response={200: APIResponse, 403: APIResponse},
)
def add_user(request, payload: NewUserIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    
    if User.objects.filter(email=payload.email).exists():
       raise HttpError(400, "Email already exists.")
    org = get_object_or_404(Organization, user = user)

    username = generate_unique_username()
    password = generate_strong_password()
    client = User.objects.create(
        username=username, 
        password=make_password(password), 
        email=payload.email,
        organization = org,
        account_status = "invited"
    )
    send_sub_account_otp_email(client,client.email)
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
def get_user(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    org = get_object_or_404(Organization, user = user)
    all_user = User.objects.filter(organization =org)
    data = [
        {
        "id": user.id,
        "email": user.email
    }
        for user in all_user
    ]
    return 200,APIResponse(
        success=True,
        message="user fetch successfully",
        data=data
    )
    
@router.post(
    "/user-role/",
    response={200: APIResponse},
)
def assign_user_role(request, payload: NewUserRoleIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    org = get_object_or_404(Organization, user = user)
    my_user = get_object_or_404(User, organization= org, id = payload.user_id)
    role = get_object_or_404(Role, organization = org, id =payload.role_id)
    farm = get_object_or_404(Farm, organization = org, id = payload.farm_id)
    if my_user.id == org.user_id:
        raise HttpError(403, "Organization ownership cannot be replaced by a role assignment.")
    if UserRole.objects.filter(
        user = my_user,
        role = role,
        farm = farm,
        status="active",
        ).exists():
       raise HttpError(400, "Role already exists.")
    user_role = UserRole.objects.create(
        user = my_user,
        role = role,
        farm = farm,
        assigned_by = user
    )
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
def update_user_role(request, assignment_id: int, payload: UserRolePatchIn):
    actor_id = get_current_user(request)
    actor = get_object_or_404(User, id=actor_id)
    org = get_object_or_404(Organization, user=actor)
    assignment = get_object_or_404(
        UserRole.objects.select_related("user", "role", "farm"),
        id=assignment_id,
        farm__organization=org,
        status="active",
    )
    if assignment.user_id == org.user_id:
        raise HttpError(403, "Organization owner assignments cannot be changed.")
    if payload.farm_id is not None:
        assignment.farm = get_object_or_404(Farm, id=payload.farm_id, organization=org)
    if payload.role_id is not None:
        assignment.role = get_object_or_404(Role, id=payload.role_id, organization=org)
    if payload.farm_id is None and payload.role_id is None:
        raise HttpError(422, "farm_id or role_id is required.")
    assignment.save(update_fields=["farm", "role"])
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
def revoke_user_role(request, assignment_id: int):
    actor_id = get_current_user(request)
    actor = get_object_or_404(User, id=actor_id)
    org = get_object_or_404(Organization, user=actor)
    assignment = get_object_or_404(
        UserRole.objects.select_related("user", "farm"),
        id=assignment_id,
        farm__organization=org,
    )
    if assignment.status == "revoked":
        raise HttpError(409, "Assignment already revoked.")
    if assignment.user_id == org.user_id:
        raise HttpError(403, "Organization owner access cannot be revoked.")
    assignment.status = "revoked"
    assignment.revoked_at = timezone.now()
    assignment.revoked_by = actor
    assignment.save(update_fields=["status", "revoked_at", "revoked_by"])
    return 200, APIResponse(
        success=True,
        message="Farm assignment removed successfully.",
        data={"assignment_id": assignment.id, "status": assignment.status},
    )
    
@router.get("/user-role/", response={200: APIResponse, 403: APIResponse})
def get_user_role(request):
    user_id = get_current_user(request)

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        raise HttpError(403, "Permission denied")

    org = get_object_or_404(Organization, user=user)
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

    return 200, APIResponse(
        success=True,
        message="User roles fetched successfully",
        data=data
    )
@router.post(
    "/role-permission/",
    response={200: APIResponse},
)
def assign_role_permission(request, payload: RolePermissionIn):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    org = get_object_or_404(Organization, user=user)
    role = get_object_or_404(Role, organization=org, id=payload.role_id)

    permissions = Permission.objects.filter(id__in=payload.permission_ids)
    found_ids = set(permissions.values_list("id", flat=True))
    missing = set(payload.permission_ids) - found_ids
    if missing:
        raise HttpError(404, f"Permission(s) not found: {sorted(missing)}")

    with db_transaction.atomic():
        RolePermission.objects.filter(role=role).delete()
        RolePermission.objects.bulk_create(
            [RolePermission(role=role, permission=p) for p in permissions]
        )
    authoritative_ids = list(
        RolePermission.objects.filter(role=role)
        .order_by("permission_id")
        .values_list("permission_id", flat=True)
    )
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
def get_role_permission(request):
    user_id = get_current_user(request)
    try:
        user = users.objects.get(Q(id=user_id))
    except users.DoesNotExist:
        raise HttpError(400, "Permission denied")
    org = get_object_or_404(Organization, user = user)
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
        
    return 200,APIResponse(
        success=True,
        message="role permission fetch successfully",
        data=data
    )