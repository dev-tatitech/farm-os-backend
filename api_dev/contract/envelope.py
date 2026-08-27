from math import ceil
from typing import Any, Optional

from ninja import Schema

from .codes import ErrorCode


class V2Success(Schema):
    success: bool = True
    code: str
    message: str
    data: Any
    meta: Optional[Any] = None


class V2Error(Schema):
    success: bool = False
    code: str
    message: str
    data: Optional[Any] = None
    errors: dict
    retryable: bool


def success_body(
    data: Any = None,
    message: str = "Request completed successfully.",
    code: str = ErrorCode.REQUEST_SUCCESSFUL,
    meta: Any = None,
) -> dict:
    return {
        "success": True,
        "code": code,
        "message": message,
        "data": {} if data is None else data,
        "meta": meta,
    }


def error_body(
    code: str,
    message: str,
    errors: Optional[dict] = None,
    retryable: bool = False,
    data: Any = None,
) -> dict:
    return {
        "success": False,
        "code": code,
        "message": message,
        "data": data,
        "errors": errors or {},
        "retryable": retryable,
    }


def pagination_meta(page: int, page_size: int, total_items: int) -> dict:
    total_pages = ceil(total_items / page_size) if page_size else 0
    return {
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        }
    }
