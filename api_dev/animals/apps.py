from django.apps import AppConfig


class AnimalsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "animals"
    def ready(self):
        # register signal handlers
        try:
            from . import signals  # noqa: F401
        except Exception:
            pass
