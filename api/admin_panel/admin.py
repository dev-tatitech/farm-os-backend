from django.contrib import admin
from .models import Species, Breed, UnitType
@admin.register(Species)
class SpeciesAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Species._meta.fields]

@admin.register(Breed)
class BreedAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Breed._meta.fields]

@admin.register(UnitType)
class UnitTypeAdmin(admin.ModelAdmin):
    list_display = [field.name for field in UnitType._meta.fields]
