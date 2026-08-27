from django.utils import timezone
from ninja import Router

from common.permissions import Permissions
from health.models import HealthCase, HealthObservation
from operations.models import Task
from operations.services import as_datetime, create_task, emit_event, json_value

from .authz import require_animal, require_farm, require_permission, require_user, resolve_organization
from .codes import ErrorCode
from .envelope import V2Error, V2Success, success_body
from .exceptions import ContractError
from .helpers import begin_idempotency, paginated, store_idempotency
from .schemas import HealthCaseCloseIn, HealthCaseIn, ObservationIn

health_router = Router(tags=["Health"])


def _serialize_case(case: HealthCase) -> dict:
    return {
        "id": case.id,
        "farm_id": case.farm_id,
        "animal_id": case.animal_id,
        "group_id": case.group_id,
        "title": case.title,
        "notes": case.notes,
        "status": case.status,
        "opened_at": json_value(case.opened_at),
        "closed_at": json_value(case.closed_at),
    }


def _serialize_observation(row: HealthObservation) -> dict:
    return {
        "id": row.id,
        "farm_id": row.farm_id,
        "animal_id": row.animal_id,
        "group_id": row.group_id,
        "case_id": row.case_id,
        "observed_at": json_value(row.observed_at),
        "symptoms": row.symptoms,
        "severity": row.severity,
        "created_at": json_value(row.created_at),
    }


@health_router.post(
    "/observations/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 422: V2Error},
    summary="Record a health observation",
)
def create_observation(request, payload: ObservationIn):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Health.CREATE)
    key, cached = begin_idempotency(user, request, payload)
    if cached:
        return cached
    farm = require_farm(org, payload.farm_id, user)
    animal = require_animal(org, payload.animal_id, farm) if payload.animal_id else None
    case = None
    if payload.case_id:
        try:
            case = HealthCase.objects.get(id=payload.case_id, farm=farm)
        except HealthCase.DoesNotExist:
            raise ContractError(404, ErrorCode.HEALTH_CASE_NOT_FOUND, "Health case could not be found.")
    row = HealthObservation.objects.create(
        farm=farm,
        animal=animal,
        group_id=payload.group_id,
        case=case,
        observed_at=as_datetime(payload.observed_at),
        symptoms=payload.symptoms,
        severity=payload.severity or "mild",
        created_by=user,
    )
    emit_event(
        farm,
        "observation",
        "Health observation",
        row.symptoms,
        "health_observation",
        row.id,
        user,
        animal=animal,
        event_date=row.observed_at,
    )
    data = _serialize_observation(row)
    if payload.create_task:
        task = create_task(
            org=org,
            farm=farm,
            user=user,
            task_type=Task.Type.OBSERVATION,
            title=f"Follow-up observation — {payload.symptoms[:80]}",
            description=payload.symptoms,
            animal_id=payload.animal_id,
            group_id=payload.group_id,
            assignee_id=payload.assignee_id,
        )
        data["task_id"] = task.id
    body = success_body(data=data, message="Observation recorded successfully.")
    store_idempotency(user, key, 200, body)
    return 200, body


@health_router.get(
    "/observations/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="List health observations",
)
def list_observations(request, page: int = 1, page_size: int = 20, farm_id: int = None, animal_id: int = None):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Health.VIEW)
    qs = HealthObservation.objects.filter(farm__organization=org)
    if farm_id is not None:
        farm = require_farm(org, farm_id, user)
        qs = qs.filter(farm=farm)
    if animal_id is not None:
        qs = qs.filter(animal_id=animal_id)
    return 200, paginated(qs, page, page_size, _serialize_observation, "Observations fetched successfully.")


@health_router.post(
    "/cases/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Open a health case",
)
def create_case(request, payload: HealthCaseIn):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Health.CREATE)
    farm = require_farm(org, payload.farm_id, user)
    animal = require_animal(org, payload.animal_id, farm) if payload.animal_id else None
    case = HealthCase.objects.create(
        farm=farm,
        animal=animal,
        group_id=payload.group_id,
        title=payload.title,
        notes=payload.notes or "",
        opened_by=user,
    )
    emit_event(
        farm,
        "health_case",
        f"Health case opened — {case.title}",
        case.notes,
        "health_case",
        case.id,
        user,
        animal=animal,
    )
    return 200, success_body(data=_serialize_case(case), message="Health case opened successfully.")


@health_router.get(
    "/cases/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="List health cases",
)
def list_cases(request, page: int = 1, page_size: int = 20, farm_id: int = None, status: str = "open"):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Health.VIEW)
    qs = HealthCase.objects.filter(farm__organization=org)
    if farm_id is not None:
        farm = require_farm(org, farm_id, user)
        qs = qs.filter(farm=farm)
    if status:
        qs = qs.filter(status=status)
    return 200, paginated(qs, page, page_size, _serialize_case, "Health cases fetched successfully.")


@health_router.post(
    "/cases/{case_id}/close/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error},
    summary="Close a health case",
)
def close_case(request, case_id: int, payload: HealthCaseCloseIn):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Health.UPDATE, Permissions.Health.CREATE)
    try:
        case = HealthCase.objects.get(id=case_id, farm__organization=org)
    except HealthCase.DoesNotExist:
        raise ContractError(404, ErrorCode.HEALTH_CASE_NOT_FOUND, "Health case could not be found.")
    require_farm(org, case.farm_id, user)
    if case.status == HealthCase.Status.CLOSED:
        raise ContractError(409, ErrorCode.CONFLICT, "Health case is already closed.")
    case.status = HealthCase.Status.CLOSED
    case.closed_by = user
    case.closed_at = timezone.now()
    if payload.notes:
        case.notes = (case.notes + "\n" + payload.notes).strip()
    case.save()
    return 200, success_body(data=_serialize_case(case), message="Health case closed successfully.")
