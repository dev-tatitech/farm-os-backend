
from django.db.models import Q

def user_has_permission(user, permission_code, farm=None):
    from .access import has_capability, organization_for
    return has_capability(user, organization_for(user), permission_code, farm)
