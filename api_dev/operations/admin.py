from django.contrib import admin

from .models import IdempotencyKey, Notification, Task, TaskAssignment, TaskSchedule


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "task_type", "status", "farm", "assigned_to", "due_at")
    list_filter = ("task_type", "status", "priority")
    search_fields = ("title",)


@admin.register(TaskAssignment)
class TaskAssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "task", "user", "status", "assigned_at")


@admin.register(TaskSchedule)
class TaskScheduleAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "task_type", "recurrence", "next_run_at", "is_active")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "title", "is_read", "created_at")


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "key", "status_code", "created_at")
