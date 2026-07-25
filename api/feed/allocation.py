from decimal import Decimal
from django.core.exceptions import ValidationError

# Relative feed-share weighting by life stage, used only by the
# "life_stage_based" allocation method. Deliberately modest defaults (not a
# universal biological truth) — farms needing precision should use
# "weight_based" or "manual"/"consumption_based" instead.
_LIFE_STAGE_WEIGHTS = {
    "Newborn": Decimal("0.3"), "Suckling": Decimal("0.5"), "Weaned": Decimal("0.7"),
    "Juvenile": Decimal("0.8"), "Grower": Decimal("1.0"), "Mature": Decimal("1.2"),
    "Breeding Eligible": Decimal("1.2"), "Senior": Decimal("0.9"),
}
_DEFAULT_LIFE_STAGE_WEIGHT = Decimal("1.0")


def _active_group_members(group):
    return [m.animal for m in group.members.filter(status="ACTIVE").select_related("animal")]


def compute_group_allocation(group, method, total_quantity, total_cost, manual_entries=None):
    """
    Returns a list of (animal, allocated_quantity, allocated_cost) for every
    active member of `group`, using the requested method. Never silently
    defaults to equal split for consumption_based/manual — those require
    explicit per-animal entries, per spec 4.4 ("must not divide every group
    feed cost equally by default").
    """
    animals = _active_group_members(group)
    if not animals:
        return []

    total_quantity = Decimal(str(total_quantity))
    total_cost = Decimal(str(total_cost))

    if method in ("manual", "consumption_based"):
        if not manual_entries:
            raise ValidationError(f"'{method}' allocation requires explicit per-animal quantities.")
        entries_by_animal = {e["animal_id"]: Decimal(str(e["quantity"])) for e in manual_entries}
        entry_total = sum(entries_by_animal.values())
        if entry_total <= 0:
            raise ValidationError("Manual allocation quantities must sum to more than zero.")
        result = []
        for animal in animals:
            qty = entries_by_animal.get(animal.id)
            if qty is None:
                continue
            share = qty / entry_total
            result.append((animal, qty, (total_cost * share).quantize(Decimal("0.01"))))
        return result

    if method == "weight_based":
        weights = {}
        for animal in animals:
            latest = animal.weights.order_by("-date").first()
            weights[animal.id] = Decimal(str(latest.weight)) if latest else Decimal("1.0")
    elif method == "life_stage_based":
        weights = {
            animal.id: _LIFE_STAGE_WEIGHTS.get(animal.current_life_stage, _DEFAULT_LIFE_STAGE_WEIGHT)
            for animal in animals
        }
    else:  # "equal"
        weights = {animal.id: Decimal("1.0") for animal in animals}

    total_weight = sum(weights.values()) or Decimal("1.0")
    result = []
    for animal in animals:
        share = weights[animal.id] / total_weight
        qty = (total_quantity * share).quantize(Decimal("0.01"))
        cost = (total_cost * share).quantize(Decimal("0.01"))
        result.append((animal, qty, cost))
    return result


def post_feed_issuance_cost(issuance):
    """
    Turns a saved FeedIssuanceRecord's cost into Finance transactions (and,
    for a group issuance, a per-animal FeedCostAllocation audit trail split
    per the record's allocation_method). Timeline events are posted by the
    calling endpoint, same as before this existed — not duplicated here.
    """
    from finance.services import record_transaction
    from .models import FeedCostAllocation

    if issuance.target_type == "animal":
        record_transaction(
            farm=issuance.farm, type="expense", category_name="Feed", amount=issuance.cost,
            transaction_date=issuance.issue_date, source_module="feed_issuance", source_id=issuance.id,
            animal=issuance.animal, created_by=issuance.issued_by,
        )
        return

    manual_entries = getattr(issuance, "_manual_allocations", None)
    allocations = compute_group_allocation(
        issuance.group, issuance.allocation_method, issuance.quantity_issued, issuance.cost,
        manual_entries=manual_entries,
    )
    for animal, qty, cost in allocations:
        FeedCostAllocation.objects.create(
            feed_issuance=issuance, animal=animal, allocated_quantity=qty, allocated_cost=cost,
        )
        if cost > 0:
            record_transaction(
                farm=issuance.farm, type="expense", category_name="Feed", amount=cost,
                transaction_date=issuance.issue_date, source_module="feed_issuance", source_id=issuance.id,
                animal=animal, created_by=issuance.issued_by,
                description=f"Group feed allocation ({issuance.allocation_method}) via group {issuance.group_id}",
            )
