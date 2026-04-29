from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
User = get_user_model()
from django.utils import timezone


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
    quantity_available = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    unit = models.CharField(max_length=50)  # e.g. kg, bags, tons
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