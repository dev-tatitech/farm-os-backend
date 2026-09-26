"""Domain 01 Farm lifecycle guards required by the locked D02 history rules."""
from django.db.models.deletion import ProtectedError
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Farm


@receiver(pre_delete, sender=Farm)
def prevent_farm_history_deletion(sender, instance, **kwargs):
    # Signals cover QuerySet.delete() as well as instance.delete(). Imports are
    # intentionally deferred so the organization app remains independent of
    # Operations model initialization.
    from animals.models import AnimalEvent
    from operations.models import Task, TaskSchedule

    protected = [
        model for model in (Task, TaskSchedule, AnimalEvent)
        if model.objects.filter(farm_id=instance.pk).exists()
    ]
    if protected:
        raise ProtectedError(
            "A Farm with authoritative operational history must be deactivated, not deleted.",
            protected,
        )
