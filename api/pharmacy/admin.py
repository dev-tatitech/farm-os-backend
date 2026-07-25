from django.contrib import admin
from .models import DrugCategory, Drug, DrugBatch


@admin.register(DrugCategory)
class DrugCategoryAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "is_system", "is_active"]


@admin.register(Drug)
class DrugAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "category", "farm", "is_system", "is_active"]


@admin.register(DrugBatch)
class DrugBatchAdmin(admin.ModelAdmin):
    list_display = ["id", "drug", "farm", "batch_number", "quantity_available", "expiry_date", "status"]
    list_filter = ["status"]
