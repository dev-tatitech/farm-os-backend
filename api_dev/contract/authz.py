from account.helper import get_app_type
from account.models import User
from account.utils.jwt_utils import decode_token
from organization.models import Farm, Organization

from .codes import ErrorCode
from .exceptions import ContractError


def require_user(request) -> User:
    from account.sessions import authenticate_request
    return authenticate_request(request)

def resolve_organization(user: User) -> Organization:
    org = user.organization or user.organizations.first()
    if not org:
        raise ContractError(
            404,
            ErrorCode.ORGANIZATION_NOT_FOUND,
            "Organization could not be found.",
        )
    return org


def is_organization_owner(user: User, org: Organization) -> bool:
    if org.user_id and str(org.user_id) == str(user.id):
        return True
    return False


def require_organization(user: User, organization_id) -> Organization:
    org = resolve_organization(user)
    if str(org.id) != str(organization_id):
        raise ContractError(
            404,
            ErrorCode.ORGANIZATION_NOT_FOUND,
            "Organization could not be found.",
        )
    return org


def require_permission(user: User, org: Organization, *codes: str, farm=None):
    user._required_capabilities = codes
    if is_organization_owner(user, org):
        return
    from common.access import has_capability

    if not codes:
        return
    if any(has_capability(user, org, code, farm) for code in codes):
        return
    raise ContractError(
        403,
        ErrorCode.PERMISSION_DENIED,
        "You do not have permission to perform this action.",
    )


def require_animal(org: Organization, animal_id, farm: Farm = None):
    from animals.models import Animal

    try:
        animal = Animal.objects.select_related(
            "farm",
            "livestock_species",
            "livestock_breed",
            "housing_unit",
            "species",
            "breed",
            "unit",
            "mother",
        ).get(id=animal_id, farm__organization=org)
    except Animal.DoesNotExist:
        raise ContractError(
            404,
            ErrorCode.ANIMAL_NOT_FOUND,
            "Animal could not be found.",
        )
    if farm and animal.farm_id != farm.id:
        raise ContractError(
            404,
            ErrorCode.ANIMAL_NOT_FOUND,
            "Animal could not be found.",
        )
    return animal


def require_farm(org: Organization, farm_id, user: User = None) -> Farm:
    try:
        farm = Farm.objects.get(id=farm_id, organization=org)
    except Farm.DoesNotExist:
        raise ContractError(
            404,
            ErrorCode.FARM_NOT_FOUND,
            "Farm could not be found.",
        )
    if user and not is_organization_owner(user, org):
        from common.access import authorized_farms
        if not authorized_farms(user, org).filter(pk=farm.pk).exists():
            raise ContractError(
                404,
                ErrorCode.FARM_NOT_FOUND,
                "Farm could not be found.",
            )
        codes = getattr(user, "_required_capabilities", ())
        if codes:
            require_permission(user, org, *codes, farm=farm)
    return farm
