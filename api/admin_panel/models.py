from django.db import models


class Species(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50)


class Breed(models.Model):
    species = models.ForeignKey(Species, on_delete=models.CASCADE, related_name="breeds")
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50)


class UnitType(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50)


# ─── Livestock Master Data ────────────────────────────────────────────────────

class LivestockSpecies(models.Model):
    CATEGORY_CHOICES = [
        ("ruminant", "Ruminant"),
        ("monogastric", "Monogastric"),
        ("small_livestock", "Small Livestock"),
        ("equine", "Equine"),
        ("camelid", "Camelid"),
    ]
    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Livestock Species"

    def __str__(self):
        return self.name


class LivestockBreed(models.Model):
    species = models.ForeignKey(
        LivestockSpecies, on_delete=models.CASCADE, related_name="livestock_breeds"
    )
    farm = models.ForeignKey(
        "organization.Farm",
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="custom_breeds",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    origin = models.CharField(max_length=100, blank=True, null=True)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["species", "farm", "name"],
                name="unique_breed_per_species_farm",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.species.name})"


class HousingUnitType(models.Model):
    species = models.ForeignKey(
        LivestockSpecies, on_delete=models.CASCADE, related_name="housing_unit_types"
    )
    name = models.CharField(max_length=100)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["species", "name"],
                name="unique_housing_unit_type_per_species",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.species.name})"


class FarmHousingUnit(models.Model):
    STATUS_CHOICES = [("active", "Active"), ("inactive", "Inactive")]

    farm = models.ForeignKey(
        "organization.Farm", on_delete=models.CASCADE, related_name="housing_units"
    )
    unit_type = models.ForeignKey(
        HousingUnitType, on_delete=models.PROTECT, related_name="farm_units"
    )
    name = models.CharField(max_length=200)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    allowed_species = models.ManyToManyField(
        LivestockSpecies, related_name="housing_units", blank=True
    )
    location = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.farm})"

    @property
    def occupancy(self):
        return self.animals.filter(is_active=True).count()


class AnimalClassification(models.Model):
    SEX_CHOICES = [("male", "Male"), ("female", "Female")]

    species = models.ForeignKey(
        LivestockSpecies, on_delete=models.CASCADE, related_name="classifications"
    )
    sex = models.CharField(max_length=10, choices=SEX_CHOICES)
    name = models.CharField(max_length=100)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["species", "sex", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["species", "sex", "name"],
                name="unique_classification_per_species_sex",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.species.name} / {self.sex})"


# ─── Contact Enquiry ─────────────────────────────────────────────────────────

class ContactEnquiry(models.Model):
    FARM_TYPE_CHOICES = [
        ("livestock", "Livestock"),
        ("poultry", "Poultry"),
        ("fishery", "Fishery"),
        ("crop", "Crop"),
        ("mixed_farming", "Mixed Farming"),
        ("cooperative", "Cooperative"),
        ("government", "Government"),
        ("ngo", "NGO"),
        ("other", "Other"),
    ]
    FARM_SIZE_CHOICES = [
        ("small", "Small"),
        ("medium", "Medium"),
        ("large", "Large"),
        ("enterprise", "Enterprise"),
    ]
    RECORD_METHOD_CHOICES = [
        ("paper", "Paper"),
        ("excel", "Excel"),
        ("existing_software", "Existing Software"),
        ("combination", "Combination"),
        ("other", "Other"),
    ]
    CONTACT_METHOD_CHOICES = [
        ("phone", "Phone"),
        ("email", "Email"),
        ("whatsapp", "WhatsApp"),
    ]
    STATUS_CHOICES = [
        ("new", "New"),
        ("in_review", "In Review"),
        ("contacted", "Contacted"),
        ("converted", "Converted"),
        ("closed", "Closed"),
    ]

    full_name = models.CharField(max_length=200)
    farm_name = models.CharField(max_length=200, blank=True, null=True)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)
    farm_type = models.CharField(max_length=50, choices=FARM_TYPE_CHOICES, blank=True, null=True)
    farm_size = models.CharField(max_length=20, choices=FARM_SIZE_CHOICES, blank=True, null=True)
    record_method = models.CharField(max_length=30, choices=RECORD_METHOD_CHOICES, blank=True, null=True)
    modules_of_interest = models.JSONField(default=list, blank=True)
    challenges = models.TextField(blank=True, null=True)
    preferred_contact_method = models.CharField(max_length=20, choices=CONTACT_METHOD_CHOICES, blank=True, null=True)
    consultation_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Contact Enquiry"
        verbose_name_plural = "Contact Enquiries"

    def __str__(self):
        return f"{self.full_name} — {self.email} ({self.created_at.date()})"