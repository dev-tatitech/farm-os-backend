"""Tenant and farm checks for legacy endpoints using Django object lookups."""
from django.shortcuts import get_object_or_404

from account.sessions import authenticate_request
from contract.authz import require_farm, require_permission, resolve_organization
from contract.codes import ErrorCode
from contract.exceptions import ContractError


def scoped_lookup(request, *capabilities):
    def lookup(model, *args, **kwargs):
        user = authenticate_request(request)
        org = resolve_organization(user)
        obj = get_object_or_404(model, *args, **kwargs)
        label = obj._meta.label_lower
        farm_id = obj.pk if label == "organization.farm" else getattr(obj, "farm_id", None)
        if farm_id is None and getattr(obj, "animal_id", None):
            farm_id = obj.animal.farm_id
        if farm_id is not None:
            farm = require_farm(org, farm_id, user)
            if capabilities:
                require_permission(user, org, *capabilities, farm=farm)
        tenant_id = getattr(obj, "organization_id", None)
        if tenant_id is not None and tenant_id != org.id:
            raise ContractError(404, ErrorCode.RESOURCE_NOT_FOUND, "Resource could not be found.")
        return obj
    return lookup
