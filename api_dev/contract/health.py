from common.mutations import atomic_mutation
from common.access import authorized_farms
from django.utils import timezone
from ninja import Router

from common.permissions import Permissions
from health.models import HealthAlert, HealthCase, HealthObservation, TreatmentRecord
from operations.models import Task
from operations.services import as_datetime, create_task, emit_event, json_value, notify_farm_capabilities, serialize_task

from .authz import require_animal, require_farm, require_permission, require_user, resolve_organization
from .codes import ErrorCode
from .envelope import V2Error, V2Success, success_body
from .exceptions import ContractError
from .helpers import begin_idempotency, paginated, store_idempotency
from .schemas import HealthCaseCloseIn, HealthCaseIn, ObservationAssessIn, ObservationIn

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
        "status": row.status,
        "assessment_note": row.assessment_note,
        "created_at": json_value(row.created_at),
    }


def open_health_case(org, farm, user, *, animal=None, group=None, title, notes=""):
    """Shared clinical case creation used by web and mobile adapters."""
    case = HealthCase.objects.create(farm=farm, animal=animal, group=group, title=title,
        notes=notes or "", opened_by=user)
    if animal and animal.status == "active":
        animal.health_status = "sick"; animal.save(update_fields=["health_status"])
    emit_event(farm, "health_case", f"Health case opened — {case.title}", case.notes,
        "health_case", case.id, user, animal=animal, group=group)
    notify_farm_capabilities(org, farm, ("manage_health_case", "assign_operation"), title="Health case opened",
        body=case.title, reference_table="health_case", reference_id=case.id,
        notification_type="health_case_opened")
    return case


@health_router.post(
    "/observations/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 422: V2Error},
    summary="Record a health observation",
)
@atomic_mutation
def create_observation(request, payload: ObservationIn):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, "record_health_observation")
    key, cached = begin_idempotency(user, request, payload)
    if cached:
        return cached
    farm = require_farm(org, payload.farm_id, user)
    if payload.create_case:
        require_permission(user, org, "manage_health_case", farm=farm)
    if payload.create_task:
        require_permission(user, org, "create_operation", farm=farm)
        if payload.assignee_id:
            require_permission(user, org, "assign_operation", farm=farm)
    if payload.group_id:
        from operations.services import _get_group
        _get_group(farm, payload.group_id)
    animal = require_animal(org, payload.animal_id, farm) if payload.animal_id else None
    case = None
    if payload.case_id:
        try:
            case = HealthCase.objects.get(id=payload.case_id, farm=farm)
        except HealthCase.DoesNotExist:
            raise ContractError(404, ErrorCode.HEALTH_CASE_NOT_FOUND, "Health case could not be found.")
    if payload.create_case and case is None:
        group = None
        if payload.group_id:
            from operations.services import _get_group
            group = _get_group(farm, payload.group_id)
        case = open_health_case(org, farm, user, animal=animal, group=group,
            title=(payload.symptoms or "Observation")[:120], notes=payload.symptoms or "")
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
    # An observation is not a diagnosis.  It only raises the existing derived
    # attention state; clinical state remains controlled by case management.
    if animal and animal.status == "active" and animal.health_status == "healthy":
        animal.health_status = "at_risk"
        animal.save(update_fields=["health_status"])
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
    notify_farm_capabilities(org, farm, ("assign_operation", "manage_health_case"),
        title="Animal observation reported", body=row.symptoms,
        reference_table="health_observation", reference_id=row.id,
        notification_type="health_observation_reported")
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
            source_type=Task.SourceType.HEALTH_OBSERVATION,
            source_id=row.id,
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
    qs = HealthObservation.objects.filter(farm__in=authorized_farms(user, org))
    if farm_id is not None:
        farm = require_farm(org, farm_id, user)
        qs = qs.filter(farm=farm)
    if animal_id is not None:
        qs = qs.filter(animal_id=animal_id)
    return 200, paginated(qs, page, page_size, _serialize_observation, "Observations fetched successfully.")


@health_router.post("/observations/{observation_id}/acknowledge/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error})
@atomic_mutation
def acknowledge_observation(request, observation_id: int):
    user = require_user(request); org = resolve_organization(user)
    require_permission(user, org, "record_health_observation")
    try: row = HealthObservation.objects.get(id=observation_id, farm__in=authorized_farms(user, org))
    except HealthObservation.DoesNotExist: raise ContractError(404, ErrorCode.OBSERVATION_NOT_FOUND, "Observation could not be found.")
    require_farm(org, row.farm_id, user)
    if row.status != HealthObservation.Status.OPEN: raise ContractError(409, ErrorCode.CONFLICT, "Only open observations can be acknowledged.")
    row.status = HealthObservation.Status.ACKNOWLEDGED; row.save(update_fields=["status"])
    emit_event(row.farm, "observation_acknowledged", "Health observation acknowledged", row.symptoms, "health_observation", row.id, user, animal=row.animal, group=row.group)
    return 200, success_body(data=_serialize_observation(row), message="Observation acknowledged successfully.")


@health_router.post("/observations/{observation_id}/assess/", response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error, 422: V2Error})
@atomic_mutation
def assess_observation(request, observation_id: int, payload: ObservationAssessIn):
    user = require_user(request); org = resolve_organization(user)
    require_permission(user, org, "manage_health_case")
    try: row = HealthObservation.objects.select_related("animal", "farm").get(id=observation_id, farm__in=authorized_farms(user, org))
    except HealthObservation.DoesNotExist: raise ContractError(404, ErrorCode.OBSERVATION_NOT_FOUND, "Observation could not be found.")
    require_farm(org, row.farm_id, user)
    if row.status not in (HealthObservation.Status.OPEN, HealthObservation.Status.ACKNOWLEDGED):
        raise ContractError(409, ErrorCode.CONFLICT, "This observation is already clinically assessed.")
    if payload.outcome not in ("resolved", "escalate_to_health_case"):
        raise ContractError(422, ErrorCode.VALIDATION_ERROR, "outcome must be resolved or escalate_to_health_case.")
    row.assessment_note = payload.note; row.assessed_by = user; row.assessed_at = timezone.now()
    if payload.outcome == "resolved":
        row.status = HealthObservation.Status.RESOLVED
    else:
        case = row.case or open_health_case(org, row.farm, user, animal=row.animal, group=row.group,
            title=payload.case_title or row.symptoms[:120], notes=payload.note)
        row.case = case; row.status = HealthObservation.Status.ESCALATED
        if row.case_id:
            emit_event(row.farm, "health_observation_escalated", "Observation linked to health case", case.title, "health_case", case.id, user, animal=row.animal, group=row.group)
    row.save(update_fields=["assessment_note", "assessed_by", "assessed_at", "case", "status"])
    emit_event(row.farm, "observation_assessed", "Health observation assessed", payload.note, "health_observation", row.id, user, animal=row.animal, group=row.group)
    return 200, success_body(data=_serialize_observation(row), message="Observation assessed successfully.")


@health_router.post(
    "/cases/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Open a health case",
)
@atomic_mutation
def create_case(request, payload: HealthCaseIn):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, "manage_health_case")
    farm = require_farm(org, payload.farm_id, user)
    animal = require_animal(org, payload.animal_id, farm) if payload.animal_id else None
    group = None
    if payload.group_id:
        from operations.services import _get_group
        group = _get_group(farm, payload.group_id)
    case = open_health_case(org, farm, user, animal=animal, group=group, title=payload.title, notes=payload.notes)
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
    qs = HealthCase.objects.filter(farm__in=authorized_farms(user, org))
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
@atomic_mutation
def close_case(request, case_id: int, payload: HealthCaseCloseIn):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, "manage_health_case")
    try:
        case = HealthCase.objects.get(id=case_id, farm__in=authorized_farms(user, org))
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
    emit_event(case.farm, "health_case_closed", "Health case closed", payload.notes or case.title, "health_case", case.id, user, animal=case.animal, group=case.group)
    return 200, success_body(data=_serialize_case(case), message="Health case closed successfully.")


@health_router.get(
    "/cases/{case_id}/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Health case detail",
)
def case_detail(request, case_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Health.VIEW)
    try:
        case = HealthCase.objects.select_related("animal", "farm").get(
            id=case_id, farm__in=authorized_farms(user, org)
        )
    except HealthCase.DoesNotExist:
        raise ContractError(404, ErrorCode.HEALTH_CASE_NOT_FOUND, "Health case could not be found.")
    require_farm(org, case.farm_id, user)
    observations = [
        _serialize_observation(row)
        for row in case.observations.all().order_by("-observed_at")[:50]
    ]
    treatments = [
        {
            "id": row.id,
            "diagnosis": row.diagnosis,
            "treatment": row.treatment,
            "severity": row.severity,
            "treatment_date": json_value(row.treatment_date),
        }
        for row in TreatmentRecord.objects.filter(case=case).order_by("-treatment_date")[:50]
    ]
    follow = treatments[0] if treatments else None
    open_tasks = list(
        Task.objects.filter(farm__in=authorized_farms(user, org), animal=case.animal)
        .exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
        .select_related("assigned_to", "animal", "farm", "created_by")[:20]
    )
    return 200, success_body(
        data={
            **_serialize_case(case),
            "animal": {"id": case.animal_id, "tag_id": case.animal.tag_id}
            if case.animal_id
            else None,
            "observations": observations,
            "diagnosis": treatments[0]["diagnosis"] if treatments else None,
            "treatments": treatments,
            "follow_up": {
                "required": bool(follow and getattr(TreatmentRecord.objects.filter(case=case).first(), "next_follow_up_date", None)),
                "next_due_at": json_value(
                    TreatmentRecord.objects.filter(case=case, next_follow_up_date__isnull=False)
                    .order_by("next_follow_up_date")
                    .values_list("next_follow_up_date", flat=True)
                    .first()
                ),
            },
            "assigned_users": [],
            "open_tasks": [serialize_task(task) for task in open_tasks],
        },
        message="Health case fetched successfully.",
    )


def _serialize_alert(row: HealthAlert) -> dict:
    from contract.identity import reference_payload, subject_payload

    return {
        "id": row.id,
        "alert_type": row.alert_type,
        "priority": row.severity,
        "title": row.alert_type.replace("_", " ").title(),
        "message": row.evidence,
        "status": row.status,
        "subject": subject_payload(animal=row.animal, farm=row.farm),
        "reference": reference_payload(
            "drug_batch" if row.drug_batch_id else "health_alert",
            row.drug_batch_id or row.id,
        ),
        "available_actions": ["view_subject", "create_task"],
        "detected_date": json_value(row.detected_date),
    }


@health_router.get(
    "/alerts/",
    response={200: V2Success, 401: V2Error, 403: V2Error},
    summary="Actionable health alerts",
)
def list_alerts(request, page: int = 1, page_size: int = 20, farm_id: int = None, status: str = "open"):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Health.VIEW)
    qs = HealthAlert.objects.filter(farm__in=authorized_farms(user, org)).select_related("animal", "farm", "drug_batch")
    if farm_id is not None:
        farm = require_farm(org, farm_id, user)
        qs = qs.filter(farm=farm)
    if status:
        qs = qs.filter(status=status)
    return 200, paginated(qs, page, page_size, _serialize_alert, "Alerts fetched successfully.")
