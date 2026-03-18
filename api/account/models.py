from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid
from django.core.exceptions import ValidationError
from .helper import generate_unique_filename
from core.models import TimeStampedModel
# Create your models here.

class Country(models.Model):
    name = models.CharField(max_length=100)
    def __str__(self):
        return self.name

def default_timezone(instance):
    if instance.country.name == "Nigeria":
        return "Africa/Lagos"
    elif instance.country.name == "US":
        return "America/New_York"  
    else:
        return "UTC"
class AdminLevel1(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="countries")
    name = models.CharField(max_length=100)
    timezone = models.CharField(max_length=50, blank=True, null=True) 

    def __str__(self):
        return self.name

class AdminLevel2(models.Model):
    name = models.CharField(max_length=100)
    admin_level1 = models.ForeignKey(AdminLevel1, on_delete=models.CASCADE, related_name="admin_level1")
    def __str__(self):
        return self.name
class User(AbstractUser):
    ACCOUNT_STATUS_CHOICES = [
        ("Active", "Active"),
        ("Suspended", "Suspended"),
        ("Deleted", "Deleted"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    csrf_token = models.CharField(max_length=100, blank=True, null=True)
    account_status = models.CharField(
        max_length=50, choices=ACCOUNT_STATUS_CHOICES, default="Active"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]


    def __str__(self):
        return self.username
    
class EmailValidation(models.Model):
    email = models.EmailField(unique=True)
    code = models.CharField(max_length=6)  # 6-digit OTP
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)


class RefreshSession(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="refresh_sessions"
    )
    token_hash = models.CharField(max_length=256, unique=True)
    user_agent = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"RefreshSession(user={self.user.username}, active={self.is_active})"

class Role(TimeStampedModel):
    organization = models.ForeignKey(
        "organization.Organization",
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50)
    description = models.TextField(blank=True)


class Permission(models.Model):
    code = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    module = models.CharField(max_length=100)
    description = models.TextField(blank=True)


class UserRole(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    farm = models.ForeignKey("organization.Farm", null=True, blank=True, on_delete=models.SET_NULL)
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.IntegerField(null=True)


class RolePermission(TimeStampedModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)
    