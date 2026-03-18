from django.db import models
from core.models import TimeStampedModel
import uuid
from django.conf import settings
from django.utils import timezone

# Create your models here.
class SubscriptionPlan(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50)
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    annual_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_users = models.IntegerField(default=2)
    max_farms = models.IntegerField(default=1)
    max_batches = models.IntegerField(default=1)
    features_json = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=20, default="active")


class Subscription(models.Model):
    BILLING_CHOICES = (
        ("monthly", "Monthly"),
        ("annual", "Annual"),
    )

    STATUS_CHOICES = (
        ("active", "Active"),
        ("expired", "Expired"),
        ("cancelled", "Cancelled"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT)
    organization = models.ForeignKey(
        "organization.Organization", on_delete=models.CASCADE, related_name="subs"
    )
    billing_cycle = models.CharField(max_length=10, choices=BILLING_CHOICES)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    auto_renew = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-end_date']
  
    def __str__(self):
        return f" - {self.plan.name}"

    def is_expired(self):
        return timezone.now() > self.end_date

    def remaining_days(self):
        return max((self.end_date - timezone.now()).days, 0)
    
class Payment(models.Model):

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    )
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="NGN")
    is_payment_verified = models.BooleanField(default=False)
    # Paystack fields
    reference = models.CharField(
        max_length=100, unique=True, help_text="Paystack payment reference"
    )
    paystack_transaction_id = models.CharField(max_length=100, blank=True, null=True)
    channel = models.CharField(
        max_length=50, blank=True, null=True, help_text="card, bank, ussd, qr, etc."
    )
    paid_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"- {self.amount}"