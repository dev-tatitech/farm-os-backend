from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("animals", "0002_animalevent_actor_display_snapshot_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterUniqueTogether(name="animalgroupmember", unique_together=set()),
        migrations.AddConstraint(
            model_name="animalgroupmember",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "ACTIVE")),
                fields=("group", "animal"),
                name="unique_active_animal_group_membership",
            ),
        ),
        migrations.CreateModel(
            name="FarmLabel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("color", models.CharField(blank=True, max_length=16)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("farm", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="labels", to="organization.farm")),
            ],
            options={"ordering": ["name", "id"]},
        ),
        migrations.AddConstraint(model_name="farmlabel", constraint=models.UniqueConstraint(fields=("farm", "name"), name="unique_farm_label_name")),
        migrations.CreateModel(
            name="AnimalMedia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.ImageField(upload_to="animals/gallery/")),
                ("note", models.TextField(blank=True)),
                ("is_primary", models.BooleanField(default=False)),
                ("captured_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("animal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="media", to="animals.animal")),
                ("uploaded_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="animal_media_uploaded", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-is_primary", "-created_at", "-id"]},
        ),
        migrations.AddConstraint(model_name="animalmedia", constraint=models.UniqueConstraint(condition=models.Q(("is_primary", True)), fields=("animal",), name="one_primary_animal_media")),
        migrations.CreateModel(
            name="AnimalLabel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("assigned_at", models.DateTimeField(auto_now_add=True)),
                ("animal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="label_assignments", to="animals.animal")),
                ("assigned_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="animal_labels_assigned", to=settings.AUTH_USER_MODEL)),
                ("label", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="animal_assignments", to="animals.farmlabel")),
            ],
        ),
        migrations.AddConstraint(model_name="animallabel", constraint=models.UniqueConstraint(fields=("animal", "label"), name="unique_animal_label")),
    ]
