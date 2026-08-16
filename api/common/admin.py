from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["id", "action", "source_module", "object_type", "object_id", "user", "created_at"]
    list_filter = ["action", "source_module"]
    readonly_fields = [f.name for f in AuditLog._meta.fields]
