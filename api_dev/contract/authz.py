from account.helper import get_app_type
from account.models import User
from account.utils.jwt_utils import decode_token
from organization.models import Farm, Organization

from .codes import ErrorCode
from .exceptions import ContractError


def require_user(request) -> User:
    app_type = get_app_type(request)
    access_token = request.COOKIES.get(f"{app_type}_access_token")
    if not access_token:
        raise ContractError(
            401,
            ErrorCode.AUTHENTICATION_REQUIRED,
            "Authentication is required.",
        )
    try:
        payload = decode_token(access_token)
    except Exception:
        raise ContractError(
            401,
            ErrorCode.SESSION_EXPIRED,
            "Session has expired. Please sign in again.",
        )
    try:
        user = User.objects.get(id=payload["sub"])
    except (User.DoesNotExist, KeyError, ValueError):
        raise ContractError(
            401,
            ErrorCode.AUTHENTICATION_REQUIRED,
            "Authentication is required.",
        )
    if user.account_status in ("Suspended", "Deleted"):
        raise ContractError(
            403,
            ErrorCode.PERMISSION_DENIED,
            "This account is not allowed to access the API.",
        )
    return user


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
    if user.is_superuser:
        return True
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


def require_permission(user: User, org: Organization, *codes: str):
    if is_organization_owner(user, org):
        return
    from common.permission_checker import user_has_permission

    if not codes:
        return
    if any(user_has_permission(user, code) for code in codes):
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
        from role.models import UserRole

        allowed = UserRole.objects.filter(user=user, farm=farm).exists()
        org_wide = UserRole.objects.filter(user=user, farm__isnull=True).exists()
        if not allowed and not org_wide:
            raise ContractError(
                403,
                ErrorCode.FARM_ACCESS_DENIED,
                "You do not have access to this farm.",
            )
    return farm
