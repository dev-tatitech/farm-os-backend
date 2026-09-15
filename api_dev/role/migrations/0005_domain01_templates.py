from django.db import migrations

TEMPLATES = {
    "farm_manager": ("Farm Manager", True, True, {
        "view_animal_details", "add_animal_details", "update_animal_details",
        "view_health", "add_health", "record_health_observation", "manage_health_case",
        "view_feed", "add_feed", "view_reproduction", "add_reproduction",
        "view_operation", "create_operation", "assign_operation", "reassign_operation",
        "complete_operation", "cancel_operation", "view_farm", "view_farm_unit",
        "create_farm_unit", "update_farm_unit", "view_reports", "view_livestock_dashboard",
        "view_production",
    }),
    "veterinarian": ("Veterinarian", True, True, {
        "view_animal_details", "view_health", "add_health", "record_health_observation",
        "manage_health_case", "view_reproduction", "view_operation", "complete_operation",
    }),
    "field_worker": ("Field Worker", False, True, {
        "view_operation", "complete_operation", "view_animal_details", "record_health_observation",
    }),
}

GOVERNANCE = {
    "view_people", "manage_people", "invite_user", "view_user_profile",
    "manage_user_assignment", "deactivate_user", "reactivate_user",
    "view_roles", "create_role", "update_role", "manage_role_permissions",
}


def provision(apps, schema_editor):
    Organization = apps.get_model("organization", "Organization")
    Role = apps.get_model("role", "Role")
    Permission = apps.get_model("role", "Permission")
    RolePermission = apps.get_model("role", "RolePermission")
    # Existing custom roles previously served Web. Preserve that entitlement;
    # template collisions are deliberately not reinterpreted as defaults.
    Role.objects.filter(system_template_type__isnull=True).update(web_access=True)
    catalog = GOVERNANCE | {"view_farm"}
    for _, _, _, codes in TEMPLATES.values():
        catalog |= codes
    permissions = {}
    for code in sorted(catalog):
        permissions[code] = Permission.objects.filter(code=code).first() or Permission.objects.create(
            code=code, name=code.replace("_", " ").title(), module="access")
    for org in Organization.objects.all().iterator():
        for template, (name, web, mobile, codes) in TEMPLATES.items():
            row, created = Role.objects.get_or_create(
                organization=org, normalized_name=name.casefold(),
                defaults={"name": name, "code": template, "system_template_type": template,
                          "active": True, "web_access": web, "mobile_access": mobile})
            if created:
                RolePermission.objects.bulk_create(
                    [RolePermission(role=row, permission=permissions[c]) for c in sorted(codes)])


class Migration(migrations.Migration):
    dependencies = [
        ("role", "0004_role_active_role_mobile_access_and_more"),
        ("organization", "0003_organization_address_organization_email_and_more"),
    ]
    operations = [migrations.RunPython(provision, migrations.RunPython.noop)]
