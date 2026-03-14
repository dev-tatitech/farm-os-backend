from datetime import timedelta
from django.utils import timezone
from ..models import RefreshSession
from ..utils.token_hash import hash_token


def store_refresh_session(user, refresh_token, request):
    token_hash = hash_token(refresh_token)
    expires_at = timezone.now() + timedelta(days=7)  # or match your token expiry

    RefreshSession.objects.create(
        user=user,
        token_hash=token_hash,
        user_agent=request.headers.get("User-Agent", ""),
        ip_address=request.META.get("REMOTE_ADDR"),
        expires_at=expires_at,
    )
