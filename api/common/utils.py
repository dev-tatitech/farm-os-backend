from zoneinfo import ZoneInfo
from django.utils import timezone

def format_datetime(dt, tz_name="UTC", fmt="%Y-%m-%d %H:%M:%S"):
    """
    Convert a timezone-aware or naive datetime to the given timezone
    and return it as a formatted string.

    Args:
        dt (datetime): The datetime to convert
        tz_name (str): IANA timezone string, e.g. "Africa/Lagos"
        fmt (str): Python strftime format

    Returns:
        str: formatted datetime string in the user's timezone
    """
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