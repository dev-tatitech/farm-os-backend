from ninja import NinjaAPI
from django.http import HttpRequest
from .auth import get_current_user, validate_crftoken
from .models import (
    User as users, User, 
    EmailValidation,
    RefreshSession
)
from ninja.files import UploadedFile
from ninja import File
from ninja import Router, Query
from django.contrib.auth.hashers import make_password, check_password
from django.http import JsonResponse
from typing import List
from django.db.models import Count, Q, F, FloatField, ExpressionWrapper, Max
import random
from ninja.errors import HttpError
from pydantic import EmailStr
from .utils.token_hash import hash_token
from django.utils.timezone import now
from .utils.store_session import store_refresh_session
from django.db.models import Q
from uuid import UUID
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
from django.db.models.functions import TruncDate
import calendar
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
import json
import os
import hashlib
from common.utils import format_datetime
from datetime import datetime
from .helper import generate_unique_username, email_sender, send_account_otp_email, get_cookie_domain, get_app_type, save_uploaded_file
from .utils.jwt_utils import create_access_token, create_refresh_token, decode_token
from .utils.csrf import generate_csrf_token
from django.utils.crypto import get_random_string
from .schema import (
    NewAccountSchema,
    ErrorResponse,
    Error_out,
    LoginSchema,
    APIResponse,
    EmailValidationSchema,
    ResendOtpSchema,
     RegionListResponse,
    StateListResponse,
    AccountInfoSchema,
    LGAListResponse,
   AccountInfoUpdate,
   NextOfKinSchema,
   BusinessProfileSchema
)

router = Router(tags=[" Authentication"])

@router.post(
    "/new-account",
    auth=None,
   
    response={403: ErrorResponse, 200: APIResponse, 400: APIResponse},
)
def create_account(request, data: NewAccountSchema):

    try:
        validate_password(data.password)
    except ValidationError as e:
        return 400, APIResponse(
            success=True,
            message="Password validation failed",
            data={"errors": e.messages},
        )

    if data.password != data.confirm_password:
        return 400, APIResponse(
            success=False, message="Passwords do not match", data=None
        )

    if User.objects.filter(email=data.email).exists():
        return 400, APIResponse(
            success=False, message="Email already exists.", data=None
        )
    username = generate_unique_username()
    user = User.objects.create(
        username=username, 
        password=make_password(data.password), 
        email=data.email
    )
    send_account_otp_email(user,data.email)
    response = JsonResponse(
                {
                    "success": True,
                    "message": "Account created successfully",
                }
            )
    response.set_cookie(
                key="email",
                value=data.email,
                httponly=True,
                secure=True,
                samesite="None",
                path="/",
                max_age=604800,
            )
    return response


@router.post("/email-validate",response={200: APIResponse},)
def email_validations(request, payload: EmailValidationSchema):
    email = request.COOKIES.get("email")
    #raise HttpError(200, f"is testing cookies {email}")
    try:
        otp=payload.otp.strip()  
        otp_record = EmailValidation.objects.get(
            email=email,
            code=otp,
            is_used=False,
            expires_at__gte=datetime.now(),
        )
    except EmailValidation.DoesNotExist:
        return JsonResponse({"detail": "Invalid OTP or Email"}, status=400)

    # Mark OTP as used
    otp_record.is_used = True
    otp_record.save()
    return 200,APIResponse(
        success=True,
        message="Your email has been successfully verified.",
        data=None
    )



@router.post(
    "/login", response={401: Error_out}, auth=None, 
)
def login(request, data: LoginSchema):
    try:
        user = users.objects.get(email=data.email)
    except users.DoesNotExist:
        return 401, Error_out(status="Error", message="Invalid credentials")

    is_admin = user.is_superuser
    if not check_password(data.password, user.password):
        return 401, Error_out(status="Error", message="Invalid credentials")
    
    if not is_admin:
        try:
            otp_record = EmailValidation.objects.get(
                email=user.email,
                is_used=True,
            )
        except EmailValidation.DoesNotExist:
            return JsonResponse({"detail": "Please verify your email"}, status=400)

    domain = get_cookie_domain(request)
    app_type = get_app_type(request)
    ACCESS_COOKIE = f"{app_type}_access_token"
    REFRESH_COOKIE = f"{app_type}_refresh_token"
    CSRF_COOKIE = f"{app_type}_csrf_token"
    # ---------- 4. Enforce domain ↔ role ----------
    if app_type == "admin" and not is_admin:
        raise HttpError(403, "Admins only")

    if app_type == "client" and is_admin:
        raise HttpError(403, f"client only {domain} my domain")
    # Generate tokens
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    csrf_token = generate_csrf_token()  # just a random string
    RefreshSession.objects.filter(user=user, is_active=True).update(is_active=False)
    store_refresh_session(user, refresh_token, request)

    # update csrftoken
    user.csrf_token = csrf_token
    user.save()
    # Prepare response
    response = JsonResponse(
        {"status": "Success",
         "message": f"Login successful", 
         "is_admin": is_admin,
         
         }
    )

    # Access token cookie
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=access_token,
        httponly=True,
        secure=True,
        samesite="None",
        domain=domain,
        path="/",
        max_age=900,  # 15 minutes
    )

    # Refresh token cookie
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="None",
        domain=domain,
        path="/api/auth/refresh-token",
        max_age=7 * 24 * 60 * 60,  # 7 days
    )

    # CSRF token (readable by JavaScript)
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        httponly=False,
        secure=True,
        samesite="None",
        domain=domain,
        path="/",
        max_age=900,  # Match access token lifespan
    )

    return response

@router.post("/resend_otp",response={200: APIResponse},)
def resend_otp(request, payload: ResendOtpSchema):

    try:
        otp_record = EmailValidation.objects.get(
            email=payload.email,
            is_used=False,
        )
    except EmailValidation.DoesNotExist:
        return JsonResponse({"detail": "Invalid Email"}, status=400)
    try:
        user = users.objects.get(email=payload.email)
    except users.DoesNotExist:
        return 401, Error_out(status="Error", message="Invalid credentials")

    email_sender(user,payload.email)
    response = JsonResponse(
                {
                    "success": True,
                    "message": "The OTP has been resent to your email.",
                }
            )
    response.set_cookie(
                key="email",
                value=payload.email,
                httponly=True,
                secure=True,
                samesite="None",
                path="/",
                max_age=604800,
            )
    return response


@router.post("/refresh-token")
def refresh_token(request):
    domain = get_cookie_domain(request)
    app_type = get_app_type(request)
    ACCESS_COOKIE = f"{app_type}_access_token"
    REFRESH_COOKIE = f"{app_type}_refresh_token"
    CSRF_COOKIE = f"{app_type}_csrf_token"
    
    token = request.COOKIES.get(REFRESH_COOKIE)

    if not token:
        raise HttpError(401, f"No refresh token token{token}")

    try:
        payload = decode_token(token)
    except Exception:
        raise HttpError(401, "Invalid refresh token")
    
    new_access = create_access_token({"sub": payload["sub"]})
    csrf_token = generate_csrf_token()
    new_refresh = create_refresh_token({"sub": payload["sub"]})
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    token_hash = hash_token(token)

    try:
        session = RefreshSession.objects.select_related("user").get(
            token_hash=token_hash, is_active=True
        )
    except RefreshSession.DoesNotExist:
        raise HttpError(401, f"Token reuse or invalid session")
    if session.expires_at < now():
        raise HttpError(401, "Refresh token expired")

    # Invalidate old session
    session.is_active = False
    session.save()

    user = session.user
    user.csrf_token = csrf_token
    user.save()
    # Save new session
    domain = get_cookie_domain(request)
    store_refresh_session(session.user, new_refresh, request)
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>.
    response = JsonResponse({"message": f"Token refreshed"})
    response.set_cookie(
        REFRESH_COOKIE,
        new_refresh,
        httponly=True,
        secure=True,
        samesite="None",
        domain=domain,
        path="/api/auth/refresh-token",
        max_age=604800,
    )

    response.set_cookie(
        ACCESS_COOKIE,
        new_access,
        httponly=True,
        secure=True,
        samesite="None",
        domain=domain,
        path="/",
    )

    response.set_cookie(
        CSRF_COOKIE, csrf_token,
        httponly=False, 
        secure=True, 
        samesite="None",
        domain=domain,
        path="/"
    )

    return response



@router.post("/signout")
def signout(request):
    # Get refresh token from cookie
    token = request.COOKIES.get("refresh_token")
    user_id = get_current_user(request)
    if user_id:

        try:
            session = RefreshSession.objects.get(user_id=user_id, is_active=True)
            session.is_active = False
            session.save()

        except RefreshSession.DoesNotExist:
            pass
    response = JsonResponse({"message": f"Signed out successfully"})

    # Delete refresh token cookie by setting it to expired
    response.delete_cookie("refresh_token", path="/")  # match your cookie path

    # Also delete access token cookie
    response.delete_cookie("access_token", path="/")

    # Delete CSRF token cookie if applicable
    response.delete_cookie("csrf_token", path="/")

    return response

@router.get(
    "/profile",
    response={200: APIResponse},
)
def profile(request):
    user_id = get_current_user(request)
    user = get_object_or_404(User, pk=user_id)

    data = {
        "email": user.email,
        "is_admin": user.is_superuser,
 
    }
    return 200, APIResponse(success=True, message=f"user details", data=data)

@router.get("/timezone")
def timezone(request):
    user_id = get_current_user(request)
    user = get_object_or_404(User, pk=user_id)

    naija = format_datetime(user.created_at, "Africa/Lagos")
    us = format_datetime(user.created_at, "America/New_York")
    data ={
       "naija": naija,
        "us": us,
       
    }
    return JsonResponse(
        {
            "test":"this is test",
            "data":data
        }
    )