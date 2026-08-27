from django.contrib import admin
from .models import MovementRecord, SalesRecord


@admin.register(MovementRecord)
class MovementRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "farm", "move_date", "created_by")
    list_filter = ("farm", "move_date")
    search_fields = ("reason",)


@admin.register(SalesRecord)
class SalesRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "farm", "animal", "buyer_name", "price", "sale_date")
    list_filter = ("farm", "sale_date")
    search_fields = ("buyer_name", "notes", "reason")
