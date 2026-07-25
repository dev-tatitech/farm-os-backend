from django.contrib import admin
from .models import Animal, AnimalEvent, AnimalWeight, AnimalAcquisition
# Register your models here.
@admin.register(Animal)
class AnimalAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Animal._meta.fields]

@admin.register(AnimalEvent)
class AnimalEventAdmin(admin.ModelAdmin):
    list_display = [field.name for field in AnimalEvent._meta.fields]

@admin.register(AnimalWeight)
class AnimalWeightAdmin(admin.ModelAdmin):
    list_display = [field.name for field in AnimalWeight._meta.fields]

@admin.register(AnimalAcquisition)
class AnimalAcquisitionAdmin(admin.ModelAdmin):
    list_display = ["id", "animal", "purchase_price", "estimated_opening_value"]
