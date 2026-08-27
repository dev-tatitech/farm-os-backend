#!/usr/bin/env python3
"""
Build FarmOS API documentation (HTML + PDF) from the live Django Ninja OpenAPI schema.

Run from the api/ directory:

    python docs/generate_api_docs.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(__file__).resolve().parent
HTML_PATH = OUTPUT_DIR / "FarmOS-API-Documentation.html"
PDF_PATH = OUTPUT_DIR / "FarmOS-API-Documentation.pdf"
OPENAPI_PATH = OUTPUT_DIR / "openapi.json"


def setup_django():
    sys.path.insert(0, str(API_DIR))
    os.chdir(API_DIR)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
    import django

    django.setup()
    from api.urls import api

    return api.get_openapi_schema()


def resolve_ref(schema: dict, components: dict) -> dict:
    if not schema:
        return {}
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        resolved = deepcopy(components.get("schemas", {}).get(name, {}))
        resolved["_ref_name"] = name
        return resolved
    if "allOf" in schema:
        merged: dict = {}
        for part in schema["allOf"]:
            merged.update(resolve_ref(part, components))
        extras = {k: v for k, v in schema.items() if k != "allOf"}
        merged.update(extras)
        return merged
    if "anyOf" in schema or "oneOf" in schema:
        options = schema.get("anyOf") or schema.get("oneOf")
        non_null = [o for o in options if o.get("type") != "null" and o.get("type") != ["null"]]
        chosen = non_null[0] if non_null else options[0]
        resolved = resolve_ref(chosen, components)
        if len(options) > 1:
            resolved["_nullable"] = True
        return resolved
    return deepcopy(schema)


def type_label(schema: dict, components: dict) -> str:
    schema = resolve_ref(schema, components)
    if schema.get("enum"):
        return " | ".join(repr(v) for v in schema["enum"])
    t = schema.get("type")
    fmt = schema.get("format")
    if t == "array":
        inner = type_label(schema.get("items") or {}, components)
        return f"array of {inner}"
    if t == "object":
        name = schema.get("_ref_name") or schema.get("title")
        return name or "object"
    if fmt:
        return f"{t} ({fmt})" if t else fmt
    if t:
        return t
    if schema.get("properties"):
        return "object"
    return "any"


def example_from_schema(schema: dict, components: dict, name: str = "", depth: int = 0):
    if depth > 6:
        return None
    schema = resolve_ref(schema, components)
    if schema.get("example") is not None:
        return schema["example"]
    if schema.get("enum"):
        return schema["enum"][0]
    t = schema.get("type")
    fmt = schema.get("format")
    key = name.lower()

    if t == "array":
        item = example_from_schema(schema.get("items") or {}, components, name, depth + 1)
        return [item] if item is not None else []
    if t == "object" or schema.get("properties"):
        props = schema.get("properties") or {}
        if not props:
            return {}
        return {
            k: example_from_schema(v, components, k, depth + 1)
            for k, v in props.items()
        }
    if t == "boolean":
        return True
    if t == "integer":
        if "page_size" in key:
            return 20
        if key == "page":
            return 1
        if key.endswith("_id") or key == "id":
            return 1
        return 1
    if t == "number":
        return 10.5
    if fmt == "email" or "email" in key:
        return "farmer@example.com"
    if fmt == "uuid" or "uuid" in key or key.endswith("_id") and "organization" in key:
        return "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    if fmt == "date-time":
        return "2026-03-15T08:30:00Z"
    if fmt == "date" or key.endswith("_date") or key in {"dob", "date"}:
        return "2026-03-15"
    if t == "string":
        if "password" in key:
            return "Str0ngPass!word"
        if "token" in key:
            return "reset_token_from_verify_step"
        if "otp" in key:
            return "123456"
        if "phone" in key:
            return "08012345678"
        if "tag" in key:
            return "COW-001"
        if "name" in key:
            return "Example name"
        if "notes" in key or "description" in key or "reason" in key or "message" in key:
            return "Free-text notes"
        if "currency" in key:
            return "NGN"
        if "status" in key:
            return "active"
        return "string"
    if schema.get("nullable") or schema.get("_nullable"):
        return None
    return None


FIELD_HELP = {
    "email": "Account email. Used as the login username.",
    "password": "Account password. Must pass Django password validators.",
    "confirm_password": "Must match password.",
    "otp": "6-digit one-time code sent to email.",
    "token": "Short-lived reset token returned after OTP verification.",
    "new_password": "Replacement password.",
    "farm_id": "Numeric ID of the farm this request applies to.",
    "organization_id": "UUID of the organization.",
    "animal_id": "Numeric ID of the animal.",
    "group_id": "Numeric ID of the animal group.",
    "page": "1-based page number for paginated lists.",
    "page_size": "How many rows to return per page.",
    "search": "Optional text filter (usually tag ID or name).",
    "status": "Record status filter or value.",
    "gender": "male or female.",
    "tag_id": "Unique ear-tag / identifier for the animal.",
    "source": "How the animal entered the farm (born, purchased, imported, …).",
    "source_type": "How the animal entered the farm.",
    "livestock_species_id": "v2 species ID from livestock master data.",
    "livestock_breed_id": "v2 breed ID from livestock master data.",
    "housing_unit_id": "v2 housing unit ID on the farm.",
    "species_id": "Legacy species ID (v1 endpoints).",
    "breed_id": "Legacy breed ID (v1 endpoints).",
    "unit_id": "Legacy farm unit ID (v1 endpoints).",
    "mother_id": "Dam animal ID. Required when source is born.",
    "dob": "Date of birth (YYYY-MM-DD).",
    "estimated_age_months": "Use when exact DOB is unknown.",
    "override_reason": "Required when staff override a breeding or sale restriction.",
}


def field_help(name: str, schema: dict, components: dict) -> str:
    if name in FIELD_HELP:
        return FIELD_HELP[name]
    schema = resolve_ref(schema, components)
    if schema.get("description"):
        return schema["description"]
    if schema.get("enum"):
        return "Allowed values: " + ", ".join(str(v) for v in schema["enum"])
    label = name.replace("_", " ")
    if name.endswith("_id"):
        return f"ID of the related {label[:-3]}."
    return f"{label[0].upper() + label[1:]}."


def collect_properties(schema: dict, components: dict) -> tuple[list[dict], list[str]]:
    schema = resolve_ref(schema, components)
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    rows = []
    for name, spec in props.items():
        resolved = resolve_ref(spec, components)
        rows.append(
            {
                "name": name,
                "type": type_label(spec, components),
                "required": name in required and not resolved.get("_nullable"),
                "help": field_help(name, spec, components),
            }
        )
    return rows, sorted(required)


MODULE_INTRO = {
    "Authentication": "Create an account, verify email with OTP, log in, and reset a password. Login sets HTTP-only cookies (access, refresh, CSRF). Most other endpoints expect those cookies.",
    "Admin panel": "Platform master data: species, breeds, housing, lifecycle stages, weight ranges, permission seeding, and public contact/newsletter forms.",
    "Global": "Shared lookup lists used across farms: unit types, group types, event types.",
    "Oganization module": "Organizations and farms. A user belongs to an organization; farms belong to that organization.",
    "User and Role management": "Invite staff, assign roles, and attach permission codes. Roles can be scoped to a farm.",
    "Farm": "Housing / farm units on a farm (v1 unit types and v2 housing units).",
    "Animals": "Animal records, groups, weights, milk, images, growth, and acquisition costs. Prefer v2 endpoints for livestock master data (species/breed/housing).",
    "Reproduction": "Insemination, pregnancy checks, births, offspring tags, and breeding eligibility rules.",
    "Health": "Treatments, vaccinations, quarantine, mortality, health alerts, and treatments that draw from pharmacy stock.",
    "Feed": "Feed master data, inventory, batches, plans, issuance, and confirmation. v3 is the current master-data model.",
    "MovementRecords": "Move animals between housing units, record sales, sale policy, sale readiness, and profitability.",
    "Alerts": "Generic farm alerts (vaccination due, pregnancy due, feed variance, treatment follow-up).",
    "Dashboard": "Read-only aggregates for the app home screens. Many routes exist in v1 and v2; v2 is the current livestock-master-data version.",
    "Finance": "Income and expense transactions, plus per-animal financial profiles.",
    "Pharmacy": "Drug catalogue, batches, stock, and expiry/low-stock alerts.",
    "Reports": "Paginated operational reports: animal cost, growth, feed/treatment cost, mortality, eligibility, sale readiness, stock valuation.",
}


AUTH_PUBLIC = {
    ("post", "/api/auth/new-account"),
    ("post", "/api/auth/login"),
    ("post", "/api/auth/forgot-password"),
    ("post", "/api/auth/verify-reset-otp"),
    ("post", "/api/auth/reset-password"),
    ("post", "/api/auth/resend_otp"),
    ("post", "/api/auth/email-validate"),
}

CUSTOM_JSON_OUTPUT = {
    "/api/auth/login": {
        "status": "Success",
        "message": "Login successful",
        "is_admin": False,
    },
    "/api/auth/new-account": {
        "success": True,
        "message": "Account created successfully",
    },
    "/api/auth/email-validate": {
        "success": True,
        "message": "Your email has been successfully verified.",
        "data": None,
    },
    "/api/auth/resend_otp": {
        "success": True,
        "message": "The OTP has been resent to your email.",
    },
    "/api/auth/forgot-password": {
        "success": True,
        "message": "If that email exists, an OTP has been sent.",
        "data": None,
    },
    "/api/auth/verify-reset-otp": {
        "success": True,
        "message": "OTP verified. Use the token to reset your password.",
        "data": {"token": "reset_token_from_verify_step"},
    },
    "/api/auth/reset-password": {
        "success": True,
        "message": "Password has been reset.",
        "data": None,
    },
    "/api/auth/refresh-token": {
        "success": True,
        "message": "Tokens rotated. New access cookie set.",
        "data": None,
    },
    "/api/auth/signout": {
        "success": True,
        "message": "Signed out.",
        "data": None,
    },
}


def operation_auth(method: str, path: str, op: dict) -> str:
    key = (method.lower(), path.rstrip("/") or path)
    if key in AUTH_PUBLIC or op.get("security") == []:
        return "Public (no login cookie)"
    return "Logged-in user (access-token cookie). Farm-scoped permission checked inside the handler."


def request_body_spec(op: dict):
    content = (op.get("requestBody") or {}).get("content") or {}
    for mime in (
        "application/json",
        "multipart/form-data",
        "application/x-www-form-urlencoded",
    ):
        if mime in content:
            return content[mime], mime
    return {}, None


def response_example(method: str, path: str, op: dict, components: dict) -> dict:
    if path in CUSTOM_JSON_OUTPUT:
        return deepcopy(CUSTOM_JSON_OUTPUT[path])
    responses = op.get("responses") or {}
    success = responses.get("200") or responses.get("201") or {}
    content = (success.get("content") or {}).get("application/json") or {}
    schema = resolve_ref(content.get("schema") or {}, components)
    name = schema.get("_ref_name") or schema.get("title") or ""
    is_list = "{page}" in path and method == "get"
    if name == "ListResponseSchema" or is_list or "num_pages" in (schema.get("properties") or {}):
        return {
            "success": True,
            "message": "Fetched successfully",
            "data": sample_data_for_path(path, method, "ListResponseSchema"),
            "num_pages": 3,
            "current_page": 1,
            "total_items": 42,
            "has_next": True,
            "has_previous": False,
        }
    if name == "Error_out":
        return {"status": "Error", "message": "Invalid credentials"}
    return {
        "success": True,
        "message": "Request completed",
        "data": sample_data_for_path(path, method, name),
    }


def sample_data_for_path(path: str, method: str, schema_name: str):
    p = path.lower()
    if "login" in p:
        return {
            "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "email": "farmer@example.com",
            "is_admin": False,
        }
    if "new-account" in p:
        return None
    if schema_name == "ListResponseSchema" or "/{" in path and method == "get":
        if "animal" in p:
            return [
                {
                    "id": 12,
                    "tag_id": "COW-001",
                    "gender": "female",
                    "status": "active",
                    "health_status": "healthy",
                }
            ]
        if "farm" in p:
            return [{"id": 1, "name": "North Paddock", "farm_code": "NP-01"}]
        if "alert" in p:
            return [{"id": 4, "title": "Vaccination due", "priority": "warning", "status": "open"}]
        return [{"id": 1, "name": "Example"}]
    if "dashboard" in p:
        return {
            "totals": {"animals": 120, "active": 110, "sold": 6, "dead": 4},
            "trends": [{"period": "2026-03", "value": 18}],
        }
    if "eligibility" in p:
        return {"eligible": False, "reasons": ["Minimum age not reached"], "can_override": True}
    if "readiness" in p or "profitability" in p:
        return {"ready": True, "estimated_profit": 45000.0, "currency": "NGN"}
    if method == "post":
        if "animal" in p and "v2" in p:
            return {
                "id": 15,
                "tag_id": "COW-001",
                "gender": "female",
                "species": "Cattle",
                "breed": "White Fulani",
                "housing_unit": "Pen A",
            }
        return {"id": 15}
    if method in {"patch", "put"}:
        return {"id": 15, "updated": True}
    if method == "delete":
        return None
    return {"id": 1}


def escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def human_title(op: dict, method: str, path: str) -> str:
    if op.get("summary") and op["summary"] not in {"Animals API health check", "Alerts API health check"}:
        return op["summary"]
    name = op.get("operationId") or ""
    name = re.sub(r"_$", "", name)
    name = name.replace("_", " ").strip()
    if name:
        return name[0].upper() + name[1:]
    return f"{method.upper()} {path}"


def explain_endpoint(method: str, path: str, title: str) -> str:
    m = method.lower()
    p = path.lower()
    if "login" in p:
        return "Checks email and password. On success the JSON body is small; the real session is HTTP-only cookies (access, refresh, CSRF). Send those cookies on later calls."
    if "new-account" in p:
        return "Registers a user with email + password. Sends a 6-digit OTP and sets an email cookie used by /email-validate."
    if "email-validate" in p:
        return "Confirms signup. Send the OTP. The email comes from the cookie set at registration, not from the body."
    if "forgot-password" in p:
        return "Starts password reset. Sends an OTP to the email if the account exists."
    if "verify-reset-otp" in p:
        return "Checks the reset OTP. Response data.token is what you send to /reset-password."
    if "reset-password" in p:
        return "Sets a new password using the token from verify-reset-otp. Does not take the OTP again."
    if "refresh-token" in p:
        return "Uses the refresh cookie to issue a new access cookie. No JSON body."
    if "signout" in p:
        return "Invalidates the refresh session and clears auth cookies."
    if m == "get" and "dashboard" in p:
        return "Returns aggregated numbers and trend series for this screen. Path farm_id selects the farm. No JSON body."
    if m == "get" and "{page}" in path:
        return "Returns a paginated list. Set page and page_size in the URL. Optional query filters narrow the list. Response uses the list envelope (data + num_pages)."
    if m == "get":
        return "Reads a record or a computed result. Path parameters identify the object."
    if m == "post" and "seed" in p:
        return "Setup helper: inserts default catalogue rows (rules, species, permissions, etc.). Body is often empty."
    if m == "post":
        return "Creates a record. Send the input fields below. On success, data usually contains the new id or the created object."
    if m == "patch":
        return "Partially updates a record. Only send fields you want to change. Omitted fields stay as they are."
    if m == "delete":
        return "Removes or deactivates a record identified by the path."
    return title


def iter_operations(spec: dict):
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            tags = op.get("tags") or ["Other"]
            yield tags[0], method.lower(), path, op


def build_html(spec: dict) -> str:
    components = spec.get("components") or {}
    grouped: dict[str, list] = defaultdict(list)
    for tag, method, path, op in iter_operations(spec):
        grouped[tag].append((method, path, op))

    tag_order = []
    seen = set()
    for tag, *_ in iter_operations(spec):
        if tag not in seen:
            tag_order.append(tag)
            seen.add(tag)

    parts = [
        """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>FarmOS API Documentation</title>
<style>
  :root { --ink:#1a1a1a; --muted:#555; --line:#ddd; --bg:#f6f6f4; --chip:#e8eef6; }
  * { box-sizing: border-box; }
  body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: var(--ink);
         margin: 0; background: #fff; line-height: 1.45; font-size: 13px; }
  .page { max-width: 900px; margin: 0 auto; padding: 32px 28px 80px; }
  h1 { font-size: 28px; margin: 0 0 8px; }
  h2 { font-size: 20px; margin: 40px 0 10px; page-break-before: always; }
  h2:first-of-type { page-break-before: auto; }
  h3 { font-size: 15px; margin: 0; }
  p { margin: 0 0 10px; }
  .muted { color: var(--muted); }
  .cover { padding: 48px 0 24px; }
  .endpoint { border: 1px solid var(--line); border-radius: 8px; margin: 16px 0 28px;
              page-break-inside: avoid; overflow: hidden; }
  .endpoint-hd { padding: 12px 14px; background: var(--bg); border-bottom: 1px solid var(--line); }
  .endpoint-bd { padding: 14px; }
  .method { display: inline-block; font-weight: 700; font-size: 11px; letter-spacing: .04em;
            padding: 2px 8px; border-radius: 4px; margin-right: 8px; vertical-align: middle; }
  .GET { background: #d9ead3; }
  .POST { background: #cfe2f3; }
  .PATCH { background: #fff2cc; }
  .PUT { background: #fce5cd; }
  .DELETE { background: #f4cccc; }
  code, pre { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 11.5px; }
  .path { font-weight: 600; }
  table { width: 100%; border-collapse: collapse; margin: 8px 0 12px; font-size: 12px; }
  th, td { border: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }
  th { background: var(--bg); font-weight: 600; }
  pre { background: #111; color: #f3f3f3; padding: 12px; border-radius: 6px; overflow-x: auto;
        white-space: pre-wrap; word-break: break-word; }
  .label { font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
           color: var(--muted); margin: 12px 0 6px; }
  .pill { display: inline-block; background: var(--chip); padding: 2px 8px; border-radius: 99px;
          font-size: 11px; margin-right: 6px; }
  .toc a { color: var(--ink); text-decoration: none; }
  .toc li { margin: 4px 0; }
  @media print {
    h2 { page-break-before: always; }
    .endpoint { page-break-inside: avoid; }
    a { text-decoration: none; color: inherit; }
  }
</style>
</head>
<body>
<div class="page">
<div class="cover">
<h1>FarmOS API documentation</h1>
<p class="muted">Tati FarmOS backend · Django Ninja · version 1.0</p>
<p>This guide is for product and engineering. Every endpoint lists what you send (URL pieces, query string, JSON body) and a sample JSON response. Field names match the live OpenAPI schema generated from the code.</p>
</div>
"""
    ]

    parts.append("<h2 id='overview'>How to call the API</h2>")
    parts.append(
        """
<p><span class="pill">Base URL</span> Local Docker: <code>http://127.0.0.1:8000</code> or Nginx <code>http://127.0.0.1:8081</code>. All routes below are prefixed with <code>/api</code>.</p>
<p><span class="pill">Docs</span> Interactive Swagger UI: <code>/api/docs</code>. Raw OpenAPI: <code>/api/openapi.json</code>.</p>
<p><span class="pill">Auth</span> After <code>POST /api/auth/login</code> the server sets cookies named <code>{app}_access_token</code>, <code>{app}_refresh_token</code>, and <code>{app}_csrf_token</code>. <code>app</code> is <code>client</code> or <code>admin</code> depending on the request host. Send cookies on later requests. For unsafe methods, send header <code>X-CSRFToken</code> matching the CSRF cookie.</p>
<p><span class="pill">JSON</span> Most bodies are <code>application/json</code>. A few animal-create routes use <code>multipart/form-data</code> so you can attach an image. Dates are <code>YYYY-MM-DD</code>. Datetimes are ISO-8601. Money examples use <code>NGN</code>.</p>
<p><span class="pill">Permissions</span> Most farm endpoints load the current user from the access cookie, resolve their organization, then check a permission code (for example <code>add_animal_details</code>) optionally scoped to that farm. Missing permission returns HTTP 403 with the envelope below.</p>
<h3>Standard success envelope</h3>
<pre>{
  "success": true,
  "message": "Human-readable summary",
  "data": {}
}</pre>
<h3>Standard paginated list</h3>
<pre>{
  "success": true,
  "message": "Fetched successfully",
  "data": [],
  "num_pages": 3,
  "current_page": 1,
  "total_items": 42,
  "has_next": true,
  "has_previous": false
}</pre>
<h3>Typical errors</h3>
<pre>{
  "success": false,
  "message": "Permission denied",
  "data": null
}</pre>
<p class="muted">Login failure uses a smaller shape: <code>{"status": "Error", "message": "Invalid credentials"}</code>. Some OTP failures return <code>{"detail": "..."}</code>.</p>
<p class="muted">v1 vs v2: older animal/farm/dashboard routes use <code>species_id</code>, <code>breed_id</code>, and <code>unit_id</code>. v2/v3 routes use livestock master data: <code>livestock_species_id</code>, <code>livestock_breed_id</code>, <code>housing_unit_id</code>. Prefer v2/v3 for new clients.</p>
"""
    )

    parts.append("<h2 id='toc'>Contents</h2><ol class='toc'>")
    for tag in tag_order:
        slug = re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-")
        parts.append(f"<li><a href='#{slug}'>{escape(tag)}</a> ({len(grouped[tag])} endpoints)</li>")
    parts.append("</ol>")

    for tag in tag_order:
        slug = re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-")
        intro = MODULE_INTRO.get(tag, "")
        parts.append(f"<h2 id='{slug}'>{escape(tag)}</h2>")
        if intro:
            parts.append(f"<p>{escape(intro)}</p>")

        for method, path, op in grouped[tag]:
            title = human_title(op, method, path)
            params = op.get("parameters") or []
            path_params = [p for p in params if p.get("in") == "path"]
            query_params = [p for p in params if p.get("in") == "query"]
            body, body_mime = request_body_spec(op)
            body_schema = resolve_ref((body or {}).get("schema") or {}, components) if body else {}
            body_props, _ = collect_properties(body_schema, components) if body_schema else ([], [])
            req_example = example_from_schema(body_schema, components) if body_schema else None
            if isinstance(req_example, dict) and not req_example and not body_props:
                req_example = None
            res_example = response_example(method, path, op, components)
            auth = operation_auth(method, path, op)

            parts.append('<div class="endpoint">')
            parts.append('<div class="endpoint-hd">')
            parts.append(
                f'<span class="method {method.upper()}">{method.upper()}</span>'
                f'<span class="path">{escape(path)}</span>'
            )
            parts.append(f"<h3 style='margin-top:8px'>{escape(title)}</h3>")
            parts.append("</div><div class='endpoint-bd'>")
            parts.append(f"<p>{escape(explain_endpoint(method, path, title))}</p>")
            parts.append(f"<p><span class='pill'>Auth</span> {escape(auth)}</p>")

            if path_params:
                parts.append("<div class='label'>URL parameters</div><table>")
                parts.append("<tr><th>Name</th><th>Type</th><th>What to send</th></tr>")
                for p in path_params:
                    schema = p.get("schema") or {}
                    parts.append(
                        "<tr>"
                        f"<td><code>{escape(p.get('name'))}</code></td>"
                        f"<td>{escape(type_label(schema, components))}</td>"
                        f"<td>{escape(field_help(p.get('name'), schema, components))}</td>"
                        "</tr>"
                    )
                parts.append("</table>")

            if query_params:
                parts.append("<div class='label'>Query parameters (optional unless marked)</div><table>")
                parts.append("<tr><th>Name</th><th>Type</th><th>Required</th><th>What to send</th></tr>")
                for p in query_params:
                    schema = p.get("schema") or {}
                    req = "yes" if p.get("required") else "no"
                    parts.append(
                        "<tr>"
                        f"<td><code>{escape(p.get('name'))}</code></td>"
                        f"<td>{escape(type_label(schema, components))}</td>"
                        f"<td>{req}</td>"
                        f"<td>{escape(field_help(p.get('name'), schema, components))}</td>"
                        "</tr>"
                    )
                parts.append("</table>")

            if body_props:
                if body_mime == "multipart/form-data":
                    parts.append(
                        "<p><span class='pill'>Input type</span> "
                        "<code>multipart/form-data</code> (form fields, not a JSON body). "
                        "If an <code>image</code> field is listed, attach a file.</p>"
                    )
                    parts.append("<div class='label'>Form fields (input)</div><table>")
                else:
                    parts.append("<div class='label'>JSON body fields (input)</div><table>")
                parts.append("<tr><th>Field</th><th>Type</th><th>Required</th><th>What to send</th></tr>")
                for row in body_props:
                    parts.append(
                        "<tr>"
                        f"<td><code>{escape(row['name'])}</code></td>"
                        f"<td>{escape(row['type'])}</td>"
                        f"<td>{'yes' if row['required'] else 'no'}</td>"
                        f"<td>{escape(row['help'])}</td>"
                        "</tr>"
                    )
                parts.append("</table>")
                if body_mime == "multipart/form-data":
                    parts.append("<div class='label'>Example form values (shown as JSON for clarity)</div>")
                else:
                    parts.append("<div class='label'>Example request body</div>")
                parts.append(f"<pre>{escape(json.dumps(req_example, indent=2, default=str))}</pre>")
            elif method in {"post", "patch", "put"}:
                parts.append("<p class='muted'>No JSON body. Path (and optional query) parameters are the input.</p>")
            else:
                parts.append("<p class='muted'>No JSON body. Input is the URL and any query parameters above.</p>")

            parts.append("<div class='label'>Example JSON response (output)</div>")
            parts.append(f"<pre>{escape(json.dumps(res_example, indent=2, default=str))}</pre>")
            parts.append("</div></div>")

    parts.append(
        "<p class='muted'>Generated from the Django Ninja OpenAPI schema. Regenerated by "
        "<code>python docs/generate_api_docs.py</code>.</p></div></body></html>"
    )
    return "".join(parts)


def html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    import shutil
    import subprocess

    chrome_candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chrome"),
    ]
    chrome = next((c for c in chrome_candidates if c and Path(c).exists()), None)
    if chrome:
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            f"--print-to-pdf={pdf_path}",
            "--no-pdf-header-footer",
            html_path.as_uri(),
        ]
        subprocess.run(cmd, check=True)
        return

    try:
        from weasyprint import HTML

        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        return
    except Exception:
        pass

    raise SystemExit(
        "Could not find Chrome/Edge or WeasyPrint to write the PDF. "
        f"HTML is ready at {html_path}"
    )


def main():
    print("Loading OpenAPI from Django Ninja…")
    spec = setup_django()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_text(json.dumps(spec, indent=2, default=str))
    html = build_html(spec)
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {HTML_PATH}")
    print("Rendering PDF…")
    html_to_pdf(HTML_PATH, PDF_PATH)
    print(f"Wrote {PDF_PATH}")


if __name__ == "__main__":
    main()
