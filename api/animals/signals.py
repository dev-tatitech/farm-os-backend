from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.apps import apps

from .models import Animal, MilkRecord


def recalc_dashboard_for_farm(farm_id):
    AnimalModel = apps.get_model("animals", "Animal")
    Dashboard = apps.get_model("animals", "AnimalDashboard")
    MovementSales = apps.get_model("movement_records", "SalesRecord")
    try:
        from django.shortcuts import get_object_or_404
    except Exception:
        get_object_or_404 = None

    total = AnimalModel.objects.filter(farm_id=farm_id).count()
    active = AnimalModel.objects.filter(farm_id=farm_id, is_active=True).count()
    healthy = AnimalModel.objects.filter(farm_id=farm_id, health_status=AnimalModel.HealthStatus.HEALTHY).count()
    lactating = AnimalModel.objects.filter(farm_id=farm_id, is_lactating=True).count()
    pregnant = AnimalModel.objects.filter(farm_id=farm_id, is_pregnant=True).count()
    sick = AnimalModel.objects.filter(farm_id=farm_id, health_status="sick").count()
    quarantine = AnimalModel.objects.filter(farm_id=farm_id, is_quarantine=True).count()
    deaths = AnimalModel.objects.filter(farm_id=farm_id, status="dead").count()
    sales = MovementSales.objects.filter(farm_id=farm_id).count()

    obj, created = Dashboard.objects.get_or_create(farm_id=farm_id)
    obj.total_animals = total
    obj.active = active
    obj.healthy = healthy
    obj.lactating = lactating
    obj.pregnant = pregnant
    obj.sick = sick
    obj.quarantine = quarantine
    obj.deaths = deaths
    obj.sales = sales
    obj.updated_at = timezone.now()
    obj.save()


@receiver(post_save, sender=Animal)
def animal_saved(sender, instance, created, **kwargs):
    if instance and instance.farm_id:
        recalc_dashboard_for_farm(instance.farm_id)


@receiver(post_delete, sender=Animal)
def animal_deleted(sender, instance, **kwargs):
    if instance and instance.farm_id:
        recalc_dashboard_for_farm(instance.farm_id)


# handle sales created/removed
@receiver(post_save)
def sales_or_other_saved(sender, instance, created, **kwargs):
    if sender._meta.label_lower == "movement_records.salesrecord":
        if instance and instance.farm_id:
            recalc_dashboard_for_farm(instance.farm_id)


@receiver(post_delete)
def sales_deleted(sender, instance, **kwargs):
    if sender._meta.label_lower == "movement_records.salesrecord":
        if instance and instance.farm_id:
            recalc_dashboard_for_farm(instance.farm_id)


def recalc_daily_milk_summary(farm_id, record_date):
    MilkRecordModel = apps.get_model("animals", "MilkRecord")
    DailyMilkSummary = apps.get_model("animals", "DailyMilkSummary")
    from django.db.models import Sum
    total = (
        MilkRecordModel.objects.filter(farm_id=farm_id, record_date=record_date)
        .aggregate(total=Sum("quantity"))["total"]
        or 0
    )
    obj, _ = DailyMilkSummary.objects.get_or_create(farm_id=farm_id, date=record_date)
    obj.total_litres = total
    obj.save()


@receiver(post_save, sender=MilkRecord)
def milk_record_saved(sender, instance, **kwargs):
    if instance and instance.farm_id and instance.record_date:
        recalc_daily_milk_summary(instance.farm_id, instance.record_date)


@receiver(post_delete, sender=MilkRecord)
def milk_record_deleted(sender, instance, **kwargs):
    if instance and instance.farm_id and instance.record_date:
        recalc_daily_milk_summary(instance.farm_id, instance.record_date)
