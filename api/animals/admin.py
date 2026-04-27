from django.contrib import admin
from .models import Animal, AnimalEvent, AnimalWeight
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
