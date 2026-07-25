from django.db import models
from django.core.exceptions import ValidationError
from account.models import User
from organization.models import Farm


class SalePolicy(models.Model):
    """
    Species/breed/farm-scoped sale rules (Phase 4). Same most-specific-wins
    resolution as BreedingEligibilityRule/WeightReferenceRange: farm+breed >
    farm-only > breed-only > system default.
    """
    species = models.ForeignKey(
        "admin_panel.LivestockSpecies", on_delete=models.CASCADE, related_name="sale_policies"
    )
    breed = models.ForeignKey(
        "admin_panel.LivestockBreed", null=True, blank=True,
        on_delete=models.CASCADE, related_name="sale_policies"
    )
    farm = models.ForeignKey(
        Farm, null=True, blank=True, on_delete=models.CASCADE, related_name="sale_policies"
    )

    target_sale_weight_kg = models.FloatField(null=True, blank=True)
    min_sale_age_months = models.FloatField(null=True, blank=True)
    approaching_ready_threshold_pct = models.FloatField(default=85)
    sale_recommended_margin_pct = models.FloatField(default=15)

    # Explicit farm/species policy, per spec 9.3 — pregnancy must not be a
    # hardcoded universal sale block.
    allow_pregnant_sale = models.BooleanField(default=False)
    require_sale_approval = models.BooleanField(default=False)
    expected_sale_expenses_pct = models.FloatField(default=0)

    is_system = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["species", "breed", "farm"], name="unique_sale_policy_scope"
            )
        ]

    def __str__(self):
        return f"SalePolicy({self.species_id}, breed={self.breed_id}, farm={self.farm_id})"


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

        if not getattr(self, "_override_restriction", False):
            from pharmacy.alerts import check_animal_withdrawal_restriction

            withdrawal_treatment = check_animal_withdrawal_restriction(animal)
            if withdrawal_treatment:
                raise ValidationError({
                    "animal": (
                        f"Animal is within the drug withdrawal period for {withdrawal_treatment.drug.name} "
                        f"(ends {withdrawal_treatment.withdrawal_end_date}) and cannot be sold."
                    )
                })

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
