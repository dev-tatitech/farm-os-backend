
from django.db.models import Q

def user_has_permission(user, permission_code, farm=None):
    from role.models import RolePermission
    filters = Q(role__userrole__user=user)

    if farm:
        filters &= Q(role__userrole__farm=farm)

    return RolePermission.objects.filter(
        filters,
        permission__code=permission_code
    ).exists()