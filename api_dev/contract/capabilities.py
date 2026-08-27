from django.db.models import Q

from common.permissions import Permissions
from role.models import RolePermission, UserRole

from .authz import is_organization_owner


def permission_codes_for_user(user, org) -> set[str]:
    if is_organization_owner(user, org):
        from role.models import Permission

        return set(Permission.objects.values_list("code", flat=True))
    return set(
        RolePermission.objects.filter(
            Q(role__userrole__user=user),
            Q(role__organization=org) | Q(role__organization__isnull=True),
        ).values_list("permission__code", flat=True)
    )


def user_assignments(user, org) -> list[dict]:
    rows = (
        UserRole.objects.filter(user=user)
        .select_related("role", "farm")
        .filter(Q(farm__organization=org) | Q(farm__isnull=True))
    )
    assignments = []
    for row in rows:
        assignments.append(
            {
                "role_id": row.role_id,
                "role_name": row.role.name,
                "role_code": row.role.code,
                "farm_id": row.farm_id,
                "farm_name": row.farm.name if row.farm else None,
            }
        )
    return assignments


def _has(codes: set[str], *needed: str) -> bool:
    return any(code in codes for code in needed)


def build_capabilities(user, org, codes: set[str]) -> dict:
    owner = is_organization_owner(user, org)

    def cap(*needed: str) -> bool:
        return owner or _has(codes, *needed)

    capabilities = {
        "view_animal_details": cap(Permissions.Animal.VIEW),
        "add_animal_details": cap(Permissions.Animal.CREATE),
        "update_animal_details": cap(Permissions.Animal.UPDATE),
        "view_health": cap(Permissions.Health.VIEW),
        "record_health": cap(Permissions.Health.CREATE),
        "record_health_observation": cap(Permissions.Health.CREATE),
        "manage_health_case": cap(Permissions.Health.UPDATE, Permissions.Health.CREATE),
        "view_feed": cap(Permissions.Feed.VIEW),
        "record_feed_activity": cap(Permissions.Feed.CREATE),
        "manage_feed_inventory": cap(Permissions.Feed.UPDATE, Permissions.Feed.CREATE),
        "view_reproduction": cap(Permissions.Reproduction.VIEW),
        "add_reproduction": cap(Permissions.Reproduction.CREATE),
        "view_movement": cap(Permissions.MovementRecord.VIEW),
        "add_movement": cap(Permissions.MovementRecord.CREATE),
        "view_sales": cap(Permissions.SalesRecord.VIEW),
        "add_sales": cap(Permissions.SalesRecord.CREATE),
        "sale_restriction_override": cap(Permissions.SalesRecord.RESTRICTION_OVERRIDE),
        "view_finance": cap(Permissions.Finance.VIEW),
        "add_finance": cap(Permissions.Finance.CREATE),
        "view_pharmacy": cap(Permissions.Pharmacy.VIEW),
        "manage_pharmacy": cap(Permissions.Pharmacy.CREATE, Permissions.Pharmacy.UPDATE),
        "view_reports": cap(Permissions.Reports.REPORTS, Permissions.Reports.LIVESTOCK_DASHBOARD),
        "view_farm_profile": cap(Permissions.Farm.UPDATE, Permissions.FarmUnit.VIEW, Permissions.Animal.VIEW),
        "manage_farm": cap(Permissions.Farm.UPDATE, Permissions.Farm.CREATE),
        "view_operation": cap(
            Permissions.Health.VIEW, Permissions.Feed.VIEW, Permissions.Animal.VIEW
        ),
        "create_operation": cap(
            Permissions.Health.CREATE, Permissions.Feed.CREATE, Permissions.Animal.CREATE
        ),
        "assign_operation": cap(Permissions.Farm.UPDATE),
        "reassign_operation": cap(Permissions.Farm.UPDATE),
        "complete_operation": cap(
            Permissions.Health.CREATE, Permissions.Feed.CREATE, Permissions.SalesRecord.CREATE
        ),
        "cancel_operation": cap(Permissions.Farm.UPDATE),
        "view_user_activity": owner,
    }
    navigation = {
        "dashboard": cap(
            Permissions.Reports.LIVESTOCK_DASHBOARD,
            Permissions.Animal.VIEW,
            Permissions.Farm.UPDATE,
        )
        or owner,
        "livestock": capabilities["view_animal_details"],
        "health": capabilities["view_health"],
        "feed": capabilities["view_feed"],
        "reproduction": capabilities["view_reproduction"],
        "movement": capabilities["view_movement"],
        "sales": capabilities["view_sales"],
        "finance": capabilities["view_finance"],
        "pharmacy": capabilities["view_pharmacy"],
        "reports": capabilities["view_reports"],
        "operations": capabilities["view_operation"],
        "my_work": capabilities["view_operation"],
        "people": owner or capabilities["manage_farm"],
    }
    return {
        "is_organization_owner": owner,
        "permissions": sorted(codes),
        "capabilities": capabilities,
        "navigation": navigation,
    }
