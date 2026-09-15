"""Provision defaults once; subsequent edits remain organization-owned."""
from common.access import GOVERNANCE_CODES, OPERATION_CODES

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


def provision_templates(org, apps=None):
    if apps is None:
        from django.apps import apps
    Role = apps.get_model("role", "Role")
    Permission = apps.get_model("role", "Permission")
    RolePermission = apps.get_model("role", "RolePermission")
    catalog = GOVERNANCE_CODES | OPERATION_CODES | {"record_health_observation", "manage_health_case", "view_farm"}
    for _, _, _, codes in TEMPLATES.values():
        catalog |= codes
    permissions = {}
    for code in sorted(catalog):
        permissions[code] = Permission.objects.filter(code=code).first() or Permission.objects.create(
            code=code, name=code.replace("_", " ").title(), module="access" if code in GOVERNANCE_CODES else "operations",
        )
    for template, (name, web, mobile, codes) in TEMPLATES.items():
        role, created = Role.objects.get_or_create(
            organization=org, normalized_name=name.casefold(),
            defaults={"name": name, "code": template, "system_template_type": template,
                      "active": True, "web_access": web, "mobile_access": mobile},
        )
        if created:
            RolePermission.objects.bulk_create([RolePermission(role=role, permission=permissions[c]) for c in sorted(codes)])
