from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum, Q
from django.utils import timezone


def _monthly_equivalent(sub):
    if sub.billing_cycle == "annual":
        return (sub.price or Decimal("0")) / Decimal("12")
    return sub.price or Decimal("0")


def get_platform_stats():
    """
    Every figure here is computed live from the real tables — no placeholder
    or mocked numbers. Sections with no backing data (support tickets,
    affiliate tracking, etc.) are intentionally left out rather than faked.
    """
    from organization.models import Organization, Farm
    from subcriptions.models import Subscription, SubscriptionPlan, Payment
    from account.models import User
    from common.models import AuditLog

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    orgs = Organization.objects.all()
    total_orgs = orgs.count()
    orgs_this_week = orgs.filter(created_at__gte=week_start).count()

    farms = Farm.objects.all()
    total_farms = farms.count()
    farms_this_month = farms.filter(created_at__gte=month_start).count()

    active_subs_qs = Subscription.objects.filter(status="active").select_related("plan")
    active_subs = list(active_subs_qs)
    total_active_subs = len(active_subs)
    trial_subs = sum(1 for s in active_subs if "trial" in (s.plan.name or "").lower())
    paid_active_subs = total_active_subs - trial_subs

    mrr = sum((_monthly_equivalent(s) for s in active_subs), Decimal("0"))
    arr = mrr * 12

    payments_success = Payment.objects.filter(status="success")
    revenue_today = payments_success.filter(paid_at__gte=today_start).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    revenue_week = payments_success.filter(paid_at__gte=week_start).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    revenue_month = payments_success.filter(paid_at__gte=month_start).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    revenue_year = payments_success.filter(paid_at__gte=now - timedelta(days=365)).aggregate(t=Sum("amount"))["t"] or Decimal("0")

    pending_payments = Payment.objects.filter(status="pending").count()

    total_users = User.objects.count()
    recent_audit_events = AuditLog.objects.filter(created_at__gte=week_start).count()

    plan_distribution = list(
        active_subs_qs.values("plan__name").annotate(count=Count("id")).order_by("-count")
    )

    status_breakdown = list(
        Subscription.objects.values("status").annotate(count=Count("id")).order_by("-count")
    )
    total_subs_ever = Subscription.objects.count()
    cancelled_subs = Subscription.objects.filter(status="cancelled").count()
    churn_rate = round((cancelled_subs / total_subs_ever) * 100, 1) if total_subs_ever else 0.0
    autorenew_rate = (
        round((sum(1 for s in active_subs if s.auto_renew) / total_active_subs) * 100, 1)
        if total_active_subs else 0.0
    )

    ended_subs = Subscription.objects.filter(end_date__isnull=False)
    avg_length_days = None
    if ended_subs.exists():
        total_days = sum(
            (s.end_date - s.start_date).days for s in ended_subs if s.end_date and s.start_date
        )
        count = ended_subs.count()
        avg_length_days = round(total_days / count) if count else None

    weekly_revenue = []
    for i in range(3, -1, -1):
        w_end = now - timedelta(days=7 * i)
        w_start = w_end - timedelta(days=7)
        total = payments_success.filter(paid_at__gte=w_start, paid_at__lt=w_end).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        weekly_revenue.append({"label": f"Week {4 - i}", "amount": float(total)})

    new_subs_by_week = []
    for i in range(3, -1, -1):
        w_end = now - timedelta(days=7 * i)
        w_start = w_end - timedelta(days=7)
        count = Subscription.objects.filter(start_date__gte=w_start, start_date__lt=w_end).count()
        new_subs_by_week.append({"label": f"Week {4 - i}", "count": count})

    return {
        "total_orgs": total_orgs,
        "orgs_this_week": orgs_this_week,
        "total_farms": total_farms,
        "farms_this_month": farms_this_month,
        "total_active_subs": total_active_subs,
        "trial_subs": trial_subs,
        "paid_active_subs": paid_active_subs,
        "mrr": mrr,
        "arr": arr,
        "revenue_today": revenue_today,
        "revenue_week": revenue_week,
        "revenue_month": revenue_month,
        "revenue_year": revenue_year,
        "pending_payments": pending_payments,
        "total_users": total_users,
        "recent_audit_events": recent_audit_events,
        "plan_distribution": plan_distribution,
        "status_breakdown": status_breakdown,
        "churn_rate": churn_rate,
        "autorenew_rate": autorenew_rate,
        "avg_length_days": avg_length_days,
        "weekly_revenue": weekly_revenue,
        "new_subs_by_week": new_subs_by_week,
        "has_payment_data": Payment.objects.exists(),
    }
