from django.contrib import admin
from .models import Animal, AnimalEvent
# Register your models here.
@admin.register(Animal)
class AnimalAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Animal._meta.fields]

@admin.register(AnimalEvent)
class AnimalEventAdmin(admin.ModelAdmin):
    list_display = [field.name for field in AnimalEvent._meta.fields]
