from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
User = get_user_model()
from django.utils import timezone


class TreatmentRecord(models.Model):
    SEVERITY_CHOICES = [
        ("mild", "Mild"),
        ("moderate", "Moderate"),
        ("severe", "Severe"),
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
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def clean(self):
        if not self.animal and not self.group:
            raise ValidationError("At least one of animal or group must be provided.")
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.severity == "severe" and self.animal:
            if self.animal.status != "dead" and self.animal.status != "sold":
                self.animal.status = "sick"
                self.animal.save(update_fields=["status"])
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