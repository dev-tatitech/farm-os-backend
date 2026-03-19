from django.contrib import admin
from .models import (
    Role,RolePermission,UserRole,Permission
)
# Register your models here.
@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Role._meta.fields]

@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = [field.name for field in RolePermission._meta.fields]

@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = [field.name for field in UserRole._meta.fields]

@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Permission._meta.fields]
