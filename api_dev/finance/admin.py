from django.contrib import admin
from .models import TransactionCategory, Transaction, AnimalAcquisition, AnimalFinancialProfile


@admin.register(TransactionCategory)
class TransactionCategoryAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "type", "is_system", "is_active"]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["id", "farm", "type", "category", "amount", "transaction_date", "source_module"]
    list_filter = ["type", "source_module"]


@admin.register(AnimalAcquisition)
class AnimalAcquisitionAdmin(admin.ModelAdmin):
    list_display = ["id", "animal", "purchase_price", "estimated_opening_value"]


@admin.register(AnimalFinancialProfile)
class AnimalFinancialProfileAdmin(admin.ModelAdmin):
    list_display = ["id", "animal", "acquisition_cost", "opening_value", "current_estimated_value"]
