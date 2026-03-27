from django.db import models

# Create your models here.
from django.db import models
from organization.models import Organization, Farm
from core.models import TimeStampedModel


class FarmUnit(TimeStampedModel):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]

    UNIT_TYPE_CHOICES = [
        ("pen", "Pen"),
        ("barn", "Barn"),
        ("pond", "Pond"),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50)
    unit_type = models.ForeignKey("admin_panel.UnitType", null=True, blank=True, on_delete=models.SET_NULL, related_name="farm_unit")
    capacity = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

