from django.db import migrations, models


def normalize_role_names(apps, schema_editor):
    Role = apps.get_model("role", "Role")
    for role in Role.objects.all().iterator():
        role.normalized_name = " ".join(role.name.split()).casefold()
        role.save(update_fields=["normalized_name"])


class Migration(migrations.Migration):
    dependencies = [
        ("role", "0002_role_normalized_name_userrole_revoked_at_and_more"),
    ]

    operations = [
        migrations.RunPython(normalize_role_names, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="role",
            constraint=models.UniqueConstraint(
                fields=("organization", "normalized_name"),
                name="unique_role_name_per_organization",
            ),
        ),
    ]
