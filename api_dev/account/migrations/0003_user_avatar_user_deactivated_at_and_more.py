from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0002_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "UPDATE account_user SET account_status = 'active' WHERE account_status IN ('Active', 'active');",
                "UPDATE account_user SET account_status = 'invited' WHERE account_status = 'inactive';",
                "UPDATE account_user SET account_status = 'deactivated' WHERE account_status IN ('Suspended', 'Deleted', 'deactivated');",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddField(
            model_name="user",
            name="avatar",
            field=models.ImageField(blank=True, null=True, upload_to="users/avatars/"),
        ),
        migrations.AddField(
            model_name="user",
            name="deactivated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="deactivation_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="user",
            name="phone",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AlterField(
            model_name="user",
            name="account_status",
            field=models.CharField(
                choices=[
                    ("invited", "Invited"),
                    ("active", "Active"),
                    ("deactivated", "Deactivated"),
                ],
                default="active",
                max_length=50,
            ),
        ),
    ]
