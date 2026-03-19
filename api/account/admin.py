from django.contrib import admin
from .models import  (User,EmailValidation,
                      Country,AdminLevel1,AdminLevel2,
                )
# Register your models here.


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Country._meta.fields]

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = [field.name for field in User._meta.fields]


@admin.register(AdminLevel1)
class AdminLevel1Admin(admin.ModelAdmin):
    list_display = [field.name for field in AdminLevel1._meta.fields]

@admin.register(AdminLevel2)
class AdminLevel2Admin(admin.ModelAdmin):
    list_display = [field.name for field in AdminLevel2._meta.fields]

@admin.register(EmailValidation)
class EmailValidationAdmin(admin.ModelAdmin):
    list_display = [field.name for field in EmailValidation._meta.fields]
