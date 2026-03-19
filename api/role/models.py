from django.db import models
from core.models import TimeStampedModel
# Create your models here.
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
    user = models.ForeignKey("account.User", on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    farm = models.ForeignKey("organization.Farm", null=True, blank=True, on_delete=models.SET_NULL)
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
    "account.User",
    null=True,
    on_delete=models.SET_NULL,
    related_name="assigned_roles"
)
class RolePermission(TimeStampedModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)
   