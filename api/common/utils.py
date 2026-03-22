from zoneinfo import ZoneInfo
from django.utils import timezone
import uuid
def format_datetime(dt, tz_name="UTC", fmt="%Y-%m-%d %H:%M:%S"):

    if dt is None:
        return None

    # Make naive datetime timezone-aware (assume UTC if naive)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone=timezone.utc)

    # Convert to user's timezone
    user_tz = ZoneInfo(tz_name)
    local_dt = timezone.localtime(dt, user_tz)

    # Format as string
    return local_dt.strftime(fmt)

def generate_ref():
    return f"{uuid.uuid4().int % 10**15:015d}"

def generate_strong_password(length=12):
    """
    Generate a strong random password.
    Default length is 12 characters.
    """
    allowed_chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+-=[]{}|;:,.<>?'
    from django.utils.crypto import get_random_string

    return get_random_string(length, allowed_chars)