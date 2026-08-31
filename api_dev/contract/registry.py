from ninja import Router

from .authz import require_user
from .envelope import V2Error, V2Success, success_body

registry_router = Router(tags=["Contract"])

V2 = "v2"
LEGACY = "legacy_approved"
DEPRECATED = "deprecated_for_new_frontend"

REGISTRY = [
    {"domain": "Auth", "operation": "Login", "endpoint": "POST /api/auth/login", "status": LEGACY, "notes": "Only approved non-v2 envelope."},
    {"domain": "Contract", "operation": "Health", "endpoint": "GET /api/v2/", "status": V2},
    {"domain": "Contract", "operation": "Endpoint registry", "endpoint": "GET /api/v2/registry/", "status": V2},
    {"domain": "Users", "operation": "Current profile", "endpoint": "GET /api/v2/users/me/", "status": V2},
    {"domain": "Users", "operation": "Capabilities", "endpoint": "GET /api/v2/users/me/capabilities/", "status": V2},
    {"domain": "Users", "operation": "My activity", "endpoint": "GET /api/v2/users/me/activity/", "status": V2},
    {"domain": "Users", "operation": "My tasks", "endpoint": "GET /api/v2/users/me/tasks/", "status": V2},
    {"domain": "Users", "operation": "User operational profile", "endpoint": "GET /api/v2/users/{user_id}/", "status": V2},
    {"domain": "Users", "operation": "User activity", "endpoint": "GET /api/v2/users/{user_id}/activity/", "status": V2},
    {"domain": "Users", "operation": "User tasks", "endpoint": "GET /api/v2/users/{user_id}/tasks/", "status": V2},
    {"domain": "Users", "operation": "People list", "endpoint": "GET /api/v2/users/", "status": V2},
    {"domain": "Users", "operation": "Invite user", "endpoint": "POST /api/admin/invite/", "status": LEGACY},
    {"domain": "Users", "operation": "Assign role", "endpoint": "POST /api/role/user-role/", "status": LEGACY},
    {"domain": "Users", "operation": "User roles", "endpoint": "GET /api/role/user-role/", "status": LEGACY},
    {"domain": "Roles", "operation": "Roles list", "endpoint": "GET /api/v2/roles/", "status": V2},
    {"domain": "Roles", "operation": "Permissions list", "endpoint": "GET /api/v2/permissions/", "status": V2},
    {"domain": "Animals", "operation": "List", "endpoint": "GET /api/v2/animals/", "status": V2},
    {"domain": "Animals", "operation": "Create", "endpoint": "POST /api/v2/animals/", "status": V2},
    {"domain": "Animals", "operation": "Update", "endpoint": "PATCH /api/v2/animals/{animal_id}/", "status": V2},
    {"domain": "Animals", "operation": "Profile", "endpoint": "GET /api/v2/animals/{id}/profile/", "status": V2},
    {"domain": "Animals", "operation": "Old profile", "endpoint": "GET /api/animals/animal-profile/v2/{id}", "status": DEPRECATED},
    {"domain": "Animals", "operation": "Resolve tag", "endpoint": "GET /api/v2/animals/resolve-tag/{tag_id}/", "status": V2},
    {"domain": "Operations", "operation": "Tasks CRUD/actions", "endpoint": "/api/v2/operations/tasks/", "status": V2},
    {"domain": "Operations", "operation": "Unable to complete", "endpoint": "POST /api/v2/operations/tasks/{id}/unable-to-complete/", "status": V2},
    {"domain": "Operations", "operation": "Reopen", "endpoint": "POST /api/v2/operations/tasks/{id}/reopen/", "status": V2},
    {"domain": "Operations", "operation": "Schedules", "endpoint": "/api/v2/operations/schedules/", "status": V2},
    {"domain": "Health", "operation": "Observations / cases", "endpoint": "/api/v2/health/", "status": V2},
    {"domain": "Health", "operation": "Case detail", "endpoint": "GET /api/v2/health/cases/{case_id}/", "status": V2},
    {"domain": "Health", "operation": "Treatment record", "endpoint": "POST /api/health/treatment/", "status": LEGACY},
    {"domain": "Health", "operation": "Vaccination", "endpoint": "POST /api/health/vaccination/", "status": LEGACY},
    {"domain": "Health", "operation": "Quarantine", "endpoint": "POST /api/health/quarantine/", "status": LEGACY},
    {"domain": "Health", "operation": "Mortality", "endpoint": "POST /api/health/mortality/", "status": LEGACY},
    {"domain": "Health", "operation": "Health alerts", "endpoint": "GET /api/v2/health/alerts/", "status": V2},
    {"domain": "Reproduction", "operation": "Insemination", "endpoint": "/api/reproduction/", "status": LEGACY},
    {"domain": "Reproduction", "operation": "Pregnancy", "endpoint": "/api/reproduction/", "status": LEGACY},
    {"domain": "Reproduction", "operation": "Birth / offspring", "endpoint": "/api/reproduction/", "status": LEGACY},
    {"domain": "Feed", "operation": "Inventory / issuance / batches", "endpoint": "/api/feed/", "status": LEGACY},
    {"domain": "Production", "operation": "Milk / production records", "endpoint": "/api/animals/", "status": LEGACY},
    {"domain": "Finance", "operation": "Transactions / cost summary", "endpoint": "/api/finance/", "status": LEGACY},
    {"domain": "Reports", "operation": "Livestock / health / finance reports", "endpoint": "/api/reports/", "status": LEGACY},
    {"domain": "Movement", "operation": "Move list / sale", "endpoint": "/api/movement-records/", "status": LEGACY},
    {"domain": "Master data", "operation": "Species / breeds / housing", "endpoint": "/api/admin/livestock/", "status": LEGACY},
    {"domain": "Dashboard", "operation": "Org / farm / my-work / health", "endpoint": "/api/v2/dashboard/", "status": V2},
    {"domain": "Search", "operation": "Global search", "endpoint": "GET /api/v2/search/", "status": V2},
    {"domain": "Notifications", "operation": "Inbox / unread count", "endpoint": "/api/v2/notifications/", "status": V2},
]


@registry_router.get(
    "/",
    response={200: V2Success, 401: V2Error},
    summary="FarmOS MVP endpoint registry",
)
def endpoint_registry(request):
    require_user(request)
    return 200, success_body(
        data={"contract": "2.1", "entries": REGISTRY},
        message="Endpoint registry fetched successfully.",
    )
