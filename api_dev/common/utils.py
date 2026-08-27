from zoneinfo import ZoneInfo
from django.utils import timezone
from datetime import timedelta
from dateutil.relativedelta import relativedelta
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

def resolve_trend_start(model_qs, date_field, nominal_start, end_date):
    """
    Clamp a trend window's start to the earliest record actually present in
    `model_qs`, so dashboard trend charts don't render empty leading buckets
    for farms/records younger than the nominal lookback window (e.g. a farm
    created this month showing 11 empty months before it in a "last 12
    months" chart). Never returns a start later than `end_date`, and falls
    back to `nominal_start` when there is no data at all.
    """
    from django.db.models import Min

    earliest = model_qs.aggregate(_earliest=Min(date_field))["_earliest"]
    if earliest is None:
        return nominal_start
    if hasattr(earliest, "date"):
        earliest = earliest.date()
    start = max(nominal_start, earliest)
    return min(start, end_date)


def daily_trend_range(start_date, end_date):
    """Inclusive list of dates from start_date to end_date."""
    if end_date < start_date:
        return []
    return [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]


def monthly_trend_range(start_month, end_month):
    """Inclusive list of month-start dates from start_month to end_month (both day=1)."""
    months = []
    cursor = start_month
    while cursor <= end_month:
        months.append(cursor)
        cursor = cursor + relativedelta(months=1)
    return months


def generate_strong_password(length=12):
    """
    Generate a strong random password.
    Default length is 12 characters.
    """
    allowed_chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+-=[]{}|;:,.<>?'
    from django.utils.crypto import get_random_string

    return get_random_string(length, allowed_chars)