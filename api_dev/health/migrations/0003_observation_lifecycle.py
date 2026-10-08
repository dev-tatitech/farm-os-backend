from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("health", "0002_repair_health_schema"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="healthobservation", name="status", field=models.CharField(choices=[("open", "Open"), ("acknowledged", "Acknowledged"), ("assessed", "Assessed"), ("resolved", "Resolved"), ("escalated_to_health_case", "Escalated to health case")], db_index=True, default="open", max_length=32)),
        migrations.AddField(model_name="healthobservation", name="assessment_note", field=models.TextField(blank=True)),
        migrations.AddField(model_name="healthobservation", name="assessed_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="healthobservation", name="assessed_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assessed_health_observations", to=settings.AUTH_USER_MODEL)),
    ]
