from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0004_idempotencykey_request_fingerprint")]
    operations = [
        migrations.AddField(model_name="taskschedule", name="starts_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="taskschedule", name="ends_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="taskschedule", name="priority", field=models.CharField(choices=[("low", "Low"), ("normal", "Normal"), ("high", "High"), ("critical", "Critical")], default="normal", max_length=16)),
    ]
