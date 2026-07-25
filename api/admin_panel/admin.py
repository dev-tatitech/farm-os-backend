from django.contrib import admin
from .models import Species, Breed, UnitType, LifeStageDefinition, AnimalLifecycleHistory, WeightReferenceRange
@admin.register(Species)
class SpeciesAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Species._meta.fields]

@admin.register(Breed)
class BreedAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Breed._meta.fields]

@admin.register(UnitType)
class UnitTypeAdmin(admin.ModelAdmin):
    list_display = [field.name for field in UnitType._meta.fields]

@admin.register(LifeStageDefinition)
class LifeStageDefinitionAdmin(admin.ModelAdmin):
    list_display = ["id", "species", "name", "order", "min_age_months", "max_age_months", "is_active"]

@admin.register(AnimalLifecycleHistory)
class AnimalLifecycleHistoryAdmin(admin.ModelAdmin):
    list_display = ["id", "animal", "previous_stage", "new_stage", "is_override", "changed_at"]

@admin.register(WeightReferenceRange)
class WeightReferenceRangeAdmin(admin.ModelAdmin):
    list_display = ["id", "species", "min_age_months", "max_age_months", "min_weight_kg", "max_weight_kg"]
