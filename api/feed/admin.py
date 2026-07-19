from django.contrib import admin
from .models import (
    FeedInventory,
    FeedPlan,
    FeedIssuanceRecord,
    FeedCategory,
    FeedUnit,
    FeedType,
)
# Register your models here.
@admin.register(FeedInventory)
class FeedInventoryAdmin(admin.ModelAdmin):
    list_display = [field.name for field in FeedInventory._meta.fields]

@admin.register(FeedPlan)
class FeedPlanAdmin(admin.ModelAdmin):
    list_display = [field.name for field in FeedPlan._meta.fields]

@admin.register(FeedIssuanceRecord)
class FeedIssuanceRecordAdmin(admin.ModelAdmin):
    list_display = [field.name for field in FeedIssuanceRecord._meta.fields]

@admin.register(FeedCategory)
class FeedCategoryAdmin(admin.ModelAdmin):
    list_display = [field.name for field in FeedCategory._meta.fields]

@admin.register(FeedUnit)
class FeedUnitAdmin(admin.ModelAdmin):
    list_display = [field.name for field in FeedUnit._meta.fields]

@admin.register(FeedType)
class FeedTypeAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "category", "farm", "is_system", "is_active"]
