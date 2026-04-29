from django.contrib import admin
from .models import FeedInventory, FeedPlan, FeedIssuanceRecord
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
