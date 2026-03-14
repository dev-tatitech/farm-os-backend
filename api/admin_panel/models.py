from django.db import models

# Create your models here.
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

    organization = models.ForeignKey(
        "organization.Organization",
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )
    plan = models.ForeignKey("organization.SubscriptionPlan", on_delete=models.CASCADE)
    billing_cycle = models.CharField(max_length=10, choices=BILLING_CHOICES)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    def __str__(self):
        return f"{self.user} - {self.plan}"
    
class Payment(models.Model):

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    )
    organization = models.ForeignKey(
        "organization.Organization",
        null=True,
        blank=True,
        on_delete=models.CASCADE
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
        return f"{self.user} - {self.amount}"