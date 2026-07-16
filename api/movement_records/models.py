from django.db import models
from django.core.exceptions import ValidationError
from account.models import User
from organization.models import Farm


class MovementRecord(models.Model):
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE)
    animal = models.ForeignKey(
        "animals.Animal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movement_records",
    )
    group = models.ForeignKey(
        "animals.AnimalGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movement_records",
    )
    from_unit = models.ForeignKey(
        "farms.FarmUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movement_from_records",
    )
    to_unit = models.ForeignKey(
        "farms.FarmUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movement_to_records",
    )
    from_housing_unit = models.ForeignKey(
        "admin_panel.FarmHousingUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movement_from_records",
    )
    to_housing_unit = models.ForeignKey(
        "admin_panel.FarmHousingUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movement_to_records",
    )
    move_date = models.DateTimeField()
    reason = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_movement_records",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Movement Record"
        verbose_name_plural = "Movement Records"
        ordering = ["-created_at"]

    def clean(self):
        # ensure either animal or group is provided
        if not self.animal_id and not self.group_id:
            raise ValidationError({"__all__": "Either animal or group must be provided."})

        # one record per animal
        if self.animal_id:
            qs = MovementRecord.objects.filter(animal_id=self.animal_id)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError({"animal": "A movement record for this animal already exists."})

            # prevent dead/sold animal movement
            try:
                animal = self.animal
                if animal and getattr(animal, "status", None) in ["sold", "dead"]:
                    raise ValidationError({"animal": "Sold or dead animals cannot be moved."})
            except Exception:
                pass

        # one record per group
        if self.group_id:
            qs = MovementRecord.objects.filter(group_id=self.group_id)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError({"group": "A movement record for this group already exists."})

    def __str__(self):
        return f"MovementRecord #{self.id} for {self.farm}"

class SalesRecord(models.Model):
    STATUS_CHOICES = [
        ("recorded", "Recorded"),
        ("approved", "Approved"),
        ("corrected", "Corrected"),
    ]
    farm = models.ForeignKey(
        Farm,
        on_delete=models.CASCADE,
        related_name="movement_sales_records",
    )
    animal = models.ForeignKey(
        "animals.Animal",
        on_delete=models.CASCADE,
        related_name="movement_sales_records",
        related_query_name="movement_sales_record",
    )
    buyer_name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    sale_date = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="recorded",
    )
    reason = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_movement_sales_records",
        related_query_name="created_movement_sales_record",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Sales Record"
        verbose_name_plural = "Sales Records"
        ordering = ["-created_at"]

    def clean(self):
        if not self.animal_id:
            raise ValidationError({"animal": "Animal is required for a sales record."})

        animal = self.animal
        if animal and animal.status in ["sold", "dead"]:
            raise ValidationError({"animal": "Only active animals can be sold."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        try:
            animal = self.animal
            if animal.status != "sold":
                animal.status = "sold"
                animal.is_active = False
                animal.save(update_fields=["status", "is_active"])
        except Exception:
            pass

    def __str__(self):
        return f"Sale #{self.id} for {self.animal}"
