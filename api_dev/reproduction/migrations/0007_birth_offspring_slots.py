from django.db import migrations, models
import django.db.models.deletion


def number_existing_slots(apps, schema_editor):
    BirthOffspringRecord = apps.get_model("reproduction", "BirthOffspringRecord")
    current_birth = None
    sequence = 0
    for row in BirthOffspringRecord.objects.order_by("birth_record_id", "id"):
        if row.birth_record_id != current_birth:
            current_birth = row.birth_record_id
            sequence = 0
        sequence += 1
        row.offspring_sequence = sequence
        row.registration_status = "registered" if row.offspring_animal_id else "registration_required"
        row.save(update_fields=["offspring_sequence", "registration_status"])


class Migration(migrations.Migration):

    dependencies = [
        ("reproduction", "0006_breedingeligibilityrule"),
    ]

    operations = [
        migrations.AddField(
            model_name="birthoffspringrecord",
            name="offspring_sequence",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="birthoffspringrecord",
            name="registration_status",
            field=models.CharField(
                choices=[
                    ("registration_required", "Registration required"),
                    ("registered", "Registered"),
                    ("deceased", "Deceased"),
                ],
                default="registration_required",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="birthoffspringrecord",
            name="offspring_animal",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="birth_links",
                to="animals.animal",
            ),
        ),
        migrations.AlterField(
            model_name="birthoffspringrecord",
            name="gender",
            field=models.CharField(blank=True, choices=[("male", "Male"), ("female", "Female")], max_length=10),
        ),
        migrations.RunPython(number_existing_slots, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="birthoffspringrecord",
            constraint=models.UniqueConstraint(
                fields=("birth_record", "offspring_sequence"),
                name="unique_birth_offspring_sequence",
            ),
        ),
    ]
