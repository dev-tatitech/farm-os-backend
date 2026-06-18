from django.contrib import admin
from .models import Alert


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("id", "farm", "alert_type", "priority", "status", "due_date", "created_at")
    list_filter = ("farm", "alert_type", "priority", "status")
    search_fields = ("title", "message", "reference_table")
