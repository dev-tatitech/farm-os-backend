"""Domain 01 authority, evaluated from current assignments, never role labels."""
from django.db.models import Q

from organization.models import Farm
from role.models import Permission, RolePermission, UserRole


GOVERNANCE_CODES = {
    "view_people", "manage_people", "invite_user", "view_user_profile",
    "manage_user_assignment", "deactivate_user", "reactivate_user",
    "view_roles", "create_role", "update_role", "manage_role_permissions",
}
OPERATION_CODES = {
    "view_operation", "create_operation", "assign_operation", "reassign_operation",
    "complete_operation", "cancel_operation",
}
# Existing public capability names map to existing domain permissions only where
# the meanings agree. Observation and case management must remain independent.
ALIASES = {
    "record_health": {"add_health"},
    "record_health_observation": set(),
    "manage_health_case": set(),
    "record_feed_activity": {"add_feed"},
    "view_farm": {"view_farm_profile"},
}


def organization_for(user):
    return user.organization or user.organizations.first()


def owner(user, org):
    return org is not None and str(org.user_id) == str(user.id)


def assignments(user, org):
    return UserRole.objects.filter(
        user=user, user__organization=org, status="active", role__active=True,
        role__organization=org, farm__organization=org, farm__status="active",
    )


def permission_codes(user, org, farm=None):
    if not user.is_active or user.account_status != "active" or org is None:
        return set()
    if owner(user, org):
        return set(Permission.objects.values_list("code", flat=True)) | GOVERNANCE_CODES | OPERATION_CODES | set(ALIASES)
    rows = assignments(user, org)
    if farm is not None:
        rows = rows.filter(farm=farm)
    return set(RolePermission.objects.filter(role_id__in=rows.values("role_id")).values_list("permission__code", flat=True))


def has_capability(user, org, code, farm=None):
    if not user.is_active or user.account_status != "active" or org is None:
        return False
    if owner(user, org):
        return farm is None or farm.organization_id == org.id
    codes = permission_codes(user, org, farm)
    return bool(codes & ({code} | ALIASES.get(code, set())))


def authorized_farms(user, org, *codes):
    codes = codes or getattr(user, "_required_capabilities", ())
    qs = Farm.objects.filter(organization=org)
    if not user.is_active or user.account_status != "active":
        return qs.none()
    if owner(user, org):
        return qs
    rows = assignments(user, org)
    if codes:
        accepted = set(codes)
        for code in codes:
            accepted.update(ALIASES.get(code, set()))
        rows = rows.filter(role__roles_permission__permission__code__in=accepted)
    return qs.filter(id__in=rows.values("farm_id"))


def channel_access(user, org):
    if owner(user, org):
        return {"web": True, "mobile": False}
    if org is None:
        return {"web": True, "mobile": False}
    rows = assignments(user, org)
    return {"web": rows.filter(role__web_access=True).exists(),
            "mobile": rows.filter(role__mobile_access=True).exists()}
