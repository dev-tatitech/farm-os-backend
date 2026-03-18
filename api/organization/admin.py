from django.contrib import admin
from .models import (
                     Industry, 
                     Organization, 
                     Farm,
              
                     )

@admin.register(Industry)
class IndustryAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Industry._meta.fields]

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Organization._meta.fields]

@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Farm._meta.fields]

