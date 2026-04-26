from django.contrib import admin
from .models import InseminationRecord, PregnancyRecord
# Register your models here.
@admin.register(InseminationRecord)
class InseminationRecordAdmin(admin.ModelAdmin):
    list_display = [field.name for field in InseminationRecord._meta.fields]

@admin.register(PregnancyRecord)
class PregnancyRecordAdmin(admin.ModelAdmin):
    list_display = [field.name for field in PregnancyRecord._meta.fields]
