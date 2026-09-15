"""Cookie credentials tied to revocable sessions and a fixed client channel."""
import secrets
from datetime import timedelta

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone

from common.access import channel_access, organization_for
from common.audit import security_event
from contract.codes import ErrorCode
from contract.exceptions import ContractError
from .helper import get_app_type, get_cookie_domain
from .models import RefreshSession, User
from .utils.jwt_utils import create_access_token, create_refresh_token, decode_token
from .utils.token_hash import hash_token


def active_account(user):
    if not user.is_active or user.account_status in {"deactivated", "Suspended", "Deleted"}:
        raise ContractError(403, ErrorCode.ACCOUNT_DEACTIVATED, "Your account is currently deactivated.")
    if user.account_status != "active":
        raise ContractError(403, ErrorCode.PERMISSION_DENIED, "This account is not active.")


def request_channel(request):
    channel = request.headers.get("X-App-Channel", "web").lower()
    if channel not in {"web", "mobile"}:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "X-App-Channel must be web or mobile.")
    return channel


def check_channel(user, channel, identity_only=False):
    access = channel_access(user, organization_for(user))
    if identity_only and not any(access.values()):
        return
    if not access.get(channel):
        raise ContractError(403, ErrorCode.CHANNEL_ACCESS_DENIED, "This account cannot access this channel.")


def authenticate_request(request):
    token = request.COOKIES.get(f"{get_app_type(request)}_access_token")
    if not token:
        raise ContractError(401, ErrorCode.AUTHENTICATION_REQUIRED, "Authentication is required.")
    try:
        payload = decode_token(token)
        if payload.get("kind") != "access":
            raise ValueError()
        session = RefreshSession.objects.select_related("user").get(id=payload["sid"], user_id=payload["sub"])
    except Exception:
        raise ContractError(401, ErrorCode.SESSION_EXPIRED, "Session has expired. Please sign in again.")
    user = session.user
    active_account(user)
    if not session.is_active or session.expires_at <= timezone.now():
        raise ContractError(401, ErrorCode.AUTHENTICATION_REQUIRED, "This session has ended.")
    if request_channel(request) != session.channel:
        raise ContractError(403, ErrorCode.CHANNEL_ACCESS_DENIED, "Session channel does not match the request.")
    identity_only = request.path in {
        "/api/v2/users/me/", "/api/v2/users/me/capabilities/", "/api/v2/users/me/avatar/", "/api/auth/signout", "/api/auth/profile",
    }
    check_channel(user, session.channel, identity_only)
    request.auth_session = session
    request.domain_user = user
    return user


def session_response(request, user, session, body):
    claims = {"sub": str(user.id), "sid": session.pk}
    refresh = create_refresh_token({**claims, "kind": "refresh", "jti": secrets.token_urlsafe(24)})
    access = create_access_token({**claims, "kind": "access"})
    session.token_hash = hash_token(refresh)
    session.expires_at = timezone.now() + timedelta(days=7)
    session.save(update_fields=["token_hash", "expires_at"])
    response = JsonResponse(body)
    prefix = get_app_type(request)
    common = dict(secure=True, samesite="None", domain=get_cookie_domain(request))
    response.set_cookie(f"{prefix}_access_token", access, httponly=True, path="/", max_age=900, **common)
    response.set_cookie(f"{prefix}_refresh_token", refresh, httponly=True, path="/api/auth/refresh-token", max_age=604800, **common)
    response.set_cookie(f"{prefix}_csrf_token", secrets.token_urlsafe(32), httponly=False, path="/", max_age=900, **common)
    return response


def login_session(request, user):
    channel = request_channel(request)
    active_account(user)
    check_channel(user, channel, identity_only=True)
    with transaction.atomic():
        session = RefreshSession.objects.create(
            user=user, token_hash=secrets.token_hex(32), channel=channel,
            expires_at=timezone.now() + timedelta(days=7),
            user_agent=request.headers.get("User-Agent", ""), ip_address=request.META.get("REMOTE_ADDR"),
        )
        response = session_response(request, user, session, {"status": "Success", "message": "Login successful", "is_admin": user.is_superuser})
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        security_event("USER_LOGGED_IN", user, target=user, org=organization_for(user))
    return response


def renew_session(request):
    token = request.COOKIES.get(f"{get_app_type(request)}_refresh_token")
    try:
        payload = decode_token(token)
        if payload.get("kind") != "refresh":
            raise ValueError()
    except Exception:
        raise ContractError(401, ErrorCode.SESSION_EXPIRED, "Refresh session has expired.")
    with transaction.atomic():
        # Serialize with deactivation and competing refresh requests.
        user = User.objects.select_for_update().filter(id=payload.get("sub")).first()
        if user is None:
            raise ContractError(401, ErrorCode.SESSION_EXPIRED, "Refresh session has expired.")
        active_account(user)
        session = RefreshSession.objects.select_for_update().filter(
            id=payload.get("sid"), user=user, token_hash=hash_token(token), is_active=True,
            expires_at__gt=timezone.now(),
        ).first()
        if session is None:
            raise ContractError(401, ErrorCode.SESSION_EXPIRED, "Refresh session has expired.")
        if request_channel(request) != session.channel:
            raise ContractError(403, ErrorCode.CHANNEL_ACCESS_DENIED, "Session channel does not match the request.")
        check_channel(user, session.channel, identity_only=True)
        return session_response(request, user, session, {"message": "Token refreshed"})


def logout_session(request):
    import jwt
    from django.conf import settings
    token = request.COOKIES.get(f"{get_app_type(request)}_access_token")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
        if payload.get("kind") != "access":
            raise ValueError()
    except Exception:
        raise ContractError(401, ErrorCode.AUTHENTICATION_REQUIRED, "Authentication is required.")
    with transaction.atomic():
        session = RefreshSession.objects.select_for_update().filter(id=payload.get("sid"), user_id=payload.get("sub")).first()
        if session and session.is_active:
            session.is_active = False
            session.save(update_fields=["is_active"])
            security_event("USER_LOGGED_OUT", session.user, target=session.user, org=organization_for(session.user))
    response = JsonResponse({"success": True, "message": "Logged out successfully"})
    for suffix, path in (("access_token", "/"), ("csrf_token", "/"), ("refresh_token", "/api/auth/refresh-token")):
        response.delete_cookie(f"{get_app_type(request)}_{suffix}", path=path, domain=get_cookie_domain(request), samesite="None")
    return response
