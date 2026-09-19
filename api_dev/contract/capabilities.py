from django.db.models import Q

from common.permissions import Permissions
from role.models import RolePermission, UserRole

from .authz import is_organization_owner
from common.access import assignments as active_assignments, channel_access, ALIASES, GOVERNANCE_CODES, OPERATION_CODES


def permission_codes_for_user(user, org, farm=None) -> set[str]:
    from common.access import permission_codes
    return permission_codes(user, org, farm=farm)


def user_assignments(user, org, farm=None) -> list[dict]:
    rows = (
        active_assignments(user, org)
        .select_related("role", "farm")
        .filter(Q(farm__organization=org) | Q(farm__isnull=True))
    )
    if farm is not None:
        rows = rows.filter(farm=farm)
    assignments = []
    for row in rows:
        assignments.append(
            {
                "id": row.id,
                "role_id": row.role_id,
                "role_name": row.role.name,
                "role_code": row.role.code,
                "farm_id": row.farm_id,
                "farm_name": row.farm.name if row.farm else None,
                "status": row.status,
            }
        )
    return assignments


def access_payload(user, org, farm=None) -> dict:
    owner = is_organization_owner(user, org)
    assignments = user_assignments(user, org, farm=farm)
    if owner:
        return {
            "account_type": "organization_owner",
            "access_source": "organization_ownership",
            "scope": "farm" if farm is not None else "organization",
            "is_organization_owner": True,
            "all_farms": True,
            "assignments": [],
            "farm": {"id": farm.id, "name": farm.name} if farm is not None else None,
            "channel_access": channel_access(user, org),
        }
    return {
        "account_type": "staff",
        "access_source": "role_assignment" if assignments else "none",
        "scope": "assigned_farms" if assignments else "none",
        "is_organization_owner": False,
        "all_farms": False,
        "channel_access": channel_access(user, org),
        "assignments": [
            {
                "id": row["id"],
                "farm": {"id": row["farm_id"], "name": row["farm_name"]},
                "role": {"id": row["role_id"], "name": row["role_name"]},
                "status": row["status"],
            }
            for row in assignments
        ],
        "farm": {"id": farm.id, "name": farm.name} if farm is not None else None,
    }


def _has(codes: set[str], *needed: str) -> bool:
    return any(code in codes for code in needed)


def build_capabilities(user, org, codes: set[str], farm=None) -> dict:
    owner = is_organization_owner(user, org)

    def cap(*needed: str) -> bool:
        return owner or any(bool(codes & ({code} | ALIASES.get(code, set()))) for code in needed)

    capabilities = {
        "view_animal_details": cap(Permissions.Animal.VIEW),
        "add_animal_details": cap(Permissions.Animal.CREATE),
        "update_animal_details": cap(Permissions.Animal.UPDATE),
        "view_health": cap(Permissions.Health.VIEW),
        "record_health": cap(Permissions.Health.CREATE),
        "record_health_observation": cap("record_health_observation"),
        "manage_health_case": cap("manage_health_case"),
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
    capabilities.update({code: cap(code) for code in GOVERNANCE_CODES | OPERATION_CODES})
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
        "people": capabilities["view_people"],
    }
    return {
        "is_organization_owner": owner,
        "access": access_payload(user, org, farm=farm),
        "channel_access": channel_access(user, org),
        "permissions": sorted(codes),
        "capabilities": capabilities,
        "navigation": navigation,
    }
