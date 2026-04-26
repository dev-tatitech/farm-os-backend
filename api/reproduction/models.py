from django.db import models
from django.core.exceptions import ValidationError
from datetime import timedelta
from django.contrib.auth import get_user_model
User = get_user_model()

class InseminationRecord(models.Model):
    METHOD_CHOICES = [
        ("natural", "Natural"),
        ("artificial", "Artificial"),
    ]
    farm = models.ForeignKey("organization.Farm", on_delete=models.CASCADE)
    animal = models.ForeignKey("animals.Animal", on_delete=models.CASCADE)
    service_date = models.DateField()
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    sire_reference = models.CharField(max_length=255, null=True, blank=True)
    technician_name = models.CharField(max_length=255, null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
    User,
    on_delete=models.SET_NULL,
    null=True
)
    def clean(self):
        if self.animal and self.animal.gender != "female":
            raise ValidationError("Insemination can only be performed on female animals.")
        if self.animal and self.animal.is_pregnant:
            raise ValidationError("This animal is already pregnant.")
        if self.method == "artificial" and not self.sire_reference:
            raise ValidationError("Sire reference is required for artificial insemination.")
    def save(self, *args, **kwargs):
        self.full_clean()  
        super().save(*args, **kwargs)
    def __str__(self):
        return f"{self.animal} - {self.service_date}"
    
class PregnancyRecord(models.Model):
    RESULT_CHOICES = [
        ('pregnant', 'Pregnant'),
        ('not_pregnant', 'Not Pregnant'),
    ]
    farm = models.ForeignKey("organization.Farm", on_delete=models.CASCADE)
    animal = models.ForeignKey("animals.Animal", on_delete=models.CASCADE)
    insemination = models.ForeignKey(
        InseminationRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pregnancy_records'
    )
    check_date = models.DateField()
    result = models.CharField(
        max_length=20,
        choices=RESULT_CHOICES
    )
    expected_delivery_date = models.DateField(
        null=True,
        blank=True
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "animal"],
                name="unique_pregnancy_per_animal_per_farm"
            )
        ]
    def clean(self):
        if self.result == 'pregnant' and not self.expected_delivery_date:
            raise ValidationError("Expected delivery date is required if result is pregnant.")
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
        if self.result == 'pregnant':
            self.animal.is_pregnant = True
            self.animal.save()