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
    normalized_name = models.CharField(max_length=100, blank=True)
    code = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    system_template_type = models.CharField(max_length=32, null=True, blank=True)
    active = models.BooleanField(default=True)
    web_access = models.BooleanField(default=False)
    mobile_access = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "normalized_name"],
                name="unique_role_name_per_organization",
            )
        ]

    def save(self, *args, **kwargs):
        self.normalized_name = " ".join(self.name.split()).casefold()
        super().save(*args, **kwargs)


class Permission(models.Model):
    code = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    module = models.CharField(max_length=100)
    description = models.TextField(blank=True)


class UserRole(models.Model):
    user = models.ForeignKey("account.User", on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    farm = models.ForeignKey("organization.Farm", null=True, blank=True, on_delete=models.SET_NULL)
    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    assigned_by = models.ForeignKey(
    "account.User",
    null=True,
    on_delete=models.SET_NULL,
    related_name="assigned_roles"
)
    status = models.CharField(max_length=16, default="active")
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        "account.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revoked_roles",
    )
class RolePermission(TimeStampedModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="roles_permission")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)
   
