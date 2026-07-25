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
