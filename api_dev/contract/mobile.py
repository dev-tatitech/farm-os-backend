"""JWT-only field-execution API.  Deliberately smaller than the web v2 API."""
from ninja import NinjaAPI, Router
from ninja.security import HttpBearer

from account.models import RefreshSession
from account.sessions import active_account, check_channel
from account.utils.jwt_utils import decode_token
from common.access import authorized_farms
from django.utils import timezone
from operations.models import Task
from operations.services import accept_task, complete_task, get_task, mark_unable_to_complete, serialize_task, start_task, work_summary_for

from .authz import require_farm, require_permission, resolve_organization
from .codes import ErrorCode
from .envelope import V2Error, V2Success, error_body, success_body
from .exceptions import ContractError
from .helpers import begin_idempotency, paginated, store_idempotency
from .ops import _domain_complete_perm, _payload_dict
from .schemas import TaskCompleteIn, TaskUnableIn


class MobileJWT(HttpBearer):
    """Accept only a live mobile-channel access JWT; never browser cookies."""
    def authenticate(self, request, token):
        try:
            claims = decode_token(token)
            if claims.get("kind") != "access":
                raise ValueError()
            session = RefreshSession.objects.select_related("user").get(
                id=claims["sid"], user_id=claims["sub"], is_active=True, channel="mobile"
            )
            if session.expires_at <= timezone.now():
                raise ValueError()
        except Exception:
            raise ContractError(401, ErrorCode.SESSION_EXPIRED, "Mobile access token is invalid or expired.")
        active_account(session.user)
        check_channel(session.user, "mobile")
        request.auth_session = session
        return session.user


class MobileSyncJWT(MobileJWT):
    """Allows a live session to discover revoked scope before channel denial."""
    def authenticate(self, request, token):
        try:
            claims = decode_token(token)
            if claims.get("kind") != "access":
                raise ValueError()
            session = RefreshSession.objects.select_related("user").get(
                id=claims["sid"], user_id=claims["sub"], is_active=True, channel="mobile"
            )
            if session.expires_at <= timezone.now():
                raise ValueError()
        except Exception:
            raise ContractError(401, ErrorCode.SESSION_EXPIRED, "Mobile access token is invalid or expired.")
        active_account(session.user)
        request.auth_session = session
        return session.user


mobile_api = NinjaAPI(
    title="FarmOS Mobile Field API",
    version="1.0",
    description="JWT Bearer API for the FarmOS mobile field-execution client. Browser-cookie endpoints are intentionally excluded.",
    docs_url="/docs",
    openapi_url="/openapi.json",
    auth=MobileJWT(),
    urls_namespace="mobile_api",
)
router = Router(tags=["Mobile My Work"])


def _user_org(request):
    user = request.auth
    return user, resolve_organization(user)


def _open_personal(user, org, farm=None):
    qs = Task.objects.filter(farm__in=authorized_farms(user, org), assigned_to=user).exclude(
        status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED, Task.Status.UNABLE_TO_COMPLETE]
    )
    return qs.filter(farm=farm) if farm else qs


@router.get("/work/", response={200: V2Success, 401: V2Error, 403: V2Error})
def my_work(request, page: int = 1, page_size: int = 20, farm_id: int = None):
    user, org = _user_org(request)
    require_permission(user, org, "view_operation")
    farm = require_farm(org, farm_id, user) if farm_id is not None else None
    return 200, paginated(_open_personal(user, org, farm).order_by("due_at", "-priority"), page, page_size, serialize_task, "Mobile work fetched successfully.")


@router.get("/sync-scope/", response={200: V2Success, 401: V2Error}, auth=MobileSyncJWT())
def sync_scope(request):
    """Authoritative cache scope for a reconnecting mobile client.

    The client must remove operational cache entries whose farm IDs are absent
    from this response before treating any local data as actionable.
    """
    user, org = _user_org(request)
    return 200, success_body(
        data={
            "authorized_farm_ids": list(authorized_farms(user, org).values_list("id", flat=True)),
            "cache_policy": "remove_revoked_farm_operational_data",
        },
        message="Mobile synchronization scope fetched successfully.",
    )


@router.get("/work/dashboard/", response={200: V2Success, 401: V2Error, 403: V2Error})
def my_work_dashboard(request, farm_id: int = None):
    user, org = _user_org(request)
    require_permission(user, org, "view_operation")
    farm = require_farm(org, farm_id, user) if farm_id is not None else None
    qs = _open_personal(user, org, farm)
    today = timezone.localdate()
    return 200, success_body(data={"summary": work_summary_for(user, org, farm), "today": [serialize_task(t) for t in qs.filter(due_at__date=today)[:20]], "overdue": [serialize_task(t) for t in qs.filter(due_at__lt=timezone.now())[:20]], "upcoming": [serialize_task(t) for t in qs.filter(due_at__date__gt=today).order_by("due_at")[:20]]}, message="Mobile work dashboard fetched successfully.")


def _mobile_task(request, task_id):
    user, org = _user_org(request)
    task = get_task(org, task_id)
    require_farm(org, task.farm_id, user)
    return user, org, task


@router.get("/tasks/{task_id}/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error})
def task_detail(request, task_id: int):
    user, org, task = _mobile_task(request, task_id)
    if task.assigned_to_id != user.id:
        raise ContractError(403, ErrorCode.TASK_NOT_ASSIGNED_TO_USER, "This task is not assigned to you.")
    return 200, success_body(data=serialize_task(task), message="Mobile task fetched successfully.")


@router.post("/tasks/{task_id}/accept/", response={200: V2Success, 401: V2Error, 403: V2Error, 409: V2Error})
def accept(request, task_id: int):
    user, org, task = _mobile_task(request, task_id)
    require_permission(user, org, "complete_operation", farm=task.farm)
    return 200, success_body(data=serialize_task(accept_task(task, user)), message="Task accepted successfully.")


@router.post("/tasks/{task_id}/start/", response={200: V2Success, 401: V2Error, 403: V2Error, 409: V2Error})
def start(request, task_id: int):
    user, org, task = _mobile_task(request, task_id)
    require_permission(user, org, "complete_operation", farm=task.farm)
    return 200, success_body(data=serialize_task(start_task(task, user)), message="Task started successfully.")


@router.post("/tasks/{task_id}/complete/", response={200: V2Success, 401: V2Error, 403: V2Error, 409: V2Error, 422: V2Error})
def complete(request, task_id: int, payload: TaskCompleteIn):
    user, org, task = _mobile_task(request, task_id)
    require_permission(user, org, "complete_operation", *_domain_complete_perm(task), farm=task.farm)
    key, cached = begin_idempotency(user, request, payload)
    if cached:
        return cached
    task = complete_task(task, user, _payload_dict(payload), evidence=payload.evidence or "")
    body = success_body(data=serialize_task(task), message="Task completed successfully.")
    store_idempotency(user, key, 200, body)
    return 200, body


@router.post("/tasks/{task_id}/unable-to-complete/", response={200: V2Success, 401: V2Error, 403: V2Error, 409: V2Error, 422: V2Error})
def unable(request, task_id: int, payload: TaskUnableIn):
    user, org, task = _mobile_task(request, task_id)
    require_permission(user, org, "complete_operation", farm=task.farm)
    key, cached = begin_idempotency(user, request, payload)
    if cached:
        return cached
    task = mark_unable_to_complete(task, user, payload.dict())
    body = success_body(data=serialize_task(task), message="Unable-to-complete recorded.")
    store_idempotency(user, key, 200, body)
    return 200, body


mobile_api.add_router("/", router)


@mobile_api.exception_handler(ContractError)
def mobile_contract_error(request, exc):
    return mobile_api.create_response(request, error_body(exc.code, exc.message, errors=exc.errors, retryable=exc.retryable, data=exc.data), status=exc.http_status)
