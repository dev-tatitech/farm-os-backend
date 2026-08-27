from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Task(TimeStampedModel):
    class Type(models.TextChoices):
        VACCINATION = "vaccination", "Vaccination"
        TREATMENT = "treatment", "Treatment"
        FEED_ISSUANCE = "feed_issuance", "Feed issuance"
        SALE = "sale", "Sale"
        MOVEMENT = "movement", "Movement"
        OBSERVATION = "observation", "Health observation"
        GENERIC = "generic", "Generic"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ASSIGNED = "assigned", "Assigned"
        ACCEPTED = "accepted", "Accepted"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    organization = models.ForeignKey(
        "organization.Organization", on_delete=models.CASCADE, related_name="tasks"
    )
    farm = models.ForeignKey(
        "organization.Farm", on_delete=models.CASCADE, related_name="tasks"
    )
    animal = models.ForeignKey(
        "animals.Animal",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tasks",
    )
    group = models.ForeignKey(
        "animals.AnimalGroup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tasks",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="follow_ups",
    )
    schedule = models.ForeignKey(
        "TaskSchedule",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tasks",
    )
    task_type = models.CharField(max_length=32, choices=Type.choices)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    priority = models.CharField(
        max_length=16, choices=Priority.choices, default=Priority.NORMAL
    )
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_tasks",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_tasks",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    completion_payload = models.JSONField(null=True, blank=True)
    result_reference_table = models.CharField(max_length=100, blank=True)
    result_reference_id = models.IntegerField(null=True, blank=True)
    cancel_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["due_at", "-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["farm", "status"]),
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["task_type", "status"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.status})"

    @property
    def is_open(self):
        return self.status not in (self.Status.COMPLETED, self.Status.CANCELLED)


class TaskAssignment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        SUPERSEDED = "superseded", "Superseded"

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="assignments")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="task_assignments"
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="issued_task_assignments",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-assigned_at"]
        indexes = [models.Index(fields=["task", "status"])]


class TaskEvidence(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="evidence")
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)


class TaskSchedule(TimeStampedModel):
    class Recurrence(models.TextChoices):
        ONCE = "once", "Once"
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"

    organization = models.ForeignKey(
        "organization.Organization", on_delete=models.CASCADE, related_name="task_schedules"
    )
    farm = models.ForeignKey(
        "organization.Farm", on_delete=models.CASCADE, related_name="task_schedules"
    )
    animal = models.ForeignKey(
        "animals.Animal", null=True, blank=True, on_delete=models.SET_NULL
    )
    group = models.ForeignKey(
        "animals.AnimalGroup", null=True, blank=True, on_delete=models.SET_NULL
    )
    task_type = models.CharField(max_length=32, choices=Task.Type.choices)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    recurrence = models.CharField(
        max_length=16, choices=Recurrence.choices, default=Recurrence.ONCE
    )
    next_run_at = models.DateTimeField(db_index=True)
    is_active = models.BooleanField(default=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="task_schedules",
    )
    template_payload = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ["next_run_at"]


class Notification(models.Model):
    class Category(models.TextChoices):
        TASK = "task", "Task"
        EVENT = "event", "Event"
        SYSTEM = "system", "System"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    organization = models.ForeignKey(
        "organization.Organization", on_delete=models.CASCADE, related_name="notifications"
    )
    farm = models.ForeignKey(
        "organization.Farm",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    category = models.CharField(
        max_length=16, choices=Category.choices, default=Category.SYSTEM
    )
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    reference_table = models.CharField(max_length=100, blank=True)
    reference_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["organization", "created_at"]),
        ]


class IdempotencyKey(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="idempotency_keys"
    )
    key = models.CharField(max_length=128)
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=255)
    status_code = models.PositiveIntegerField(null=True, blank=True)
    response_json = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "key"], name="unique_user_idempotency_key")
        ]
        indexes = [models.Index(fields=["created_at"])]
