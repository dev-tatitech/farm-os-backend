from django.db import models
from core.models import TimeStampedModel
from django.contrib.auth import get_user_model

User = get_user_model()


class TransactionCategory(models.Model):
    TYPE_CHOICES = [
        ("expense", "Expense"),
        ("income", "Income"),
    ]
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    is_system = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Transaction Categories"
        ordering = ["type", "name"]
        constraints = [
            models.UniqueConstraint(fields=["name", "type"], name="unique_transaction_category")
        ]

    def __str__(self):
        return f"{self.name} ({self.type})"


class Transaction(TimeStampedModel):
    TYPE_CHOICES = [
        ("expense", "Expense"),
        ("income", "Income"),
    ]
    PAYMENT_STATUS_CHOICES = [
        ("paid", "Paid"),
        ("pending", "Pending"),
        ("partial", "Partial"),
    ]

    farm = models.ForeignKey(
        "organization.Farm", on_delete=models.CASCADE, related_name="transactions"
    )
    animal = models.ForeignKey(
        "animals.Animal", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="transactions"
    )
    group = models.ForeignKey(
        "animals.AnimalGroup", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="transactions"
    )
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    category = models.ForeignKey(
        TransactionCategory, on_delete=models.PROTECT, related_name="transactions"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10, default="NGN")
    transaction_date = models.DateField()
    description = models.CharField(max_length=255, blank=True)

    # Which module/record produced this transaction (e.g. "animal_acquisition",
    # "feed_issuance", "treatment", "sales_record"), so historical entries can
    # always be traced back to their source without re-deriving them.
    source_module = models.CharField(max_length=50)
    source_id = models.CharField(max_length=64, null=True, blank=True)

    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default="paid"
    )
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    transaction_reference = models.CharField(max_length=100, blank=True, null=True)
    supporting_document = models.FileField(
        upload_to="finance/documents/", null=True, blank=True
    )
    notes = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="created_transactions"
    )

    class Meta:
        ordering = ["-transaction_date", "-created_at"]
        indexes = [
            models.Index(fields=["farm", "transaction_date"]),
            models.Index(fields=["animal"]),
            models.Index(fields=["group"]),
            models.Index(fields=["source_module", "source_id"]),
        ]

    def __str__(self):
        return f"{self.type} - {self.category_id} - {self.amount}"


class AnimalFinancialProfile(models.Model):
    """
    Denormalized money fields for an animal, kept separate from the
    detailed AnimalAcquisition record so most reads (list/report views)
    don't need the wider acquisition join. Written by animals/acquisition.py
    and read wherever a fast per-animal cost baseline is needed.
    """
    animal = models.OneToOneField(
        "animals.Animal", on_delete=models.CASCADE, related_name="financial_profile"
    )
    acquisition_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    opening_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    current_estimated_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"Financial profile for {self.animal.tag_id}"


class AnimalAcquisition(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ("paid", "Paid"),
        ("pending", "Pending"),
        ("partial", "Partial"),
    ]
    VALUATION_METHOD_CHOICES = [
        ("market_comparison", "Market Comparison"),
        ("book_value", "Book Value"),
        ("professional_appraisal", "Professional Appraisal"),
        ("owner_estimate", "Owner Estimate"),
    ]

    animal = models.OneToOneField(
        "animals.Animal", on_delete=models.CASCADE, related_name="acquisition"
    )

    # Shared across purchased / imported
    supplier = models.CharField(max_length=255, blank=True, null=True)
    purchase_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, default="NGN")
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default="paid")
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    transaction_reference = models.CharField(max_length=100, blank=True, null=True)
    supporting_document = models.FileField(upload_to="animals/acquisition/", null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    # Purchased
    purchase_date = models.DateField(null=True, blank=True)
    transportation_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    veterinary_inspection_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    other_acquisition_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # Imported
    country_of_origin = models.CharField(max_length=100, blank=True, null=True)
    import_date = models.DateField(null=True, blank=True)
    shipping_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    customs_clearance_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    quarantine_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    veterinary_certification_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    insurance_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    other_import_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # Born on farm - internal production cost components (not a purchase transaction)
    production_cost_dam_feeding = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    production_cost_pregnancy_treatment = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    production_cost_delivery = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    production_cost_breeding = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # Opening record
    estimated_opening_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    valuation_date = models.DateField(null=True, blank=True)
    valuation_method = models.CharField(max_length=30, choices=VALUATION_METHOD_CHOICES, blank=True, null=True)
    valuation_notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def total_purchased_cost(self):
        return (
            (self.purchase_price or 0)
            + (self.transportation_cost or 0)
            + (self.veterinary_inspection_cost or 0)
            + (self.other_acquisition_cost or 0)
        )

    def total_landed_cost(self):
        return (
            (self.purchase_price or 0)
            + (self.shipping_cost or 0)
            + (self.customs_clearance_cost or 0)
            + (self.quarantine_cost or 0)
            + (self.veterinary_certification_cost or 0)
            + (self.insurance_cost or 0)
            + (self.other_import_cost or 0)
        )

    def total_production_cost(self):
        return (
            (self.production_cost_dam_feeding or 0)
            + (self.production_cost_pregnancy_treatment or 0)
            + (self.production_cost_delivery or 0)
            + (self.production_cost_breeding or 0)
        )

    def __str__(self):
        return f"Acquisition for {self.animal.tag_id}"
