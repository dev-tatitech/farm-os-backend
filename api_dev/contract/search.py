from django.db.models import Q
from ninja import Router

from account.models import User
from animals.models import Animal
from operations.models import Task

from .authz import require_farm, require_user, resolve_organization
from .capabilities import build_capabilities, permission_codes_for_user
from .envelope import V2Error, V2Success, success_body
from .identity import can_view_people, display_name

search_router = Router(tags=["Search"])


def _search_person(user, org):
    from role.models import UserRole

    assignment = (
        UserRole.objects.filter(user=user)
        .select_related("role", "farm")
        .filter(Q(farm__organization=org) | Q(farm__isnull=True))
        .first()
    )
    return {
        "id": str(user.id),
        "display_name": display_name(user),
        "email": user.email,
        "role": assignment.role.name if assignment else None,
        "farm": assignment.farm.name if assignment and assignment.farm_id else None,
        "farm_id": assignment.farm_id if assignment else None,
    }


@search_router.get(
    "/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Search animals, people, and tasks",
)
def search(request, q: str, farm_id: int = None, limit: int = 10):
    user = require_user(request)
    org = resolve_organization(user)
    caps = build_capabilities(user, org, permission_codes_for_user(user, org))["capabilities"]
    limit = max(1, min(limit or 10, 25))
    farm = require_farm(org, farm_id, user) if farm_id is not None else None
    query = (q or "").strip()
    animals = []
    people = []
    tasks = []
    if query:
        if caps.get("view_animal_details"):
            animals_qs = Animal.objects.filter(farm__organization=org).select_related(
                "farm", "livestock_species", "livestock_breed", "species", "breed"
            )
            if farm:
                animals_qs = animals_qs.filter(farm=farm)
            animals = list(
                animals_qs.filter(Q(tag_id__icontains=query) | Q(notes__icontains=query))[:limit]
            )
        if can_view_people(user, org):
            people_qs = User.objects.filter(Q(organization=org) | Q(id=org.user_id)).filter(
                Q(email__icontains=query) | Q(username__icontains=query) | Q(first_name__icontains=query)
            )
            people = list(people_qs.distinct()[:limit])
        if caps.get("view_operation"):
            tasks_qs = Task.objects.filter(organization=org).select_related(
                "animal", "assigned_to", "created_by", "farm"
            )
            if farm:
                tasks_qs = tasks_qs.filter(farm=farm)
            tasks = list(
                tasks_qs.filter(Q(title__icontains=query) | Q(description__icontains=query))[:limit]
            )
    data = {
        "query": query,
        "animals": [
            {
                "id": a.id,
                "tag_id": a.tag_id,
                "species": a.livestock_species.name if a.livestock_species else None,
                "breed": a.livestock_breed.name if a.livestock_breed else None,
                "farm": a.farm.name,
                "farm_id": a.farm_id,
                "lifecycle_status": a.status,
                "status": a.status,
            }
            for a in animals
        ],
        "people": [_search_person(p, org) for p in people],
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "subject": {
                    "type": "animal",
                    "id": t.animal_id,
                    "label": t.animal.tag_id if t.animal_id else None,
                },
                "farm": t.farm.name,
                "assignee": display_name(t.assigned_to) if t.assigned_to_id else None,
                "due": t.due_at.isoformat() if t.due_at else None,
                "status": t.status,
            }
            for t in tasks
        ],
    }
    return 200, success_body(data=data, message="Search completed.")
