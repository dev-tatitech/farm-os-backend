from django.db.models import Q
from ninja import Router

from account.models import User
from animals.models import Animal
from operations.models import Task
from operations.services import serialize_task

from .authz import require_farm, require_permission, require_user, resolve_organization
from .envelope import V2Error, V2Success, success_body
from common.permissions import Permissions

search_router = Router(tags=["Search"])


@search_router.get(
    "/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Search animals, people, and tasks",
)
def search(request, q: str, farm_id: int = None, limit: int = 10):
    user = require_user(request)
    org = resolve_organization(user)
    require_permission(user, org, Permissions.Animal.VIEW)
    limit = max(1, min(limit or 10, 25))
    farm = require_farm(org, farm_id, user) if farm_id is not None else None
    query = (q or "").strip()
    animals_qs = Animal.objects.filter(farm__organization=org)
    tasks_qs = Task.objects.filter(organization=org)
    if farm:
        animals_qs = animals_qs.filter(farm=farm)
        tasks_qs = tasks_qs.filter(farm=farm)
    animals = []
    people = []
    tasks = []
    if query:
        animals = list(
            animals_qs.filter(Q(tag_id__icontains=query) | Q(notes__icontains=query))
            .select_related("farm")[:limit]
        )
        people_qs = User.objects.filter(Q(organization=org) | Q(id=org.user_id)).filter(
            Q(email__icontains=query) | Q(username__icontains=query)
        )
        people = list(people_qs.distinct()[:limit])
        tasks = list(
            tasks_qs.filter(Q(title__icontains=query) | Q(description__icontains=query))
            .select_related("animal", "assigned_to", "created_by", "farm")[:limit]
        )
    data = {
        "query": query,
        "animals": [
            {
                "id": a.id,
                "tag_id": a.tag_id,
                "farm_id": a.farm_id,
                "status": a.status,
            }
            for a in animals
        ],
        "people": [
            {"id": str(p.id), "email": p.email, "username": p.username}
            for p in people
        ],
        "tasks": [serialize_task(t) for t in tasks],
    }
    return 200, success_body(data=data, message="Search completed.")
