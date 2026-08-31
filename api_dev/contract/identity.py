from common.permissions import Permissions

from .authz import is_organization_owner
from .capabilities import permission_codes_for_user


def display_name(user) -> str:
    if user is None:
        return None
    full = " ".join(
        part
        for part in (getattr(user, "first_name", ""), getattr(user, "last_name", ""))
        if part
    ).strip()
    if full:
        return full
    if getattr(user, "username", None):
        return user.username
    return user.email or str(user.id)


def can_manage_people(user, org) -> bool:
    if is_organization_owner(user, org):
        return True
    codes = permission_codes_for_user(user, org)
    return Permissions.Farm.UPDATE in codes


def can_view_people(user, org) -> bool:
    return can_manage_people(user, org)


def actor_payload(user, org=None) -> dict:
    if user is None:
        return None
    role_name = None
    if org is not None:
        from role.models import UserRole

        assignment = (
            UserRole.objects.filter(user=user)
            .select_related("role")
            .filter(farm__organization=org)
            .first()
        )
        if assignment:
            role_name = assignment.role.name
    return {
        "id": str(user.id),
        "display_name": display_name(user),
        "role_name": role_name,
    }


def subject_payload(animal=None, farm=None, extra_type=None, extra_id=None, extra_label=None):
    if animal is not None:
        return {"type": "animal", "id": animal.id, "label": animal.tag_id or f"animal-{animal.id}"}
    if farm is not None:
        return {"type": "farm", "id": farm.id, "label": farm.name}
    if extra_type:
        return {"type": extra_type, "id": extra_id, "label": extra_label}
    return None


def reference_payload(ref_type, ref_id):
    if not ref_type or ref_id in (None, ""):
        return None
    return {"type": ref_type, "id": ref_id}
