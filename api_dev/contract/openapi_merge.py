"""Merge legacy-approved `/api/*` routes into the v2 OpenAPI schema for `/api/v2/docs`."""
from __future__ import annotations

import copy
import re
from typing import Any

from .registry import LEGACY, REGISTRY

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "options", "head", "trace"})

# Registry uses /api/reproduction/; legacy routes live under /api/reproductions/.
_PREFIX_ALIASES = {
    "/api/reproduction/": "/api/reproductions/",
}

# Coarse registry rows that should not pull the entire animals domain into v2 docs.
_PREFIX_OVERRIDES = {
    "/api/animals/": "/api/animals/milk/",
}


def _normalize_path(path: str) -> str:
    return path if path.startswith("/") else f"/{path}"


def _same_path(a: str, b: str) -> bool:
    return _normalize_path(a).rstrip("/") == _normalize_path(b).rstrip("/")


def _apply_prefix_aliases(path: str) -> str:
    for alias, repl in _PREFIX_ALIASES.items():
        if path.startswith(alias):
            return repl + path[len(alias) :]
    return path


def _legacy_merge_rules() -> tuple[set[str], set[str]]:
    exact: set[str] = set()
    prefixes: set[str] = set()
    legacy_domains: set[str] = set()
    for row in REGISTRY:
        if row["status"] != LEGACY:
            continue
        legacy_domains.add(row["domain"])
        endpoint = row["endpoint"].strip()
        match = re.match(r"^(GET|POST|PATCH|PUT|DELETE)\s+(/api/\S+)$", endpoint)
        if match:
            exact.add(_normalize_path(match.group(2)))
            continue
        if endpoint.startswith("/api/"):
            path = _normalize_path(endpoint)
            path = _PREFIX_OVERRIDES.get(path, path)
            prefixes.add(_apply_prefix_aliases(path))
    if "Health" in legacy_domains:
        prefixes.add("/api/health/")
    return exact, prefixes


def _domain_for_path(path: str) -> str:
    for row in REGISTRY:
        if row["status"] != LEGACY:
            continue
        endpoint = row["endpoint"].strip()
        match = re.match(r"^(?:GET|POST|PATCH|PUT|DELETE)\s+(/api/\S+)$", endpoint)
        candidate = match.group(1) if match else endpoint
        candidate = _apply_prefix_aliases(_PREFIX_OVERRIDES.get(candidate, candidate))
        if _same_path(path, candidate) or path.startswith(candidate.rstrip("/")):
            return row["domain"]
    return "Legacy"


def _legacy_tag(path: str, domain: str) -> str:
    if _same_path(path, "/api/auth/login"):
        return "Session (legacy login, still required)"
    return f"Legacy (approved) — {domain}"


def _decorate_legacy_operation(operation: dict[str, Any], path: str) -> dict[str, Any]:
    op = copy.deepcopy(operation)
    domain = _domain_for_path(path)
    tag = _legacy_tag(path, domain)
    op["tags"] = [tag]
    note = (
        "Legacy-approved route (not under `/api/v2/`). Uses the legacy JSON envelope, "
        "not the v2 `{success, code, message, data}` shape. Authenticate with "
        "`POST /api/auth/login` and send session cookies on subsequent calls."
    )
    existing = (op.get("description") or "").strip()
    op["description"] = f"{existing}\n\n{note}" if existing else note
    op["x-contract-status"] = "legacy_approved"
    return op


def merge_legacy_openapi(v2_schema: dict[str, Any], legacy_schema: dict[str, Any]) -> dict[str, Any]:
    exact, prefixes = _legacy_merge_rules()
    merged = copy.deepcopy(v2_schema)
    merged_paths = merged.setdefault("paths", {})
    legacy_paths = legacy_schema.get("paths", {})

    for path, operations in legacy_paths.items():
        norm = _normalize_path(path)
        if not (
            any(_same_path(norm, candidate) for candidate in exact)
            or any(norm.startswith(prefix.rstrip("/")) for prefix in prefixes)
        ):
            continue
        if path in merged_paths:
            continue
        merged_paths[path] = {}
        for method, spec in operations.items():
            if method not in HTTP_METHODS or not isinstance(spec, dict):
                merged_paths[path][method] = spec
                continue
            merged_paths[path][method] = _decorate_legacy_operation(spec, norm)

    tag_names = {tag["name"] for tag in merged.get("tags", []) if isinstance(tag, dict)}
    for path in merged_paths:
        for method, spec in merged_paths[path].items():
            if method not in HTTP_METHODS or not isinstance(spec, dict):
                continue
            for tag in spec.get("tags", []):
                if tag not in tag_names:
                    merged.setdefault("tags", []).append({"name": tag})
                    tag_names.add(tag)

    info = merged.setdefault("info", {})
    description = (info.get("description") or "").strip()
    extra = (
        "This spec includes all `/api/v2/*` contract routes plus legacy-approved `/api/*` "
        "routes from `GET /api/v2/registry/` (login, health writes, reproduction, feed, "
        "production, finance, reports, movement, master data). Legacy routes keep their "
        "original URLs and response envelopes."
    )
    info["description"] = f"{description}\n\n{extra}" if description else extra
    return merged


def patch_v2_openapi(v2_api, legacy_api) -> None:
    original = v2_api.get_openapi_schema

    def merged_schema(*args, **kwargs):
        return merge_legacy_openapi(original(*args, **kwargs), legacy_api.get_openapi_schema())

    v2_api.get_openapi_schema = merged_schema
