from django.contrib import admin
from subcriptions.models import Payment, SubscriptionPlan, Subscription
# Register your models here.
@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = [field.name for field in SubscriptionPlan._meta.fields]

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Subscription._meta.fields]

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Payment._meta.fields]
