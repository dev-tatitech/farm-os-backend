"""Atomic writes with operation-bound replay of successful responses."""
import json
from functools import wraps

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.http import HttpResponse

from account.models import User
from contract.codes import ErrorCode
from contract.exceptions import ContractError
from operations.models import IdempotencyKey


def atomic_mutation(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        from account.sessions import authenticate_request
        actor = authenticate_request(request)
        payload = kwargs.get("payload") or kwargs.get("data")
        key = (getattr(payload, "client_request_id", None) or request.headers.get("X-Client-Request-Id")
               or request.headers.get("X-Idempotency-Key"))
        if key and len(key) > 128:
            raise ContractError(422, ErrorCode.VALIDATION_ERROR, "client_request_id is too long.")
        with transaction.atomic():
            # Serializes a user's retries, including first-use keys, and orders
            # governance changes against session refresh.
            User.objects.select_for_update().get(pk=actor.pk)
            actor.refresh_from_db()
            from account.sessions import active_account
            active_account(actor)
            existing = IdempotencyKey.objects.filter(user=actor, key=key).first() if key else None
            if existing:
                if existing.path != request.path or existing.method != request.method:
                    raise ContractError(409, ErrorCode.CONFLICT, "client_request_id belongs to another operation.")
                if existing.response_json is not None:
                    return existing.status_code, existing.response_json
                # Pre-Domain-01 incomplete keys have no proven result.
                raise ContractError(409, ErrorCode.CONFLICT, "An earlier request has no recorded result.", retryable=False)
            request._idempotency_managed = True
            result = view(request, *args, **kwargs)
            if isinstance(result, HttpResponse):
                status = result.status_code
                body = json.loads(result.content)
            else:
                status, body = result if isinstance(result, tuple) else (200, result)
                if hasattr(body, "model_dump"):
                    body = body.model_dump(mode="json")
                body = json.loads(json.dumps(body, cls=DjangoJSONEncoder))
            if status >= 400:
                transaction.set_rollback(True)
            elif key:
                IdempotencyKey.objects.create(user=actor, key=key, method=request.method,
                    path=request.path, status_code=status, response_json=body)
            return result
    return wrapped
