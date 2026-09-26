from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0003_notification_notification_type_and_more")]

    operations = [
        migrations.AddField(
            model_name="idempotencykey",
            name="request_fingerprint",
            field=models.CharField(default="", max_length=64),
        ),
    ]
