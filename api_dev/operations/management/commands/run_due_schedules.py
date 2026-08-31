from django.core.management.base import BaseCommand

from operations.services import process_due_schedules


class Command(BaseCommand):
    help = "Create tasks for due recurring operation schedules. Safe to run every minute."

    def handle(self, *args, **options):
        created = process_due_schedules()
        self.stdout.write(self.style.SUCCESS(f"Generated {created} schedule occurrence(s)."))
