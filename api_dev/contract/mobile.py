"""JWT-only field-execution API.  Deliberately smaller than the web v2 API."""
import secrets
from datetime import timedelta
from functools import wraps

from django.contrib.auth.hashers import check_password
from django.db import transaction
from django.utils import timezone
from ninja import NinjaAPI, Router
from ninja.security import HttpBearer
from common.permissions import Permissions

from account.models import EmailValidation, RefreshSession, User
from account.schema import LoginSchema
from account.utils.jwt_utils import create_access_token, create_refresh_token, decode_token
from account.utils.token_hash import hash_token
from account.sessions import active_account, check_channel
from common.audit import security_event
from common.access import authorized_farms, organization_for
from operations.models import Task
from operations.models import Notification
from animals.models import AnimalGroup
from health.models import HealthCase
from operations.services import accept_task, complete_task, execute_direct_domain_action, get_task, mark_unable_to_complete, public_result_type, serialize_notification, serialize_task, start_task, work_summary_for

from .authz import require_farm, require_permission, resolve_organization
from .codes import ErrorCode
from .envelope import V2Error, V2Success, error_body, success_body
from .exceptions import ContractError
from .helpers import begin_idempotency, paginated, store_idempotency
from .ops import WORK_TYPE_METADATA, _domain_complete_perm, _payload_dict, eligible_assignee_rows, _work_type_or_404
from .schemas import DirectDomainActionIn, HealthCaseIn, TaskCompleteIn, TaskUnableIn
from .identity import reference_payload, subject_payload
from .authz import require_animal


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


def mobile_atomic_mutation(view):
    """Atomic material write with JWT-session/channel revalidation."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        session = getattr(request, "auth_session", None)
        if session is None:
            raise ContractError(401, ErrorCode.SESSION_EXPIRED, "Mobile session is required.")
        with transaction.atomic():
            locked = RefreshSession.objects.select_for_update().select_related("user").get(pk=session.pk)
            User.objects.select_for_update().get(pk=locked.user_id)
            locked.user.refresh_from_db()
            active_account(locked.user)
            if not locked.is_active or locked.expires_at <= timezone.now() or locked.channel != "mobile":
                raise ContractError(401, ErrorCode.SESSION_EXPIRED, "Mobile session is invalid or expired.")
            check_channel(locked.user, "mobile")
            request.auth_session = locked
            request.auth = locked.user
            return view(request, *args, **kwargs)
    return wrapped


@router.post("/auth/login/", auth=None)
def mobile_login(request, data: LoginSchema):
    """Create a mobile-channel session and return JWTs for native clients."""
    user = User.objects.filter(email=data.email).first()
    if user is None or not check_password(data.password, user.password):
        raise ContractError(401, ErrorCode.AUTHENTICATION_REQUIRED, "Invalid email or password.")
    active_account(user)
    if not user.is_superuser and not EmailValidation.objects.filter(email=user.email, is_used=True).exists():
        raise ContractError(400, ErrorCode.VALIDATION_ERROR, "Please verify your email.")
    if user.is_superuser:
        raise ContractError(403, ErrorCode.CHANNEL_ACCESS_DENIED, "This account cannot use the mobile application.")
    check_channel(user, "mobile", identity_only=True)

    with transaction.atomic():
        session = RefreshSession.objects.create(
            user=user,
            token_hash=secrets.token_hex(32),
            channel="mobile",
            expires_at=timezone.now() + timedelta(days=7),
            user_agent=request.headers.get("User-Agent", ""),
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        claims = {"sub": str(user.id), "sid": session.pk}
        refresh = create_refresh_token({**claims, "kind": "refresh", "jti": secrets.token_urlsafe(24)})
        access = create_access_token({**claims, "kind": "access"})
        session.token_hash = hash_token(refresh)
        session.save(update_fields=["token_hash"])
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        security_event("USER_LOGGED_IN", user, target=user, org=organization_for(user))

    return success_body(
        data={"access_token": access, "refresh_token": refresh, "token_type": "Bearer", "expires_in": 900},
        message="Mobile login successful.",
    )


@router.post("/auth/logout/", response={200: V2Success, 401: V2Error})
def mobile_logout(request):
    """Revoke the current mobile session represented by the Bearer token."""
    session = request.auth_session
    with transaction.atomic():
        locked = RefreshSession.objects.select_for_update().get(pk=session.pk)
        if locked.is_active:
            locked.is_active = False
            locked.save(update_fields=["is_active"])
            security_event("USER_LOGGED_OUT", locked.user, target=locked.user, org=organization_for(locked.user))
    return success_body(message="Logged out successfully.")


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


@router.get("/notifications/", response={200: V2Success, 401: V2Error})
def mobile_notifications(request, page: int = 1, page_size: int = 20, unread_only: bool = False):
    user, org = _user_org(request)
    qs = Notification.objects.filter(user=user, organization=org)
    if unread_only: qs = qs.filter(is_read=False)
    return 200, paginated(qs, page, page_size, serialize_notification, "Mobile notifications fetched successfully.")


@router.get("/notifications/unread-count/", response={200: V2Success, 401: V2Error})
def mobile_notification_unread_count(request):
    user, org = _user_org(request)
    return 200, success_body(data={"count": Notification.objects.filter(user=user, organization=org, is_read=False).count()}, message="Unread notification count fetched successfully.")


@router.post("/notifications/{notification_id}/read/", response={200: V2Success, 401: V2Error, 404: V2Error})
@mobile_atomic_mutation
def mobile_notification_read(request, notification_id: int):
    user, org = _user_org(request)
    try: row = Notification.objects.get(id=notification_id, user=user, organization=org)
    except Notification.DoesNotExist: raise ContractError(404, ErrorCode.NOTIFICATION_NOT_FOUND, "Notification could not be found.")
    if not row.is_read:
        row.is_read = True; row.read_at = timezone.now(); row.save(update_fields=["is_read", "read_at"])
    return 200, success_body(data=serialize_notification(row), message="Notification marked as read.")


@router.get("/work/dashboard/", response={200: V2Success, 401: V2Error, 403: V2Error})
def my_work_dashboard(request, farm_id: int = None):
    user, org = _user_org(request)
    require_permission(user, org, "view_operation")
    farm = require_farm(org, farm_id, user) if farm_id is not None else None
    qs = _open_personal(user, org, farm)
    today = timezone.localdate()
    return 200, success_body(data={"summary": work_summary_for(user, org, farm), "today": [serialize_task(t) for t in qs.filter(due_at__date=today)[:20]], "overdue": [serialize_task(t) for t in qs.filter(due_at__lt=timezone.now())[:20]], "upcoming": [serialize_task(t) for t in qs.filter(due_at__date__gt=today).order_by("due_at")[:20]]}, message="Mobile work dashboard fetched successfully.")


@router.get("/animals/", response={200: V2Success, 401: V2Error, 403: V2Error})
def mobile_animals(request, page: int = 1, page_size: int = 20, farm_id: int = None,
                   search: str = None, livestock_species_id: int = None, livestock_breed_id: int = None,
                   gender: str = None, lifecycle_status: str = None, health_status: str = None,
                   housing_unit_id: int = None, group_id: int = None, is_pregnant: bool = None,
                   is_lactating: bool = None, is_quarantine: bool = None, needs_attention: bool = None,
                   label_id: int = None, profile_incomplete: bool = None, open_observation: bool = None,
                   open_health_case: bool = None, age_min_months: int = None, age_max_months: int = None,
                   sort: str = "-id"):
    user, org = _user_org(request)
    from .animal_query import query_animals
    data = query_animals(user, org, page=page, page_size=page_size, farm_id=farm_id, search=search,
        livestock_species_id=livestock_species_id, livestock_breed_id=livestock_breed_id, gender=gender,
        lifecycle_status=lifecycle_status, health_status=health_status, housing_unit_id=housing_unit_id,
        group_id=group_id, is_pregnant=is_pregnant, is_lactating=is_lactating, is_quarantine=is_quarantine,
        needs_attention=needs_attention, label_id=label_id, profile_incomplete=profile_incomplete,
        open_observation=open_observation, open_health_case=open_health_case, age_min_months=age_min_months,
        age_max_months=age_max_months, sort=sort)
    return 200, data


@router.get("/work-types/{work_type}/eligible-assignees/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error})
def mobile_eligible_assignees(request, work_type: str, farm_id: int):
    user, org = _user_org(request)
    require_permission(user, org, "assign_operation")
    farm = require_farm(org, farm_id, user)
    return 200, success_body(data=eligible_assignee_rows(user, org, farm, _work_type_or_404(work_type), channel="mobile"), message="Eligible assignees fetched successfully.")


@router.get("/work-types/{work_type}/eligible-targets/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 422: V2Error})
def mobile_eligible_targets(request, work_type: str, farm_id: int, target_type: str = "animal", search: str = None,
                            livestock_species_id: int = None, livestock_breed_id: int = None, gender: str = None,
                            group_id: int = None, housing_unit_id: int = None, health_status: str = None,
                            lifecycle_status: str = None, page: int = 1, page_size: int = 20):
    user, org = _user_org(request); require_permission(user, org, "create_operation")
    meta = _work_type_or_404(work_type); farm = require_farm(org, farm_id, user)
    require_permission(user, org, Permissions.Animal.VIEW, farm=farm)
    require_permission(user, org, *meta["capabilities"], farm=farm)
    if target_type not in meta["target_types"]:
        raise ContractError(422, ErrorCode.TARGET_NOT_ELIGIBLE, "This work type does not support the requested target type.")
    if target_type == "group":
        from .helpers import paginated
        qs = AnimalGroup.objects.filter(farm=farm, status=AnimalGroup.Status.ACTIVE)
        if search: qs = qs.filter(name__icontains=search)
        return 200, paginated(qs.order_by("name", "id"), page, page_size, lambda row: {"id": row.id, "type": "group", "name": row.name, "farm_id": row.farm_id}, "Eligible targets fetched successfully.")
    from .animal_query import query_animals
    data = query_animals(user, org, page=page, page_size=page_size, farm_id=farm.id, search=search,
        livestock_species_id=livestock_species_id, livestock_breed_id=livestock_breed_id, gender=gender,
        lifecycle_status=lifecycle_status or "active", health_status=health_status, housing_unit_id=housing_unit_id,
        group_id=group_id, sort="tag_id")
    data["data"] = [{"id": row["id"], "type": "animal", "tag_id": row["tag_id"], "farm_id": farm.id} for row in data.get("data", [])]
    return 200, data


@router.get("/farm-members/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error})
def mobile_farm_members(request, farm_id: int, work_type: str):
    """Work-context assignment list; never returns every farm member."""
    return mobile_eligible_assignees(request, work_type, farm_id)


@router.post("/quick-record/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error, 422: V2Error})
@mobile_atomic_mutation
def mobile_quick_record(request, payload: DirectDomainActionIn):
    user, org = _user_org(request)
    farm = require_farm(org, payload.farm_id, user)
    if payload.task_type not in WORK_TYPE_METADATA or payload.task_type == Task.Type.GENERIC:
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "Unsupported direct domain action type.")
    context = Task(task_type=payload.task_type, farm=farm)
    require_permission(user, org, *_domain_complete_perm(context), farm=farm)
    animal = require_animal(org, payload.animal_id, farm) if payload.animal_id else None
    group = None
    if payload.group_id:
        from operations.services import _get_group
        group = _get_group(farm, payload.group_id)
    key, cached = begin_idempotency(user, request, payload)
    if cached:
        return cached
    table, record_id = execute_direct_domain_action(org, farm, user, task_type=payload.task_type,
        animal=animal, group=group, payload=_payload_dict(payload))
    body = success_body(data={"execution_context": "direct", "task": None,
        "subject": subject_payload(animal=animal, farm=farm),
        "result": reference_payload(public_result_type(table), record_id)}, message="Mobile domain record saved successfully.")
    store_idempotency(user, key, 200, body)
    return 200, body


@router.post("/health/cases/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error, 422: V2Error})
@mobile_atomic_mutation
def mobile_open_health_case(request, payload: HealthCaseIn):
    """Open a clinical case through the shared web/mobile case service."""
    from contract.health import _serialize_case, open_health_case

    user, org = _user_org(request)
    farm = require_farm(org, payload.farm_id, user)
    require_permission(user, org, "manage_health_case", farm=farm)
    animal = require_animal(org, payload.animal_id, farm) if payload.animal_id else None
    group = None
    if payload.group_id:
        from operations.services import _get_group
        group = _get_group(farm, payload.group_id)
    key, cached = begin_idempotency(user, request, payload)
    if cached:
        return cached
    case = open_health_case(org, farm, user, animal=animal, group=group,
                            title=payload.title, notes=payload.notes)
    body = success_body(data=_serialize_case(case), message="Health case opened successfully.")
    store_idempotency(user, key, 200, body)
    return 200, body


@router.get("/health/cases/{case_id}/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error})
def mobile_health_case_detail(request, case_id: int):
    from contract.health import _serialize_case
    user, org = _user_org(request)
    case = HealthCase.objects.select_related("farm", "animal", "group").filter(
        id=case_id, farm__in=authorized_farms(user, org)
    ).first()
    if case is None:
        raise ContractError(404, ErrorCode.HEALTH_CASE_NOT_FOUND, "Health case could not be found.")
    require_permission(user, org, Permissions.Health.VIEW, farm=case.farm)
    return 200, success_body(data=_serialize_case(case), message="Health case fetched successfully.")


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
@mobile_atomic_mutation
def accept(request, task_id: int):
    user, org, task = _mobile_task(request, task_id)
    require_permission(user, org, "complete_operation", farm=task.farm)
    key, cached = begin_idempotency(user, request)
    if cached:
        return cached
    body = success_body(data=serialize_task(accept_task(task, user)), message="Task accepted successfully.")
    store_idempotency(user, key, 200, body)
    return 200, body


@router.post("/tasks/{task_id}/start/", response={200: V2Success, 401: V2Error, 403: V2Error, 409: V2Error})
@mobile_atomic_mutation
def start(request, task_id: int):
    user, org, task = _mobile_task(request, task_id)
    require_permission(user, org, "complete_operation", farm=task.farm)
    key, cached = begin_idempotency(user, request)
    if cached:
        return cached
    body = success_body(data=serialize_task(start_task(task, user)), message="Task started successfully.")
    store_idempotency(user, key, 200, body)
    return 200, body


@router.post("/tasks/{task_id}/complete/", response={200: V2Success, 401: V2Error, 403: V2Error, 409: V2Error, 422: V2Error})
@mobile_atomic_mutation
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
@mobile_atomic_mutation
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
