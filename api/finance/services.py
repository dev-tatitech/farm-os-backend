from .models import Transaction, TransactionCategory, AnimalFinancialProfile

DEFAULT_CATEGORIES = [
    # expense
    ("Acquisition", "expense"),
    ("Feed", "expense"),
    ("Treatment", "expense"),
    ("Veterinary Service", "expense"),
    ("Breeding", "expense"),
    ("Labour", "expense"),
    ("Transportation", "expense"),
    ("Other Direct Cost", "expense"),
    # income
    ("Milk Sales", "income"),
    ("Offspring Sales", "income"),
    ("Wool or Fibre Sales", "income"),
    ("Manure Sales", "income"),
    ("Breeding Service Income", "income"),
    ("Prize or Exhibition Income", "income"),
    ("Animal Sale Income", "income"),
    ("Other Production Income", "income"),
]


def seed_transaction_categories():
    created = 0
    for name, type_ in DEFAULT_CATEGORIES:
        _, was_created = TransactionCategory.objects.get_or_create(
            name=name, type=type_, defaults={"is_system": True}
        )
        if was_created:
            created += 1
    return created


def record_transaction(
    *,
    farm,
    type,
    category_name,
    amount,
    transaction_date,
    source_module,
    source_id=None,
    animal=None,
    group=None,
    currency="NGN",
    description="",
    payment_status="paid",
    payment_method=None,
    transaction_reference=None,
    notes=None,
    created_by=None,
):
    """
    Shared entry point for every module (animal acquisition, feed issuance,
    treatment, sales, etc.) to post a ledger entry. Centralizing this here
    means historical transactions are never recalculated after the fact —
    each one is its own stored, auditable record.
    """
    if amount is None or amount <= 0:
        return None

    category, _ = TransactionCategory.objects.get_or_create(
        name=category_name, type=type, defaults={"is_system": True}
    )

    return Transaction.objects.create(
        farm=farm,
        animal=animal,
        group=group,
        type=type,
        category=category,
        amount=amount,
        currency=currency,
        transaction_date=transaction_date,
        description=description,
        source_module=source_module,
        source_id=str(source_id) if source_id is not None else None,
        payment_status=payment_status,
        payment_method=payment_method,
        transaction_reference=transaction_reference,
        notes=notes,
        created_by=created_by,
    )


def get_financial_profile(animal):
    """
    Safe accessor for an animal's AnimalFinancialProfile — a reverse OneToOne
    that raises DoesNotExist (not caught by getattr's default) when no
    profile row has been created yet, e.g. for an animal with no acquisition
    data on record.
    """
    try:
        return animal.financial_profile
    except AnimalFinancialProfile.DoesNotExist:
        return None


def _acquisition_baseline(animal):
    """
    Acquisition/opening value that hasn't yet been posted as its own
    Transaction. Kept self-healing on purpose: whether or not the
    animal-creation flow has been wired to post an "Acquisition" transaction
    for this particular animal, the baseline is counted exactly once either
    way — never doubled, never silently dropped.
    """
    has_acquisition_txn = Transaction.objects.filter(
        animal=animal, type="expense", category__name="Acquisition"
    ).exists()
    if has_acquisition_txn:
        return 0.0
    profile = get_financial_profile(animal)
    if not profile:
        return 0.0
    return float(profile.acquisition_cost or profile.opening_value or 0)


def compute_cost_breakdown(animal):
    """{category_name: total_expense_amount}, including the acquisition baseline."""
    breakdown = {}
    for t in Transaction.objects.filter(animal=animal, type="expense").select_related("category"):
        breakdown[t.category.name] = breakdown.get(t.category.name, 0) + float(t.amount)

    baseline = _acquisition_baseline(animal)
    if baseline:
        breakdown["Acquisition"] = breakdown.get("Acquisition", 0) + baseline
    return breakdown


def compute_total_cost_to_date(animal):
    return sum(compute_cost_breakdown(animal).values())


def compute_income_generated(animal):
    from django.db.models import Sum

    return float(
        Transaction.objects.filter(animal=animal, type="income").aggregate(t=Sum("amount"))["t"] or 0
    )
