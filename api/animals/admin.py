from django.contrib import admin
from .models import Animal
# Register your models here.
@admin.register(Animal)
class AnimalAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Animal._meta.fields]
