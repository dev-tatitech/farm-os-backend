from django.contrib import admin
from .models import (
    Subscription,
    Payment
)
# Register your models here.
@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Subscription._meta.fields]

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Payment._meta.fields]
