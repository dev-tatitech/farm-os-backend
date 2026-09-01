from django.db import models
from django.core.exceptions import ValidationError
from datetime import timedelta
from django.contrib.auth import get_user_model
User = get_user_model()


class BreedingEligibilityRule(models.Model):
    """
    Species/breed/farm-scoped breeding rules. Resolution favors the most
    specific match: farm+breed > farm+species > system+breed > system+species,
    so a farm can override the system default without duplicating it for
    every breed. `breed`/`farm` null means "applies to all breeds"/"system
    default", respectively.
    """
    species = models.ForeignKey(
        "admin_panel.LivestockSpecies", on_delete=models.CASCADE, related_name="breeding_rules"
    )
    breed = models.ForeignKey(
        "admin_panel.LivestockBreed", null=True, blank=True,
        on_delete=models.CASCADE, related_name="breeding_rules"
    )
    farm = models.ForeignKey(
        "organization.Farm", null=True, blank=True,
        on_delete=models.CASCADE, related_name="breeding_rules"
    )

    min_breeding_age_months = models.FloatField(null=True, blank=True)
    recommended_breeding_age_months = models.FloatField(null=True, blank=True)
    max_breeding_age_months = models.FloatField(null=True, blank=True)
    min_breeding_weight_kg = models.FloatField(null=True, blank=True)
    min_postpartum_interval_days = models.PositiveIntegerField(null=True, blank=True)
    max_births_lifetime = models.PositiveIntegerField(null=True, blank=True)

    # Whether pregnant + lactating may co-occur for this species/farm. Default
    # True (allowed, farms decide) — the spec explicitly warns against a
    # hardcoded universal block, since many species/systems permit it.
    allow_pregnant_and_lactating = models.BooleanField(default=True)

    is_system = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["species", "breed", "farm"], name="unique_breeding_rule_scope"
            )
        ]

    def __str__(self):
        return f"BreedingRule({self.species_id}, breed={self.breed_id}, farm={self.farm_id})"


class InseminationRecord(models.Model):
    METHOD_CHOICES = [
        ("natural", "Natural"),
        ("artificial", "Artificial"),
    ]
    farm = models.ForeignKey("organization.Farm", on_delete=models.CASCADE)
    animal = models.ForeignKey("animals.Animal", on_delete=models.CASCADE)
    service_date = models.DateField()
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    sire_reference = models.CharField(max_length=255, null=True, blank=True)
    technician_name = models.CharField(max_length=255, null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
    User,
    on_delete=models.SET_NULL,
    null=True
)
    def clean(self):
        if self.animal and not getattr(self, "_override_eligibility", False):
            from .eligibility import check_breeding_eligibility
            is_eligible, reasons = check_breeding_eligibility(self.animal, farm=self.farm)
            if not is_eligible:
                raise ValidationError({"animal": reasons})
        if self.method == "artificial" and not self.sire_reference:
            raise ValidationError("Sire reference is required for artificial insemination.")
    def save(self, *args, **kwargs):
        self.full_clean()  
        super().save(*args, **kwargs)
    def __str__(self):
        return f"{self.animal} - {self.service_date}"
    
class PregnancyRecord(models.Model):
    RESULT_CHOICES = [
        ('pregnant', 'Pregnant'),
        ('not_pregnant', 'Not Pregnant'),
    ]
    farm = models.ForeignKey("organization.Farm", on_delete=models.CASCADE)
    animal = models.ForeignKey("animals.Animal", on_delete=models.CASCADE)
    insemination = models.ForeignKey(
        InseminationRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pregnancy_records'
    )
    check_date = models.DateField()
    result = models.CharField(
        max_length=20,
        choices=RESULT_CHOICES
    )
    expected_delivery_date = models.DateField(
        null=True,
        blank=True
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "animal"],
                name="unique_pregnancy_per_animal_per_farm"
            )
        ]
    def clean(self):
        if self.result == "pregnant" and self.animal and not getattr(self, "_override_eligibility", False):
            from .eligibility import check_breeding_eligibility
            is_eligible, reasons = check_breeding_eligibility(self.animal, farm=self.farm, for_pregnancy=True)
            if not is_eligible:
                raise ValidationError({"animal": reasons})
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
        if self.result == "pregnant":
            self.animal.is_pregnant = True
            self.animal.save(update_fields=["is_pregnant"])
        elif self.result == "not_pregnant":
            self.animal.is_pregnant = False
            self.animal.save(update_fields=["is_pregnant"])
            
class BirthRecord(models.Model):
    farm = models.ForeignKey("organization.Farm", on_delete=models.CASCADE)
    mother = models.ForeignKey("animals.Animal", on_delete=models.CASCADE)
    birth_date = models.DateField()
    number_of_offspring = models.PositiveIntegerField()
    number_alive = models.PositiveIntegerField()
    number_dead = models.PositiveIntegerField()
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    def clean(self):
        if self.number_alive + self.number_dead != self.number_of_offspring:
            raise ValidationError("alive + dead must equal total_offspring.")
        if self.pk:
            registered = self.offspring_records.filter(
                registration_status="registered", offspring_animal__isnull=False
            ).count()
            if self.number_alive < registered:
                raise ValidationError(
                    "Cannot reduce live offspring below already registered animals. "
                    "Escalate this historical correction."
                )
        if not self.mother.is_pregnant:
            raise ValidationError("Mother must be pregnant to record a birth.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
        self.ensure_offspring_slots()

    def ensure_offspring_slots(self):
        existing = {row.offspring_sequence: row for row in self.offspring_records.all()}
        for sequence in range(1, self.number_alive + 1):
            if sequence in existing:
                continue
            BirthOffspringRecord.objects.create(
                farm=self.farm,
                birth_record=self,
                offspring_sequence=sequence,
                registration_status="registration_required",
            )
        extras = [
            row
            for seq, row in existing.items()
            if seq > self.number_alive and row.registration_status != "registered"
        ]
        for row in extras:
            row.delete()

    @property
    def pending_offspring_registration(self):
        return self.offspring_records.filter(registration_status="registration_required").count()
        
class BirthOffspringRecord(models.Model):
    GENDER_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
    ]
    REGISTRATION_CHOICES = [
        ("registration_required", "Registration required"),
        ("registered", "Registered"),
        ("deceased", "Deceased"),
    ]
    farm = models.ForeignKey("organization.Farm", on_delete=models.CASCADE)
    offspring_animal = models.ForeignKey(
        "animals.Animal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="birth_links",
    )
    birth_record = models.ForeignKey(
        BirthRecord,
        on_delete=models.CASCADE,
        related_name="offspring_records",
    )
    offspring_sequence = models.PositiveIntegerField(default=1)
    registration_status = models.CharField(
        max_length=32,
        choices=REGISTRATION_CHOICES,
        default="registration_required",
    )
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    birth_weight = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["birth_record", "offspring_sequence"],
                name="unique_birth_offspring_sequence",
            )
        ]