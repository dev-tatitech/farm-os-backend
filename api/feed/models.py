from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
User = get_user_model()
from django.utils import timezone
from django.db import models, transaction


class FeedCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_system = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Feed Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class FeedUnit(models.Model):
    name = models.CharField(max_length=50)
    abbreviation = models.CharField(max_length=20, blank=True, null=True)
    farm = models.ForeignKey(
        "organization.Farm",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="custom_feed_units",
    )
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "name"],
                name="unique_feed_unit_per_farm",
            )
        ]

    def __str__(self):
        return self.name


class FeedType(models.Model):
    name = models.CharField(max_length=150)
    category = models.ForeignKey(
        FeedCategory,
        on_delete=models.PROTECT,
        related_name="feed_types",
    )
    species = models.ManyToManyField(
        "admin_panel.LivestockSpecies",
        related_name="feed_types",
        blank=True,
    )
    farm = models.ForeignKey(
        "organization.Farm",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="custom_feed_types",
    )
    description = models.TextField(null=True, blank=True)
    manufacturer = models.CharField(max_length=150, null=True, blank=True)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_feed_types",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "name"],
                name="unique_feed_type_per_farm",
            )
        ]

    def __str__(self):
        return self.name


class FeedInventory(models.Model):
    STATUS_CHOICES = [
        ("normal", "Normal"),
        ("low_stock", "Low Stock"),
        ("out_of_stock", "Out of Stock"),
    ]
    farm = models.ForeignKey(
        "organization.Farm",
        on_delete=models.CASCADE,
        related_name="feed_inventories"
    )
    feed_name = models.CharField(max_length=255)
    feed_type = models.ForeignKey(
        FeedType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventories",
    )
    quantity_available = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    unit = models.CharField(max_length=50)  # e.g. kg, bags, tons
    feed_unit = models.ForeignKey(
        FeedUnit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventories",
    )
    reorder_level = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="normal"
    )
    last_restocked_at = models.DateTimeField(
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["feed_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "feed_name"],
                name="unique_feed_per_farm"
            )
        ]
        indexes = [
            models.Index(fields=["farm", "status"]),
        ]
    def __str__(self):
        return f"{self.feed_name} ({self.quantity_available} {self.unit})"
    def clean(self):
        if self.quantity_available < 0:
            raise ValidationError("Quantity cannot be negative.")
        if self.reorder_level is not None and self.reorder_level < 0:
            raise ValidationError("Reorder level cannot be negative.")
    def update_status(self):
        if self.quantity_available <= 0:
            self.status = "out_of_stock"
        elif (
            self.reorder_level is not None and
            self.quantity_available <= self.reorder_level
        ):
            self.status = "low_stock"
        else:
            self.status = "normal"
    def save(self, *args, **kwargs):
        self.full_clean()  
        if self.pk:
            old = FeedInventory.objects.filter(pk=self.pk).first()
            if old and self.quantity_available > old.quantity_available:
                self.last_restocked_at = timezone.now()
        self.update_status()
        super().save(*args, **kwargs)
        
class FeedPlan(models.Model):

    PLAN_TYPE_CHOICES = [
        ("species", "Species"),
        ("group", "Group"),
    ]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("completed", "Completed"),
    ]
    farm = models.ForeignKey(
        "organization.Farm",
        on_delete=models.CASCADE,
        related_name="feed_plans"
    )
    plan_type = models.CharField(
        max_length=10,
        choices=PLAN_TYPE_CHOICES
    )
    species = models.ForeignKey(
        "admin_panel.Species",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feed_plans"
    )
    livestock_species = models.ForeignKey(
        "admin_panel.LivestockSpecies",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feed_plans"
    )
    group = models.ForeignKey(
        "animals.AnimalGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feed_plans"
    )
    feed_inventory = models.ForeignKey(
        FeedInventory,   
        on_delete=models.CASCADE,
        related_name="feed_plans"
    )
    daily_feed_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    unit = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField(
        null=True,
        blank=True
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="inactive"  
    )
    notes = models.TextField(
        null=True,
        blank=True
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_feed_plans"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["farm", "status"]),
        ]
    def clean(self):
        if self.plan_type == "species":
            if not self.species:
                raise ValidationError("Species is required for species-based feed plan.")
            if self.group:
                raise ValidationError("Group must be empty when plan_type is species.")

        elif self.plan_type == "group":
            if not self.group:
                raise ValidationError("Group is required for group-based feed plan.")
            if self.species:
                raise ValidationError("Species must be empty when plan_type is group.")

        if self.end_date and self.end_date < self.start_date:
            raise ValidationError("End date cannot be before start date.")

        if self.daily_feed_quantity <= 0:
            raise ValidationError("Daily feed quantity must be greater than zero.")

    def update_status(self):
        today = timezone.now().date()

        if self.end_date and today > self.end_date:
            return "completed"
        elif self.start_date <= today:
            return "active"
        return "inactive"

    def save(self, *args, **kwargs):
        self.full_clean()
        self.status = self.update_status()
        super().save(*args, **kwargs)
    def __str__(self):
        target = self.species or self.group
        return f"{self.plan_type} plan ({target}) - {self.daily_feed_quantity} {self.unit}"
    
class FeedIssuanceRecord(models.Model):
    TARGET_TYPE_CHOICES = [
        ("animal", "Animal"),
        ("group", "Group"),
    ]
    farm = models.ForeignKey(
        "organization.Farm",
        on_delete=models.CASCADE,
        related_name="feed_issuance_records"
    )
    target_type = models.CharField(
        max_length=10,
        choices=TARGET_TYPE_CHOICES
    )
    animal = models.ForeignKey(
        "animals.Animal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feed_issuances"
    )
    group = models.ForeignKey(
        "animals.AnimalGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feed_issuances"
    )
    feed_inventory = models.ForeignKey(
        FeedInventory,
        on_delete=models.CASCADE,
        related_name="issuance_records"
    )

    quantity_issued = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    issue_date = models.DateField()
    issued_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="issued_feed_records"
    )
    notes = models.TextField(
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-issue_date"]
        indexes = [
            models.Index(fields=["farm", "issue_date"]),
        ]
    def __str__(self):
        return f"{self.target_type} - {self.quantity_issued}"
    def clean(self):
        # target validation
        if self.target_type == "animal":
            if not self.animal:
                raise ValidationError("Animal is required when target_type is 'animal'.")
            if self.group:
                raise ValidationError("Group must be empty when target_type is 'animal'.")
        elif self.target_type == "group":
            if not self.group:
                raise ValidationError("Group is required when target_type is 'group'.")
            if self.animal:
                raise ValidationError("Animal must be empty when target_type is 'group'.")
        # quantity validation
        if self.quantity_issued <= 0:
            raise ValidationError("Quantity must be greater than zero.")
    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            inventory = self.feed_inventory
            inventory = (
                type(inventory)
                .objects.select_for_update()
                .get(pk=inventory.pk)
            )
            if inventory.quantity_available < self.quantity_issued:
                raise ValidationError("Insufficient stock available.")
            inventory.quantity_available -= self.quantity_issued
            inventory.save()
            super().save(*args, **kwargs)
            
class FeedConfirmationRecord(models.Model):
    STATUS_CHOICES = [
        ("confirmed", "Confirmed"),
        ("variance_detected", "Variance Detected"),
    ]
    farm = models.ForeignKey(
        "organization.Farm",
        on_delete=models.CASCADE,
        related_name="feed_confirmations"
    )
    issuance = models.OneToOneField(
        FeedIssuanceRecord,
        on_delete=models.CASCADE,
        related_name="confirmation"
    )

    actual_used_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    confirmation_date = models.DateField()

    confirmed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="confirmed_feed_records"
    )

    notes = models.TextField(
        null=True,
        blank=True
    )

    variance_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-confirmation_date"]

    def clean(self):
        if self.actual_used_quantity < 0:
            raise ValidationError("Actual used quantity cannot be negative.")
        issued_qty = self.issuance.quantity_issued
        if self.actual_used_quantity > issued_qty:
            raise ValidationError(
                "Actual used quantity cannot exceed issued quantity."
            )
    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            issued_qty = self.issuance.quantity_issued
            self.variance_quantity = issued_qty - self.actual_used_quantity
            self.status = (
                "confirmed"
                if self.variance_quantity == 0
                else "variance_detected"
            )
            super().save(*args, **kwargs)
            if self.variance_quantity > 0:
                inventory = self.issuance.feed_inventory
                inventory = (
                    type(inventory)
                    .objects.select_for_update()
                    .get(pk=inventory.pk)
                )
                inventory.quantity_available += self.variance_quantity
                inventory.save()
    def __str__(self):
        return f"Confirmation - Issuance {self.issuance_id}"