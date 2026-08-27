from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q
from ninja import Router, Query
from ninja.errors import HttpError
from account.auth import get_current_user
from account.models import User as users
from organization.models import Farm
from .models import Alert
from .schema import AlertSchema
from core.schema import APIResponse

router = Router(tags=["Alerts"])


@router.get("/", summary="Alerts API health check")
def root(request):
    return {"success": True, "message": "Alerts API is available"}


@router.post("/create/", response={200: APIResponse, 400: APIResponse, 403: APIResponse})
def create_alert(request, payload: AlertSchema):
    user_id = get_current_user(request)
    try:
        user =users.objects.get(id=user_id)
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")
    
    farm = get_object_or_404(Farm, id=payload.farm_id)

    alert = Alert(
        farm=farm,
        alert_type=payload.alert_type,
        priority=payload.priority,
        reference_table=payload.reference_table,
        reference_id=payload.reference_id,
        title=payload.title,
        message=payload.message,
        status=payload.status,
        due_date=payload.due_date,
        resolved_at=payload.resolved_at,
    )
    try:
        alert.full_clean()
        alert.save()
    except Exception as exc:
        raise HttpError(400, str(exc))

    return 200, APIResponse(success=True, message="Alert created", data={"id": alert.id})


@router.get("/alerts/{page}/{page_size}/{farm_id}", response={200: APIResponse, 400: APIResponse, 403: APIResponse})
def list_alerts(request, page: int, page_size: int, farm_id: int, q: str = Query(None)):
    user_id = get_current_user(request)
    try:
        users.objects.get(id=user_id)
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")

    qs = Alert.objects.filter(farm_id=farm_id)
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(message__icontains=q)
            | Q(reference_table__icontains=q)
        )

    paginator = Paginator(qs.order_by("-created_at"), page_size)
    page_obj = paginator.get_page(page)

    items = [
        {
            "id": a.id,
            "farm_id": a.farm_id,
            "alert_type": a.alert_type,
            "priority": a.priority,
            "reference_table": a.reference_table,
            "reference_id": a.reference_id,
            "title": a.title,
            "message": a.message,
            "status": a.status,
            "due_date": a.due_date,
            "created_at": a.created_at,
            "resolved_at": a.resolved_at,
        }
        for a in page_obj.object_list
    ]

    return 200, APIResponse(
        success=True,
        message="Alerts list",
        data={
            "items": items,
            "num_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "total_items": paginator.count,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        },
    )


@router.get("/alert/{alert_id}", response={200: APIResponse, 404: APIResponse, 403: APIResponse})
def get_alert(request, alert_id: int):
    user_id = get_current_user(request)
    try:
        users.objects.get(id=user_id)
    except users.DoesNotExist:
        raise HttpError(403, "Permission denied")

    alert = get_object_or_404(Alert, id=alert_id)
    data = {
        "id": alert.id,
        "farm_id": alert.farm_id,
        "alert_type": alert.alert_type,
        "priority": alert.priority,
        "reference_table": alert.reference_table,
        "reference_id": alert.reference_id,
        "title": alert.title,
        "message": alert.message,
        "status": alert.status,
        "due_date": alert.due_date,
        "created_at": alert.created_at,
        "resolved_at": alert.resolved_at,
    }
    return 200, APIResponse(success=True, message="Alert details", data=data)
