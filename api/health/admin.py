from django.contrib import admin
from .models import MortalityRecord, TreatmentRecord, VaccinationRecord
# Register your models here.
@admin.register(MortalityRecord)
class MortalityRecordAdmin(admin.ModelAdmin):
    list_display = [field.name for field in MortalityRecord._meta.fields]

@admin.register(TreatmentRecord)
class TreatmentRecordAdmin(admin.ModelAdmin):
    list_display = [field.name for field in TreatmentRecord._meta.fields]


@admin.register(VaccinationRecord)
class VaccinationRecordAdmin(admin.ModelAdmin):
    list_display = [field.name for field in VaccinationRecord._meta.fields]
    
