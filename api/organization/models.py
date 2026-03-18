from django.db import models
from core.models import TimeStampedModel
from django.contrib.auth import get_user_model
from account.models import Country, AdminLevel1, AdminLevel2
import uuid
User = get_user_model()



class Industry(models.Model):
    short_nme = models.CharField(max_length=100)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Organization(TimeStampedModel):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("suspended", "Suspended"),
        ("trial", "Trial"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    industry_type = models.ForeignKey(
        Industry, null=True, blank=True, on_delete=models.SET_NULL
    )
    country  = models.ForeignKey(
        Country, null=True, blank=True, on_delete=models.SET_NULL
    )
    state_region  = models.ForeignKey(
        AdminLevel1, null=True, blank=True, on_delete=models.SET_NULL
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="trial")


class Farm(TimeStampedModel):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="farms"
    )
    name = models.CharField(max_length=255)
    farm_code = models.CharField(max_length=50)
    country  = models.ForeignKey(
        Country, null=True, blank=True, on_delete=models.SET_NULL
    )
    state_region  = models.ForeignKey(
        AdminLevel1, null=True, blank=True, on_delete=models.SET_NULL
    )
    city = models.CharField(max_length=100, blank=True)
    location_address = models.TextField(blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    farm_type = models.CharField(max_length=50)
    is_primary = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="active")

