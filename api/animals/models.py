from django.db import models
from core.models import TimeStampedModel
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
User = get_user_model()


# Create your models here.

class Animal(TimeStampedModel):

    STATUS_CHOICES = [
        ("active", "Active"),
        ("pregnant", "Pregnant"),
        ("lactating", "Lactating"),
        ("sick", "Sick"),
        ("quarantine", "Quarantine"),
        ("sold", "Sold"),
        ("dead", "Dead"),
    ]
    GENDER = [
        ("male", "Male"),
        ("female", "Female"),
    ]
    SOURCE_TYPE = [
        ("born", "Born"),
        ("purchased", "Purchased"),
        ("imported", "Imported"),
    ]
    class HealthStatus(models.TextChoices):
        HEALTHY = "healthy", "Healthy"
        SICK = "sick", "Sick"
        RECOVERING = "recovering", "Recovering"
        AT_RISK = "at_risk", "At Risk"
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='animals_added_by')
    
    # Relationships
    farm = models.ForeignKey("organization.Farm", on_delete=models.CASCADE)
    unit = models.ForeignKey("farms.FarmUnit", on_delete=models.SET_NULL, null=True)

    species = models.ForeignKey("admin_panel.Species", on_delete=models.CASCADE, related_name="animals_species")
    breed = models.ForeignKey("admin_panel.Breed", on_delete=models.CASCADE, related_name="animal_breeds")

    mother = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="offspring"
    )

    # Core fields
    tag_id = models.CharField(max_length=100, unique=True)
    gender = models.CharField(max_length=10, choices=GENDER)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE)

    dob = models.DateField(null=True, blank=True)
    estimated_age_months = models.IntegerField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    health_status = models.CharField(
        max_length=20,
        choices=HealthStatus.choices,
        default=HealthStatus.HEALTHY
    )

    is_pregnant = models.BooleanField(default=False)
    is_lactating = models.BooleanField(default=False)
    is_quarantine = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    notes = models.TextField(blank=True)

    # -----------------------------
    # BUSINESS VALIDATION
    # -----------------------------
    def clean(self):
        errors = {}

        # RULE 1: Born animals
        if self.source_type == "born":
            if not self.mother_id:
                errors["mother"] = "Mother is required when source is 'born'"
            if not self.dob:
                errors["dob"] = "Date of birth is required when source is 'born'"

        # RULE 2: Purchased / Imported animals
        if self.source_type in ["purchased", "imported"]:
            if not self.dob and not self.estimated_age_months:
                errors["dob"] = (
                    "Either date of birth or estimated age is required "
                    "for purchased/imported animals"
                )

        # RULE 3: Gender-based logic
        if self.is_pregnant and self.gender != "female":
            errors["is_pregnant"] = "Only female animals can be pregnant"

        if self.is_lactating and self.gender != "female":
            errors["is_lactating"] = "Only female animals can be lactating"

        # RULE 4: Logical consistency
        if self.source_type == "born" and self.mother_id == self.id:
            errors["mother"] = "Animal cannot be its own mother"

        # RULE 5: Age sanity check
        if self.estimated_age_months is not None and self.estimated_age_months < 0:
            errors["estimated_age_months"] = "Age cannot be negative"

        if errors:
            raise ValidationError(errors)

    # -----------------------------
    # ENSURE VALIDATION ALWAYS RUNS
    # -----------------------------
    def save(self, *args, **kwargs):
        self.full_clean()  # enforce validation everywhere
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.tag_id} ({self.species})"
    
class AnimalProfileAttribute(models.Model):
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='profile_attributes')
    attribute_key = models.CharField(max_length=100)  
    attribute_value = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['animal', 'attribute_key'], name='unique_animal_attribute')
        ]
        verbose_name = 'Animal Profile Attribute'
        verbose_name_plural = 'Animal Profile Attributes'

    def __str__(self):
        return f"{self.animal.tag_id} - {self.attribute_key}: {self.attribute_value}"
    
from django.db import models


class AnimalGroup(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    farm = models.ForeignKey(
        "organization.Farm",
        on_delete=models.CASCADE,
        related_name="animal_groups"
    )
    name = models.CharField(max_length=255)
    group_type = models.ForeignKey("core.GroupType", null=True, blank=True, on_delete=models.SET_NULL)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("farm", "name")
        indexes = [
            models.Index(fields=["farm", "group_type"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.farm})"
    
class AnimalGroupMember(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        REMOVED = "REMOVED", "Removed"
    group = models.ForeignKey(
        AnimalGroup,
        on_delete=models.CASCADE,
        related_name="members"
    )
    animal = models.ForeignKey(
        "Animal",
        on_delete=models.CASCADE,
        related_name="group_memberships"
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    removed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    class Meta:
        unique_together = ("group", "animal")
        indexes = [
            models.Index(fields=["group", "status"]),
            models.Index(fields=["animal", "status"]),
        ]
    def remove(self):
        """Soft remove animal from group"""
        from django.utils import timezone
        self.status = self.Status.REMOVED
        self.removed_at = timezone.now()
        self.save()
        

class AnimalEvent(models.Model):
    farm = models.ForeignKey(
        "organization.Farm",
        on_delete=models.CASCADE,
        related_name="animal_event_farms"
    )
    group = models.ForeignKey(
        AnimalGroup,
        on_delete=models.CASCADE,
        related_name="animal_event_groups"
    )
    animal = models.ForeignKey(
        "Animal",
        on_delete=models.CASCADE,
        related_name="animal_event_animals"
    )
    event_type = models.ForeignKey(
        "core.EventType",
        on_delete=models.PROTECT,
        related_name="events",
        db_index=True
    )
    event_date = models.DateTimeField(db_index=True)
    event_title = models.CharField(max_length=255)
    event_summary = models.TextField(blank=True, null=True)
    reference_table = models.CharField(max_length=100, null=True, blank=True)
    reference_id = models.IntegerField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-event_date"]
        indexes = [
        models.Index(fields=["farm", "animal"]),
        models.Index(fields=["farm", "group"]),
        models.Index(fields=["event_type"]),
        models.Index(fields=["event_date"]),
    ]

    def __str__(self):
        return f"{self.event_type.name} - {self.event_date}"