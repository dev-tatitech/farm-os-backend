from django.contrib import admin
from .models import TransactionCategory, Transaction


@admin.register(TransactionCategory)
class TransactionCategoryAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "type", "is_system", "is_active"]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["id", "farm", "type", "category", "amount", "transaction_date", "source_module"]
    list_filter = ["type", "source_module"]
