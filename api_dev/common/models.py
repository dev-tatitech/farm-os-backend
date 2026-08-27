from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class AuditLog(models.Model):
    """
    Generic audit trail for override/approval actions that need a recorded
    reason and before/after state (spec 13) — used where a dedicated history
    model doesn't already exist for the action (lifecycle overrides already
    have AnimalLifecycleHistory, for example, so they don't duplicate here).
    """
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs")
    action = models.CharField(max_length=100)
    source_module = models.CharField(max_length=50)
    object_type = models.CharField(max_length=100, null=True, blank=True)
    object_id = models.CharField(max_length=64, null=True, blank=True)
    previous_value = models.TextField(null=True, blank=True)
    new_value = models.TextField(null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["object_type", "object_id"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self):
        return f"{self.action} - {self.object_type}:{self.object_id} by {self.user_id}"
