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
