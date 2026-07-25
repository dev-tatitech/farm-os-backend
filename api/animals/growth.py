def weight_history(animal, limit=None):
    qs = animal.weights.order_by("-date")
    return list(qs[:limit]) if limit else list(qs)


def weight_gain(animal):
    """Gain between the two most recent weight records, or None if fewer than 2 exist."""
    recent = weight_history(animal, limit=2)
    if len(recent) < 2:
        return None
    latest, previous = recent
    return latest.weight - previous.weight


def average_daily_gain(animal):
    """ADG = weight gain / days elapsed between the two most recent records."""
    recent = weight_history(animal, limit=2)
    if len(recent) < 2:
        return None
    latest, previous = recent
    days = (latest.date - previous.date).days
    if days <= 0:
        return None
    return (latest.weight - previous.weight) / days


def percentage_weight_change(animal):
    recent = weight_history(animal, limit=2)
    if len(recent) < 2:
        return None
    latest, previous = recent
    if previous.weight == 0:
        return None
    return (latest.weight - previous.weight) / previous.weight * 100


def weight_trend(animal, limit=12):
    """Chronological (oldest-first) list of {date, weight} for charting."""
    recent = weight_history(animal, limit=limit)
    return [{"date": w.date, "weight": w.weight} for w in reversed(recent)]


def cost_per_kg_gained(animal):
    """
    Total recorded cost-to-date divided by total weight gained since the
    first weight record. Returns None if there isn't enough data to compute
    a meaningful figure (fewer than 2 weight records, or zero/negative gain).
    """
    from django.db.models import Sum
    from finance.models import Transaction

    history = weight_history(animal)
    if len(history) < 2:
        return None
    first, latest = history[-1], history[0]
    total_gain = latest.weight - first.weight
    if total_gain <= 0:
        return None

    total_cost = (
        Transaction.objects.filter(animal=animal, type="expense")
        .aggregate(total=Sum("amount"))["total"]
        or 0
    )
    if not total_cost:
        return None
    return float(total_cost) / total_gain
