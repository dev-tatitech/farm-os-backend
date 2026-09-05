"""Unified development OpenAPI at /api/docs — legacy /api/* plus /api/v2/*."""
from __future__ import annotations

import copy
import re
from typing import Any

from .registry import DEPRECATED, REGISTRY

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "options", "head", "trace"})

# Superseded by GET /api/v2/animals/{animal_id}/profile/ — hide from dev docs only.
_EXTRA_DEPRECATED_DOC_PATHS = (
    "/api/animals/animal-profile/{animal_id}",
)


def _normalize_path(path: str) -> str:
    return path if path.startswith("/") else f"/{path}"


def _path_pattern(path: str) -> str:
    """Normalize OpenAPI path params so {id} and {animal_id} compare equal."""
    return re.sub(r"\{[^}]+\}", "{}", _normalize_path(path).rstrip("/"))


def _deprecated_doc_patterns() -> set[str]:
    patterns: set[str] = {_path_pattern(p) for p in _EXTRA_DEPRECATED_DOC_PATHS}
    for row in REGISTRY:
        if row["status"] != DEPRECATED:
            continue
        endpoint = row["endpoint"].strip()
        match = re.match(r"^(?:GET|POST|PATCH|PUT|DELETE)\s+(/api/\S+)$", endpoint)
        if match:
            patterns.add(_path_pattern(match.group(1)))
    return patterns


def _is_deprecated_doc_path(path: str, deprecated_patterns: set[str]) -> bool:
    return _path_pattern(path) in deprecated_patterns


def merge_dev_openapi(dev_schema: dict[str, Any], v2_schema: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dev_schema)
    merged_paths = merged.setdefault("paths", {})
    deprecated_patterns = _deprecated_doc_patterns()

    for path in list(merged_paths.keys()):
        if _is_deprecated_doc_path(path, deprecated_patterns):
            del merged_paths[path]

    for path, operations in (v2_schema.get("paths") or {}).items():
        if path in merged_paths:
            continue
        merged_paths[path] = copy.deepcopy(operations)

    tag_names = {tag["name"] for tag in merged.get("tags", []) if isinstance(tag, dict)}
    for path, operations in merged_paths.items():
        for method, spec in operations.items():
            if method not in HTTP_METHODS or not isinstance(spec, dict):
                continue
            for tag in spec.get("tags", []):
                if tag not in tag_names:
                    merged.setdefault("tags", []).append({"name": tag})
                    tag_names.add(tag)

    info = merged.setdefault("info", {})
    info["title"] = "FarmOS API — Dev"
    info["version"] = "2.2"
    info["description"] = "Read each endpoint carefully. If there is any issue, contact the backend team."
    return merged


def patch_dev_openapi(dev_api, v2_api) -> None:
    original = dev_api.get_openapi_schema

    def merged_schema(*args, **kwargs):
        return merge_dev_openapi(original(*args, **kwargs), v2_api.get_openapi_schema())

    dev_api.get_openapi_schema = merged_schema
