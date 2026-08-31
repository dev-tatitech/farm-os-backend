from django.utils import timezone
from ninja import Router

from operations.models import Notification
from operations.services import serialize_notification

from .authz import require_user, resolve_organization
from .codes import ErrorCode
from .envelope import V2Error, V2Success, success_body
from .exceptions import ContractError
from .helpers import paginated

notify_router = Router(tags=["Notifications"])


@notify_router.get(
    "/unread-count/",
    response={200: V2Success, 401: V2Error},
    summary="Unread notification badge count",
)
def unread_count(request):
    user = require_user(request)
    org = resolve_organization(user)
    count = Notification.objects.filter(user=user, organization=org, is_read=False).count()
    return 200, success_body(
        data={"count": count}, message="Unread notification count fetched successfully."
    )


@notify_router.get(
    "/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="In-app notification inbox",
)
def list_notifications(request, page: int = 1, page_size: int = 20, unread_only: bool = False):
    user = require_user(request)
    org = resolve_organization(user)
    qs = Notification.objects.filter(user=user, organization=org)
    if unread_only:
        qs = qs.filter(is_read=False)
    return 200, paginated(qs, page, page_size, serialize_notification, "Notifications fetched successfully.")


@notify_router.post(
    "/{notification_id}/read/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Mark a notification as read",
)
def read_notification(request, notification_id: int):
    user = require_user(request)
    org = resolve_organization(user)
    try:
        row = Notification.objects.get(id=notification_id, user=user, organization=org)
    except Notification.DoesNotExist:
        raise ContractError(404, ErrorCode.NOTIFICATION_NOT_FOUND, "Notification could not be found.")
    if not row.is_read:
        row.is_read = True
        row.read_at = timezone.now()
        row.save(update_fields=["is_read", "read_at"])
    return 200, success_body(data=serialize_notification(row), message="Notification marked as read.")


@notify_router.post(
    "/read-all/",
    response={200: V2Success, 401: V2Error, 403: V2Error, 404: V2Error},
    summary="Mark all notifications as read",
)
def read_all_notifications(request):
    user = require_user(request)
    org = resolve_organization(user)
    updated = Notification.objects.filter(user=user, organization=org, is_read=False).update(
        is_read=True, read_at=timezone.now()
    )
    return 200, success_body(data={"updated": updated}, message="Notifications marked as read.")
