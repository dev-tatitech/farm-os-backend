from django.db import models
from organization.models import Farm


class Alert(models.Model):
    class AlertType(models.TextChoices):
        VACCINATION_DUE = "vaccination_due", "Vaccination Due"
        PREGNANCY_DUE = "pregnancy_due", "Pregnancy Due"
        FEED_VARIANCE = "feed_variance", "Feed Variance"
        TREATMENT_FOLLOW_UP = "treatment_follow_up", "Treatment Follow-up"

    class Priority(models.TextChoices):
        CRITICAL = "critical", "Critical"
        WARNING = "warning", "Warning"
        INFO = "info", "Info"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="alerts")
    alert_type = models.CharField(max_length=32, choices=AlertType.choices)
    priority = models.CharField(max_length=16, choices=Priority.choices)
    reference_table = models.CharField(max_length=100, null=True, blank=True)
    reference_id = models.PositiveIntegerField(null=True, blank=True)
    title = models.CharField(max_length=255)
    message = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    due_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Alert"
        verbose_name_plural = "Alerts"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.alert_type})"
