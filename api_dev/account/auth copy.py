import jwt, datetime
from django.conf import settings
from ninja.security import HttpBearer, APIKeyCookie
from ninja.security import HttpBearer
import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from .utils.jwt_utils import decode_token
from ninja.errors import HttpError
from .helper import get_app_type
User = get_user_model()

SECRET_KEY = settings.SECRET_KEY

def get_current_user(request):
    app_type = get_app_type(request)
    ACCESS_COOKIE = f"{app_type}_access_token"
    REFRESH_COOKIE = f"{app_type}_refresh_token"
    CSRF_COOKIE = f"{app_type}_csrf_token"
    access_token = request.COOKIES.get(ACCESS_COOKIE)
    csrf_cookie = request.COOKIES.get(CSRF_COOKIE)
    csrf_header = request.headers.get("X-CSRFToken")

    if not access_token:
        raise HttpError(401, "No access token")

    try:
        payload = decode_token(access_token)
    except Exception:
        raise HttpError(401, "Invalid or expired access token")

    return payload["sub"]


def validate_crftoken(request, csrf_header):
    csrf_cookie = request.COOKIES.get("csrf_token")

    # CSRF protection (only for unsafe methods)
    if request.method not in ["GET", "HEAD", "OPTIONS"]:
        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            raise HttpError(403, f"CSRF token mismatch ")

    return True
