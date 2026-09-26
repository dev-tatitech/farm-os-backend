"""v2 direct domain execution, independent of Operations task creation."""

from common.mutations import atomic_mutation
from ninja import Router

from operations.models import Task
from operations.services import execute_direct_domain_action, public_result_type

from .authz import require_animal, require_farm, require_permission, require_user, resolve_organization
from .envelope import V2Error, V2Success, success_body
from .exceptions import ContractError
from .identity import reference_payload, subject_payload
from .ops import _domain_complete_perm, _payload_dict
from .schemas import DirectDomainActionIn


domain_actions_router = Router(tags=["Domain actions"])


@domain_actions_router.post(
    "/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error, 409: V2Error, 422: V2Error},
    summary="Record an authorized ad-hoc domain action",
)
@atomic_mutation
def record_direct_domain_action(request, payload: DirectDomainActionIn):
    """Write the authoritative record directly, without making a Task."""
    user = require_user(request)
    org = resolve_organization(user)
    farm = require_farm(org, payload.farm_id, user)
    if payload.task_type not in Task.Type.values or payload.task_type == Task.Type.GENERIC:
        raise ContractError(422, "VALIDATION_ERROR", "Unsupported direct domain action type.")
    context = Task(task_type=payload.task_type, farm=farm)
    require_permission(user, org, *_domain_complete_perm(context), farm=farm)
    animal = require_animal(org, payload.animal_id, farm) if payload.animal_id else None
    group = None
    if payload.group_id:
        from operations.services import _get_group

        group = _get_group(farm, payload.group_id)
    table, record_id = execute_direct_domain_action(
        org,
        farm,
        user,
        task_type=payload.task_type,
        animal=animal,
        group=group,
        payload=_payload_dict(payload),
    )
    return 200, success_body(
        data={
            "execution_context": "direct",
            "task": None,
            "subject": subject_payload(animal=animal, farm=farm),
            "result": reference_payload(public_result_type(table), record_id),
        },
        message="Domain action recorded successfully.",
    )
