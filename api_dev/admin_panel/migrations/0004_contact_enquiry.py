from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("admin_panel", "0003_livestock_master_data"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContactEnquiry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("full_name", models.CharField(max_length=200)),
                ("farm_name", models.CharField(blank=True, max_length=200, null=True)),
                ("email", models.EmailField(max_length=254)),
                ("phone", models.CharField(blank=True, max_length=50, null=True)),
                ("country", models.CharField(blank=True, max_length=100, null=True)),
                ("region", models.CharField(blank=True, max_length=100, null=True)),
                ("farm_type", models.CharField(
                    blank=True, max_length=50, null=True,
                    choices=[
                        ("livestock", "Livestock"), ("poultry", "Poultry"),
                        ("fishery", "Fishery"), ("crop", "Crop"),
                        ("mixed_farming", "Mixed Farming"), ("cooperative", "Cooperative"),
                        ("government", "Government"), ("ngo", "NGO"), ("other", "Other"),
                    ],
                )),
                ("farm_size", models.CharField(
                    blank=True, max_length=20, null=True,
                    choices=[
                        ("small", "Small"), ("medium", "Medium"),
                        ("large", "Large"), ("enterprise", "Enterprise"),
                    ],
                )),
                ("record_method", models.CharField(
                    blank=True, max_length=30, null=True,
                    choices=[
                        ("paper", "Paper"), ("excel", "Excel"),
                        ("existing_software", "Existing Software"),
                        ("combination", "Combination"), ("other", "Other"),
                    ],
                )),
                ("modules_of_interest", models.JSONField(blank=True, default=list)),
                ("challenges", models.TextField(blank=True, null=True)),
                ("preferred_contact_method", models.CharField(
                    blank=True, max_length=20, null=True,
                    choices=[("phone", "Phone"), ("email", "Email"), ("whatsapp", "WhatsApp")],
                )),
                ("consultation_date", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(
                    default="new", max_length=20,
                    choices=[
                        ("new", "New"), ("in_review", "In Review"),
                        ("contacted", "Contacted"), ("converted", "Converted"),
                        ("closed", "Closed"),
                    ],
                )),
                ("notes", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Contact Enquiry",
                "verbose_name_plural": "Contact Enquiries",
                "ordering": ["-created_at"],
            },
        ),
    ]
