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