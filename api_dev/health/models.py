from django.db import models
from django.db import transaction as db_transaction
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from datetime import timedelta
User = get_user_model()
from django.utils import timezone


class TreatmentRecord(models.Model):
    SEVERITY_CHOICES = [
        ("mild", "Mild"),
        ("moderate", "Moderate"),
        ("severe", "Severe"),
    ]
    ADMINISTRATION_ROUTE_CHOICES = [
        ("oral", "Oral"),
        ("injection", "Injection"),
        ("topical", "Topical"),
        ("other", "Other"),
    ]
    farm = models.ForeignKey("organization.Farm", on_delete=models.CASCADE)
    animal = models.ForeignKey("animals.Animal", on_delete=models.CASCADE, related_name="treatments", null=True,
        blank=True,)
    group = models.ForeignKey(
        "animals.AnimalGroup",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="treatments"
    )
    diagnosis = models.TextField()
    treatment = models.TextField()
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    treatment_date = models.DateField()
    next_follow_up_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    case = models.ForeignKey(
        "health.HealthCase",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="treatments",
    )
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Pharmacy-linked treatment workflow (spec 3.3) — all optional so a
    # treatment can still be recorded as a plain clinical note without
    # drawing from inventory, same behavior as before this was added.
    drug = models.ForeignKey(
        "pharmacy.Drug", on_delete=models.PROTECT, null=True, blank=True, related_name="treatments"
    )
    drug_batch = models.ForeignKey(
        "pharmacy.DrugBatch", on_delete=models.PROTECT, null=True, blank=True, related_name="treatments"
    )
    quantity_administered = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    dose = models.CharField(max_length=100, null=True, blank=True)
    frequency = models.CharField(max_length=100, null=True, blank=True)
    duration_days = models.PositiveIntegerField(null=True, blank=True)
    administration_route = models.CharField(max_length=20, choices=ADMINISTRATION_ROUTE_CHOICES, null=True, blank=True)
    administered_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="administered_treatments"
    )
    prescribed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="prescribed_treatments"
    )
    next_dose_date = models.DateField(null=True, blank=True)
    withdrawal_end_date = models.DateField(null=True, blank=True)
    treatment_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # External / emergency medication (spec 3.4) — a drug obtained and
    # administered before being formally received into pharmacy inventory.
    # Deliberately bypasses DrugBatch deduction; permission-gated at the API
    # layer so regular treatment-entry users can't use this to sidestep
    # inventory tracking.
    is_external_administration = models.BooleanField(default=False)
    external_drug_name = models.CharField(max_length=200, null=True, blank=True)
    external_unit = models.CharField(max_length=50, null=True, blank=True)
    external_unit_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    external_source = models.CharField(max_length=200, null=True, blank=True)
    external_reason = models.TextField(null=True, blank=True)
    reconciled_to_batch = models.ForeignKey(
        "pharmacy.DrugBatch", on_delete=models.SET_NULL, null=True, blank=True, related_name="reconciled_treatments"
    )

    def clean(self):
        if not self.animal and not self.group:
            raise ValidationError("At least one of animal or group must be provided.")
        if self.drug_batch_id and not self.quantity_administered:
            raise ValidationError("Quantity administered is required when a drug batch is selected.")
        if self.quantity_administered is not None and self.quantity_administered <= 0:
            raise ValidationError("Quantity administered must be greater than zero.")
        if self.is_external_administration:
            if not self.quantity_administered or self.external_unit_cost is None:
                raise ValidationError("Quantity administered and unit cost are required for external medication.")
            if self.drug_batch_id:
                raise ValidationError("External medication must not reference a drug batch — that would bypass inventory tracking.")

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        if self.drug_id and not self.withdrawal_end_date:
            self.withdrawal_end_date = self.treatment_date + timedelta(days=self.drug.withdrawal_period_days)

        if self.is_external_administration and self.quantity_administered and self.external_unit_cost is not None:
            self.treatment_cost = self.quantity_administered * self.external_unit_cost

        if is_new and self.drug_batch_id and self.quantity_administered:
            with db_transaction.atomic():
                from pharmacy.models import DrugBatch

                batch = DrugBatch.objects.select_for_update().get(pk=self.drug_batch_id)
                if batch.quantity_available < self.quantity_administered:
                    raise ValidationError("Insufficient stock available in the selected drug batch.")
                batch.quantity_available -= self.quantity_administered
                batch.save()
                self.treatment_cost = self.quantity_administered * (batch.cost_per_base_unit or 0)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

        if self.severity == "severe" and self.animal:
            if self.animal.status != "dead" and self.animal.status != "sold":
                self.animal.health_status = "sick"
                self.animal.save(update_fields=["health_status"])

        if is_new and self.treatment_cost and self.animal_id:
            from finance.services import record_transaction

            record_transaction(
                farm=self.farm, type="expense", category_name="Treatment", amount=self.treatment_cost,
                transaction_date=self.treatment_date, source_module="treatment", source_id=self.id,
                animal=self.animal, created_by=self.created_by,
            )

    def __str__(self):
        return f"Treatment {self.id} - {self.severity}"

class VaccinationRecord(models.Model):
    farm = models.ForeignKey(
       "organization.Farm",
        on_delete=models.CASCADE,
        related_name="vaccination_records"
    )
    animal = models.ForeignKey(
        "animals.Animal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vaccinations"
    )
    group = models.ForeignKey(
        "animals.AnimalGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vaccination_records"
    )
    vaccine_name = models.CharField(max_length=255)
    date_given = models.DateField()
    next_due_date = models.DateField(
        null=True,
        blank=True
    )
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_given"]

    def __str__(self):
        return f"{self.vaccine_name} ({self.date_given})"
    
class QuarantineRecord(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("released", "Released"),
    ]
    farm = models.ForeignKey(
        "organization.Farm",
        on_delete=models.CASCADE,
        related_name="quarantine_records"
    )
    animal = models.ForeignKey(
        "animals.Animal",
        on_delete=models.CASCADE,
        related_name="quarantine_records"
    )
    reason = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField(
        null=True,
        blank=True
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="active"
    )
    notes = models.TextField(
        null=True,
        blank=True
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_quarantine_records"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-start_date"]
    def save(self, *args, **kwargs):
        if self.status == "released" and not self.end_date:
            self.end_date = timezone.now().date()

        super().save(*args, **kwargs)
        is_quarantined = QuarantineRecord.objects.filter(
            animal=self.animal,
            status="active"
        ).exists()
        if self.animal.is_quarantine != is_quarantined:
            self.animal.is_quarantine = is_quarantined
            self.animal.save(update_fields=["is_quarantine"])

    def __str__(self):
        return f"{self.animal} - {self.status}"
    
class MortalityRecord(models.Model):
    STATUS_CHOICES = [
        ("recorded", "Recorded"),
        ("approved", "Approved"),
        ("corrected", "Corrected"),
    ]
    farm = models.ForeignKey(
        "organization.Farm",
        on_delete=models.CASCADE,
        related_name="mortality_records"
    )
    animal = models.OneToOneField(
        "animals.Animal",
        on_delete=models.CASCADE,
        related_name="mortality_record"
    )
    cause = models.TextField()
    death_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="recorded",
    )
    notes = models.TextField(
        null=True,
        blank=True
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_mortality_records"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-death_date"]
    def __str__(self):
        return f"{self.animal.tag_id} - {self.death_date}"
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            self.animal.mark_dead()


class HealthAlert(models.Model):
    SEVERITY_CHOICES = [
        ("informational", "Informational"),
        ("monitor", "Monitor"),
        ("attention_required", "Attention Required"),
        ("high_priority", "High Priority"),
        ("critical", "Critical"),
    ]
    STATUS_CHOICES = [
        ("open", "Open"),
        ("acknowledged", "Acknowledged"),
        ("resolved", "Resolved"),
        ("dismissed", "Dismissed"),
    ]

    farm = models.ForeignKey("organization.Farm", on_delete=models.CASCADE, related_name="health_alerts")
    animal = models.ForeignKey(
        "animals.Animal", null=True, blank=True, on_delete=models.CASCADE, related_name="health_alerts"
    )
    group = models.ForeignKey(
        "animals.AnimalGroup", null=True, blank=True, on_delete=models.CASCADE, related_name="health_alerts"
    )
    drug_batch = models.ForeignKey(
        "pharmacy.DrugBatch", null=True, blank=True, on_delete=models.CASCADE, related_name="health_alerts"
    )

    alert_type = models.CharField(max_length=50)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    detected_date = models.DateField()
    evidence = models.TextField()
    recommended_review = models.TextField()

    assigned_user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_health_alerts"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    resolution_notes = models.TextField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="resolved_health_alerts"
    )
    resolution_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-detected_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["animal", "alert_type"],
                condition=models.Q(status="open"),
                name="unique_open_alert_per_animal_type",
            ),
            models.UniqueConstraint(
                fields=["drug_batch", "alert_type"],
                condition=models.Q(status="open"),
                name="unique_open_alert_per_batch_type",
            ),
        ]

    def __str__(self):
        return f"{self.alert_type} - {self.animal_id or self.drug_batch_id} ({self.severity})"


class HealthCase(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    farm = models.ForeignKey(
        "organization.Farm", on_delete=models.CASCADE, related_name="health_cases"
    )
    animal = models.ForeignKey(
        "animals.Animal",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="health_cases",
    )
    group = models.ForeignKey(
        "animals.AnimalGroup",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="health_cases",
    )
    title = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    opened_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="opened_health_cases"
    )
    closed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="closed_health_cases"
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self):
        return f"{self.title} ({self.status})"


class HealthObservation(models.Model):
    farm = models.ForeignKey(
        "organization.Farm", on_delete=models.CASCADE, related_name="health_observations"
    )
    animal = models.ForeignKey(
        "animals.Animal",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="health_observations",
    )
    group = models.ForeignKey(
        "animals.AnimalGroup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="health_observations",
    )
    case = models.ForeignKey(
        HealthCase,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="observations",
    )
    observed_at = models.DateTimeField()
    symptoms = models.TextField()
    severity = models.CharField(max_length=20, default="mild")
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-observed_at"]

    def __str__(self):
        return f"Observation {self.id}"