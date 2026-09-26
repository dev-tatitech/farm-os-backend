from typing import Callable, Optional
import hashlib
import json

from django.core.paginator import Paginator

from operations.models import IdempotencyKey

from .codes import ErrorCode
from .envelope import pagination_meta, success_body
from .exceptions import ContractError


def page_args(page: int, page_size: int):
    page = page or 1
    page_size = page_size or 20
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20
    if page_size > 100:
        page_size = 100
    return page, page_size


def paginated(qs, page: int, page_size: int, serialize: Callable, message: str):
    page, page_size = page_args(page, page_size)
    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page)
    return success_body(
        data=[serialize(item) for item in page_obj.object_list],
        message=message,
        meta=pagination_meta(page_obj.number, page_size, paginator.count),
    )


def client_request_id(request, payload=None) -> Optional[str]:
    body_id = None
    if payload is not None:
        body_id = getattr(payload, "client_request_id", None)
        if body_id is None and isinstance(payload, dict):
            body_id = payload.get("client_request_id")
    header_id = request.headers.get("X-Client-Request-Id") or request.headers.get(
        "X-Idempotency-Key"
    )
    value = body_id or header_id
    return str(value).strip() if value else None


def begin_idempotency(user, request, payload=None):
    if getattr(request, "_idempotency_managed", False):
        return None, None
    key = client_request_id(request, payload)
    if not key:
        return None, None
    if payload is not None:
        value = payload.dict() if hasattr(payload, "dict") else payload
        raw = json.dumps(value, sort_keys=True, default=str).encode()
    else:
        raw = getattr(request, "body", b"") or b""
    fingerprint = hashlib.sha256(request.method.encode() + b"\n" + request.path.encode() + b"\n" + raw).hexdigest()
    existing = IdempotencyKey.objects.filter(user=user, key=key).first()
    if existing and existing.request_fingerprint and existing.request_fingerprint != fingerprint:
        raise ContractError(409, ErrorCode.CONFLICT, "client_request_id was reused for a different request.")
    if existing and existing.response_json is not None:
        return key, (existing.status_code or 200, existing.response_json)
    if existing and existing.response_json is None:
        raise ContractError(
            409,
            ErrorCode.CONFLICT,
            "A request with this client_request_id is already in progress.",
            retryable=True,
        )
    IdempotencyKey.objects.create(
        user=user,
        key=key,
        method=request.method,
        path=request.path,
        request_fingerprint=fingerprint,
    )
    return key, None


def store_idempotency(user, key, status_code: int, body: dict):
    if not key:
        return
    IdempotencyKey.objects.filter(user=user, key=key).update(
        status_code=status_code, response_json=body
    )
