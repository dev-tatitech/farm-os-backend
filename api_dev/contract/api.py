from django.core.exceptions import ValidationError as DjangoValidationError
from ninja import NinjaAPI
from ninja.errors import HttpError, ValidationError as NinjaValidationError

from .animals import animals_router
from .births import births_router
from .codes import ErrorCode
from .dash import dash_router
from .envelope import V2Error, V2Success, error_body, success_body
from .exceptions import ContractError
from .farms import farms_router
from .health import health_router
from .notify import notify_router
from .ops import ops_router
from .orgs import orgs_router, permissions_router, roles_router, users_router
from .registry import registry_router
from .search import search_router
from .timeline import timeline_router

v2_api = NinjaAPI(
    title="FarmOS Frontend API Contract v2.2 — Livestock MVP Final Release Candidate",
    version="2.2",
    description=(
        "v2.2 is the frozen Livestock MVP Web/Mobile API contract. No additional "
        "MVP functionality or breaking contract change may be introduced without "
        "Product change approval."
    ),
    docs_url=None,
    openapi_url="/openapi.json",
    urls_namespace="api_v2",
)


@v2_api.exception_handler(ContractError)
def on_contract_error(request, exc: ContractError):
    return v2_api.create_response(
        request,
        error_body(
            exc.code,
            exc.message,
            errors=exc.errors,
            retryable=exc.retryable,
            data=exc.data,
        ),
        status=exc.http_status,
    )


@v2_api.exception_handler(HttpError)
def on_http_error(request, exc: HttpError):
    code = ErrorCode.PERMISSION_DENIED if exc.status_code == 403 else ErrorCode.VALIDATION_ERROR
    if exc.status_code == 401:
        code = ErrorCode.AUTHENTICATION_REQUIRED
    return v2_api.create_response(
        request,
        error_body(code, str(exc.message), retryable=False),
        status=exc.status_code,
    )


@v2_api.exception_handler(NinjaValidationError)
def on_validation_error(request, exc: NinjaValidationError):
    return v2_api.create_response(
        request,
        error_body(
            ErrorCode.VALIDATION_ERROR,
            "Request validation failed.",
            errors={"details": exc.errors},
        ),
        status=422,
    )


@v2_api.exception_handler(DjangoValidationError)
def on_django_validation(request, exc: DjangoValidationError):
    errors = getattr(exc, "message_dict", None) or {"details": getattr(exc, "messages", [str(exc)])}
    return v2_api.create_response(
        request,
        error_body(ErrorCode.VALIDATION_ERROR, "Request validation failed.", errors=errors),
        status=422,
    )


@v2_api.get(
    "/",
    response={200: V2Success},
    tags=["Contract"],
    summary="Contract health",
)
def contract_root(request):
    return 200, success_body(
        data={
                "contract": "FarmOS Frontend API Contract v2.2",
                "release": "Livestock MVP Final Release Candidate",
            "legacy_prefix": "/api/",
            "this_prefix": "/api/v2/",
            "identifiers": [
                "livestock_species_id",
                "livestock_breed_id",
                "housing_unit_id",
                "farm_id",
                "organization_id",
                "animal_id",
                "group_id",
            ],
        },
        message="v2.2 Livestock MVP Final Release Candidate is available.",
    )


v2_api.add_router("/registry/", registry_router)
v2_api.add_router("/users/", users_router)
v2_api.add_router("/roles/", roles_router)
v2_api.add_router("/permissions/", permissions_router)
v2_api.add_router("/organizations/", orgs_router)
v2_api.add_router("/farms/", farms_router)
v2_api.add_router("/animals/", animals_router)
v2_api.add_router("/operations/", ops_router)
v2_api.add_router("/timeline/", timeline_router)
v2_api.add_router("/notifications/", notify_router)
v2_api.add_router("/search/", search_router)
v2_api.add_router("/dashboard/", dash_router)
v2_api.add_router("/health/", health_router)
v2_api.add_router("/reproduction/births/", births_router)
