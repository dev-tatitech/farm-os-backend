from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class DrugCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_system = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Drug Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Drug(models.Model):
    UNIT_CHOICES = [
        ("bottle", "Bottle"), ("vial", "Vial"), ("tablet", "Tablet"), ("sachet", "Sachet"),
        ("ml", "Millilitre"), ("litre", "Litre"), ("gram", "Gram"), ("kg", "Kilogram"), ("dose", "Dose"),
    ]
    DOSAGE_FORM_CHOICES = [
        ("tablet", "Tablet"), ("capsule", "Capsule"), ("injection", "Injection"),
        ("oral_liquid", "Oral Liquid"), ("powder", "Powder"), ("topical", "Topical"), ("other", "Other"),
    ]

    name = models.CharField(max_length=200)
    category = models.ForeignKey(DrugCategory, on_delete=models.PROTECT, related_name="drugs")
    active_ingredient = models.CharField(max_length=200, null=True, blank=True)
    brand_name = models.CharField(max_length=200, null=True, blank=True)
    manufacturer = models.CharField(max_length=200, null=True, blank=True)
    dosage_form = models.CharField(max_length=20, choices=DOSAGE_FORM_CHOICES, null=True, blank=True)
    strength_concentration = models.CharField(max_length=100, null=True, blank=True)
    unit_of_measurement = models.CharField(max_length=10, choices=UNIT_CHOICES)
    withdrawal_period_days = models.PositiveIntegerField(default=0)

    farm = models.ForeignKey(
        "organization.Farm", null=True, blank=True, on_delete=models.CASCADE, related_name="custom_drugs"
    )
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_drugs")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["farm", "name"], name="unique_drug_per_farm")
        ]

    def __str__(self):
        return self.name


class DrugBatch(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"), ("expired", "Expired"), ("depleted", "Depleted"), ("recalled", "Recalled"),
    ]

    drug = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name="batches")
    farm = models.ForeignKey("organization.Farm", on_delete=models.CASCADE, related_name="drug_batches")
    batch_number = models.CharField(max_length=100)

    quantity_received = models.DecimalField(max_digits=12, decimal_places=2)
    quantity_available = models.DecimalField(max_digits=12, decimal_places=2)
    purchase_unit = models.CharField(max_length=100, null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=14, decimal_places=2)
    cost_per_base_unit = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    supplier = models.CharField(max_length=200, null=True, blank=True)

    purchase_date = models.DateField(null=True, blank=True)
    manufacturing_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField()
    storage_location = models.CharField(max_length=200, null=True, blank=True)
    minimum_stock_level = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    supporting_document = models.FileField(upload_to="pharmacy/documents/", null=True, blank=True)

    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_drug_batches")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["expiry_date"]
        constraints = [
            models.UniqueConstraint(fields=["drug", "farm", "batch_number"], name="unique_batch_per_drug_farm")
        ]
        indexes = [
            models.Index(fields=["farm", "status"]),
            models.Index(fields=["expiry_date"]),
        ]

    def save(self, *args, **kwargs):
        if self.purchase_price is not None and self.quantity_received:
            self.cost_per_base_unit = self.purchase_price / self.quantity_received
        if self.status == "active":
            if self.expiry_date and self.expiry_date < timezone.localdate():
                self.status = "expired"
            elif self.quantity_available is not None and self.quantity_available <= 0:
                self.status = "depleted"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.drug.name} - batch {self.batch_number}"
