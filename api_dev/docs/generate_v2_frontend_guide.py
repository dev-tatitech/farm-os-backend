#!/usr/bin/env python3
"""
Frontend guide for FarmOS API Contract v2.1.

Writes HTML + PDF. Brand green sampled from tatifarmos.com screenshot (#209850).

    python docs/generate_v2_frontend_guide.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent
HTML_PATH = OUTPUT_DIR / "FarmOS-Frontend-API-Contract-v2.1.html"
PDF_PATH = OUTPUT_DIR / "FarmOS-Frontend-API-Contract-v2.1.pdf"
HTML_ALIAS = OUTPUT_DIR / "FarmOS-Frontend-API-Contract-v2.html"
PDF_ALIAS = OUTPUT_DIR / "FarmOS-Frontend-API-Contract-v2.pdf"

PRIMARY = "#209850"
PRIMARY_DARK = "#187A40"
INK = "#1F2937"
MUTED = "#6B7280"
MINT = "#E8F6EE"
LINE = "#E5E7EB"
PAGE_BG = "#F7FBF8"

ORG_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
USER_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
WORKER_ID = "0c1194a3-1e2b-4c5d-9f11-2a3b4c5d6e7f"


def envelope(data, message="Request completed successfully.", meta=None):
    body = {
        "success": True,
        "code": "REQUEST_SUCCESSFUL",
        "message": message,
        "data": data,
        "meta": meta,
    }
    return body


def err(code, message, http_note, errors=None, retryable=False):
    return {
        "_http": http_note,
        "success": False,
        "code": code,
        "message": message,
        "data": None,
        "errors": errors or {},
        "retryable": retryable,
    }


def page_meta(page=1, page_size=20, total=2):
    total_pages = 1 if total <= page_size else 2
    return {
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        }
    }


ACTOR = {"id": USER_ID, "display_name": "Amina Owner", "role_name": "Farm Manager"}
WORKER = {"id": WORKER_ID, "display_name": "Ibrahim Musa"}
SUBJECT = {"type": "animal", "id": 15, "label": "COW-001"}

ANIMAL_CARD = {
    "id": 15,
    "tag_id": "COW-001",
    "farm_id": 1,
    "species": "Cattle",
    "breed": "White Fulani",
    "gender": "female",
    "age_months": 18,
    "lifecycle_status": "active",
    "health_status": "healthy",
    "housing_unit": {"id": 4, "name": "Pen A"},
    "flags": {
        "is_pregnant": False,
        "is_lactating": False,
        "is_quarantine": False,
        "needs_attention": False,
    },
    "image_url": None,
}

TASK = {
    "id": 12,
    "farm_id": 1,
    "organization_id": ORG_ID,
    "animal_id": 15,
    "animal_tag": "COW-001",
    "group_id": None,
    "parent_id": None,
    "task_type": "vaccination",
    "title": "Vaccinate COW-001 — CBPP",
    "description": "Annual CBPP shot",
    "status": "assigned",
    "priority": "high",
    "due_at": "2026-08-28T08:00:00+00:00",
    "assigned_to": WORKER_ID,
    "assigned_to_email": "ibrahim@farm.example",
    "assignee": WORKER,
    "created_by": USER_ID,
    "actor": ACTOR,
    "accepted_at": None,
    "started_at": None,
    "completed_at": None,
    "cancelled_at": None,
    "unable_to_complete_at": None,
    "unable_reason_code": None,
    "source": {"type": "manual", "id": None},
    "result": None,
    "subject": SUBJECT,
    "result_reference_table": None,
    "result_reference_id": None,
    "created_at": "2026-08-27T07:00:00+00:00",
}

EVENT = {
    "id": 88,
    "farm_id": 1,
    "animal_id": 15,
    "animal_tag": "COW-001",
    "group_id": None,
    "event_type": "vaccination",
    "event_date": "2026-08-27T09:15:00+00:00",
    "event_title": "Vaccination - CBPP",
    "event_summary": "Administered in paddock",
    "reference_table": "vaccination",
    "reference_id": 41,
    "reference": {"type": "vaccination", "id": 41},
    "subject": SUBJECT,
    "created_by": WORKER_ID,
    "actor": {"id": WORKER_ID, "display_name": "Ibrahim Musa", "role_name": "Field Worker"},
    "created_at": "2026-08-27T09:15:00+00:00",
}

AUTH_401 = err("AUTHENTICATION_REQUIRED", "Authentication is required.", "401")
PERM_403 = err("PERMISSION_DENIED", "You do not have permission to perform this action.", "403")
NOT_FOUND = err("FARM_NOT_FOUND", "Farm could not be found.", "404")

ENDPOINTS = [
    {
        "tag": "Contract",
        "method": "GET",
        "path": "/api/v2/",
        "title": "Contract health",
        "explain": "Ping the official frontend contract. No cookie required. Use this to confirm the app is talking to /api/v2/ rather than legacy /api/*.",
        "auth": "Public",
        "success": envelope(
            {
                "contract": "FarmOS Frontend API Contract v2.1",
                "legacy_prefix": "/api/",
                "this_prefix": "/api/v2/",
                "identifiers": [
                    "livestock_species_id",
                    "livestock_breed_id",
                    "housing_unit_id",
                    "farm_id",
                    "organization_id",
                    "animal_id",
                    "group_id",
                ],
            },
            "v2.1 contract is available.",
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Contract",
        "method": "GET",
        "path": "/api/v2/registry/",
        "title": "Endpoint registry",
        "explain": "Machine-readable map of every MVP operation: v2, approved legacy, or deprecated. Cookie required. Use this instead of hard-coding which domains are still on /api/*.",
        "auth": "Cookie",
        "success": envelope(
            {
                "contract": "2.1",
                "entries": [
                    {"domain": "Auth", "operation": "Login", "endpoint": "POST /api/auth/login", "status": "legacy_approved", "notes": "Only approved non-v2 envelope."},
                    {"domain": "Animals", "operation": "List", "endpoint": "GET /api/v2/animals/", "status": "v2"},
                    {"domain": "Reproduction", "operation": "Pregnancy", "endpoint": "/api/reproduction/", "status": "legacy_approved"},
                ],
            },
            "Endpoint registry fetched successfully.",
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Session (legacy login, still required)",
        "method": "POST",
        "path": "/api/auth/login",
        "title": "Sign in (sets cookies)",
        "explain": "v2 does not replace login. POST email + password to the legacy auth route. Success JSON is small; the session is HTTP-only cookies client_access_token, client_refresh_token, client_csrf_token. Send those cookies on every /api/v2/ call. Do not parse v2 fields on this response.",
        "auth": "Public",
        "request": {"email": "ibrahim@farm.example", "password": "Str0ngPass!word"},
        "success": {"status": "Success", "message": "Login successful", "is_admin": False},
        "error": {"status": "Error", "message": "Invalid credentials"},
        "error_http": "401 — this shape is NOT the v2 envelope",
    },
    {
        "tag": "Users",
        "method": "GET",
        "path": "/api/v2/users/me/",
        "title": "Current user operational profile",
        "explain": "Call once after login to bootstrap the shell: identity, organization, farm-role assignments, permission codes, and work_summary for My Work badges. Task counts are live.",
        "auth": "Cookie",
        "success": envelope(
            {
                "id": USER_ID,
                "display_name": "Amina Owner",
                "email": "owner@farm.example",
                "username": "owner",
                "account_status": "Active",
                "is_admin": False,
                "organization": {
                    "id": ORG_ID,
                    "name": "Zaima Farms",
                    "code": "ZAIMA",
                    "status": "active",
                },
                "assignments": [
                    {
                        "role_id": 3,
                        "role_name": "Farm Manager",
                        "role_code": "farm_manager",
                        "farm_id": 1,
                        "farm_name": "North Paddock",
                    }
                ],
                "permissions": ["add_health", "view_animal_details", "view_health"],
                "work_summary": {"open_tasks": 2, "due_today": 1, "overdue_tasks": 1, "completed_today": 1},
            },
            "User profile fetched successfully.",
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Users",
        "method": "GET",
        "path": "/api/v2/users/me/capabilities/",
        "title": "Capabilities and navigation map",
        "explain": "Drive UI chrome from capabilities and navigation booleans. Do not infer menus from raw permission strings alone. operations and my_work are true when the user can view health/feed/animal work.",
        "auth": "Cookie",
        "success": envelope(
            {
                "is_organization_owner": True,
                "permissions": ["add_health", "view_animal_details"],
                "capabilities": {
                    "view_animal_details": True,
                    "add_animal_details": True,
                    "update_animal_details": True,
                    "view_health": True,
                    "record_health": True,
                    "record_health_observation": True,
                    "manage_health_case": True,
                    "view_feed": True,
                    "record_feed_activity": True,
                    "view_reproduction": True,
                    "add_reproduction": True,
                    "view_operation": True,
                    "create_operation": True,
                    "assign_operation": True,
                    "reassign_operation": True,
                    "complete_operation": True,
                    "cancel_operation": True,
                },
                "navigation": {
                    "dashboard": True,
                    "livestock": True,
                    "health": True,
                    "feed": True,
                    "reproduction": True,
                    "operations": True,
                    "my_work": True,
                    "people": True,
                    "reports": True,
                    "sales": False,
                },
            },
            "Capabilities fetched successfully.",
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Users",
        "method": "GET",
        "path": "/api/v2/users/me/activity/",
        "title": "Current user activity",
        "explain": "Timeline of events this user created. Paginated via query page and page_size. Read meta.pagination — not current_page / num_pages.",
        "auth": "Cookie",
        "query": [
            ("page", "int", "no", "1-based page, default 1"),
            ("page_size", "int", "no", "Default 20, max 100"),
        ],
        "success": envelope([EVENT], "Activity fetched successfully.", page_meta(total=1)),
        "error": AUTH_401,
    },
    {
        "tag": "Users",
        "method": "GET",
        "path": "/api/v2/users/me/tasks/",
        "title": "Tasks assigned to me",
        "explain": "Same records as My Work, including completed if you pass status. Use status=open for the inbox.",
        "auth": "Cookie",
        "query": [
            ("page", "int", "no", "1-based page"),
            ("page_size", "int", "no", "Default 20"),
            ("status", "string", "no", "open | assigned | accepted | completed | cancelled | unable_to_complete | overdue"),
        ],
        "success": envelope([TASK], "Tasks fetched successfully.", page_meta(total=1)),
        "error": AUTH_401,
    },
    {
        "tag": "Users",
        "method": "GET",
        "path": "/api/v2/users/",
        "title": "People list",
        "explain": "Org people picker. Requires Farm.UPDATE or org owner. Invite still uses approved legacy POST /api/admin/invite/.",
        "auth": "Cookie · manage people",
        "query": [("page", "int", "no", "Page"), ("page_size", "int", "no", "Page size")],
        "success": envelope(
            [
                {
                    "id": WORKER_ID,
                    "display_name": "Ibrahim Musa",
                    "email": "ibrahim@farm.example",
                    "account_status": "Active",
                }
            ],
            "People fetched successfully.",
            page_meta(total=1),
        ),
        "error": PERM_403,
    },
    {
        "tag": "Users",
        "method": "GET",
        "path": "/api/v2/users/{user_id}/",
        "title": "User operational profile",
        "explain": "Same people-auth as the list. Includes display_name, assignments, and work_summary.",
        "auth": "Cookie · manage people",
        "path_params": [("user_id", "uuid", "User UUID")],
        "success": envelope(
            {
                "id": WORKER_ID,
                "display_name": "Ibrahim Musa",
                "email": "ibrahim@farm.example",
                "phone": None,
                "account_status": "Active",
                "organization": {"id": ORG_ID, "name": "Zaima Farms", "code": "ZAIMA"},
                "assignments": [{"role_id": 4, "role_name": "Field Worker", "role_code": "e2e_field", "farm_id": 1, "farm_name": "North Paddock"}],
                "work_summary": {"open_tasks": 2, "due_today": 1, "overdue_tasks": 0, "completed_today": 1},
            },
            "User profile fetched successfully.",
        ),
        "error": err("USER_NOT_FOUND", "User could not be found.", "404"),
    },
    {
        "tag": "Users",
        "method": "GET",
        "path": "/api/v2/users/{user_id}/activity/",
        "title": "User activity",
        "explain": "Timeline of events this user created. Same people-auth.",
        "auth": "Cookie · manage people",
        "path_params": [("user_id", "uuid", "User UUID")],
        "query": [("page", "int", "no", "Page"), ("page_size", "int", "no", "Page size")],
        "success": envelope([EVENT], "Activity fetched successfully.", page_meta(total=1)),
        "error": AUTH_401,
    },
    {
        "tag": "Users",
        "method": "GET",
        "path": "/api/v2/users/{user_id}/tasks/",
        "title": "Tasks assigned to a user",
        "explain": "Manager view of one worker’s queue. Same filters as /users/me/tasks/.",
        "auth": "Cookie · manage people",
        "path_params": [("user_id", "uuid", "User UUID")],
        "query": [
            ("page", "int", "no", "Page"),
            ("page_size", "int", "no", "Page size"),
            ("status", "string", "no", "open | assigned | completed | …"),
        ],
        "success": envelope([TASK], "Tasks fetched successfully.", page_meta(total=1)),
        "error": AUTH_401,
    },
    {
        "tag": "Roles",
        "method": "GET",
        "path": "/api/v2/roles/",
        "title": "Roles list",
        "explain": "Org roles for people screens. Assigning a role still uses approved legacy POST /api/role/user-role/.",
        "auth": "Cookie · manage people",
        "success": envelope(
            [{"id": 3, "name": "Farm Manager", "code": "farm_manager", "organization_id": ORG_ID}],
            "Roles fetched successfully.",
            page_meta(total=1),
        ),
        "error": PERM_403,
    },
    {
        "tag": "Roles",
        "method": "GET",
        "path": "/api/v2/permissions/",
        "title": "Permissions catalog",
        "explain": "Permission codes the UI can show when editing roles.",
        "auth": "Cookie · manage people",
        "success": envelope(
            [{"id": 1, "code": "view_animal_details", "name": "View animal details", "module": "animals"}],
            "Permissions fetched successfully.",
            page_meta(total=1),
        ),
        "error": PERM_403,
    },
    {
        "tag": "Organizations",
        "method": "GET",
        "path": "/api/v2/organizations/{organization_id}/",
        "title": "Organization profile",
        "explain": "Operational org card for settings and home. organization_id is a UUID and must be the caller’s org.",
        "auth": "Cookie",
        "path_params": [("organization_id", "uuid", "Caller’s organization UUID")],
        "success": envelope(
            {
                "id": ORG_ID,
                "name": "Zaima Farms",
                "code": "ZAIMA",
                "status": "active",
                "industry": "Livestock",
                "country": "Nigeria",
                "state_region": "Kaduna",
                "logo": None,
                "is_owner": True,
                "counts": {
                    "farms": 1,
                    "people": 4,
                    "animals": 120,
                    "active_animals": 110,
                    "open_tasks": 6,
                },
            },
            "Organization fetched successfully.",
        ),
        "error": err("ORGANIZATION_NOT_FOUND", "Organization could not be found.", "404"),
    },
    {
        "tag": "Organizations",
        "method": "PATCH",
        "path": "/api/v2/organizations/{organization_id}/",
        "title": "Update organization",
        "explain": "Owner-only. Send only fields to change.",
        "auth": "Cookie · organization owner",
        "path_params": [("organization_id", "uuid", "Organization UUID")],
        "request": {"name": "Zaima Farms Ltd", "status": "active"},
        "success": envelope({"id": ORG_ID, "name": "Zaima Farms Ltd", "status": "active"}, "Organization updated successfully."),
        "error": PERM_403,
    },
    {
        "tag": "Organizations",
        "method": "GET",
        "path": "/api/v2/organizations/{organization_id}/summary/",
        "title": "Organization summary counts",
        "explain": "Compact counts for the org home header. Prefer this over chaining many legacy dashboard calls.",
        "auth": "Cookie",
        "path_params": [("organization_id", "uuid", "Organization UUID")],
        "success": envelope(
            {
                "organization_id": ORG_ID,
                "farms": 1,
                "animals": {
                    "total": 120,
                    "active": 110,
                    "sold": 6,
                    "dead": 4,
                    "quarantine": 2,
                    "pregnant": 9,
                },
                "open_tasks": 6,
                "roles": 3,
                "people": 4,
            },
            "Organization summary fetched successfully.",
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Organizations",
        "method": "GET",
        "path": "/api/v2/organizations/{organization_id}/activity/",
        "title": "Organization activity",
        "explain": "Unified event list across all farms in the org. Same event objects as /timeline/.",
        "auth": "Cookie",
        "path_params": [("organization_id", "uuid", "Organization UUID")],
        "query": [("page", "int", "no", "Page"), ("page_size", "int", "no", "Page size")],
        "success": envelope([EVENT], "Activity fetched successfully.", page_meta()),
        "error": AUTH_401,
    },
    {
        "tag": "Organizations",
        "method": "GET",
        "path": "/api/v2/organizations/{organization_id}/farms/",
        "title": "List farms",
        "explain": "Farm switcher. Each row includes animal_count.",
        "auth": "Cookie",
        "path_params": [("organization_id", "uuid", "Organization UUID")],
        "query": [("page", "int", "no", "Page"), ("page_size", "int", "no", "Page size")],
        "success": envelope(
            [
                {
                    "id": 1,
                    "name": "North Paddock",
                    "farm_code": "NP-01",
                    "status": "active",
                    "is_primary": True,
                    "farm_type": "Livestock",
                    "city": "Zaria",
                    "animal_count": 120,
                    "active_animals": 110,
                }
            ],
            "Farms fetched successfully.",
            page_meta(total=1),
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Farms",
        "method": "GET",
        "path": "/api/v2/farms/{farm_id}/",
        "title": "Farm profile",
        "explain": "Farm settings card plus live counts (animals, tasks, alerts, units). farm_id is an integer.",
        "auth": "Cookie · farm access",
        "path_params": [("farm_id", "int", "Farm numeric ID")],
        "success": envelope(
            {
                "id": 1,
                "organization_id": ORG_ID,
                "name": "North Paddock",
                "farm_code": "NP-01",
                "status": "active",
                "is_primary": True,
                "farm_type": "Livestock",
                "city": "Zaria",
                "location_address": "Kaduna–Zaria road",
                "latitude": 11.11,
                "longitude": 7.72,
                "country": "Nigeria",
                "state_region": "Kaduna",
                "counts": {
                    "animals": 120,
                    "active_animals": 110,
                    "sold": 6,
                    "dead": 4,
                    "quarantine": 2,
                    "open_tasks": 6,
                    "open_alerts": 3,
                    "housing_units": 8,
                    "farm_units": 4,
                },
            },
            "Farm fetched successfully.",
        ),
        "error": NOT_FOUND,
    },
    {
        "tag": "Farms",
        "method": "PATCH",
        "path": "/api/v2/farms/{farm_id}/",
        "title": "Update farm",
        "explain": "Partial update. Setting is_primary true clears primary on other farms in the org.",
        "auth": "Cookie · update_farm",
        "path_params": [("farm_id", "int", "Farm ID")],
        "request": {"name": "North Paddock", "city": "Zaria", "status": "active", "is_primary": True},
        "success": envelope({"id": 1, "name": "North Paddock", "is_primary": True}, "Farm updated successfully."),
        "error": PERM_403,
    },
    {
        "tag": "Farms",
        "method": "GET",
        "path": "/api/v2/farms/{farm_id}/overview/",
        "title": "Farm overview",
        "explain": "Profile plus health_breakdown and people_count for the farm home.",
        "auth": "Cookie · farm access",
        "path_params": [("farm_id", "int", "Farm ID")],
        "success": envelope(
            {
                "id": 1,
                "name": "North Paddock",
                "health_breakdown": {"healthy": 100, "sick": 8, "recovering": 2},
                "people_count": 3,
            },
            "Farm overview fetched successfully.",
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Farms",
        "method": "GET",
        "path": "/api/v2/farms/{farm_id}/timeline/",
        "title": "Farm timeline",
        "explain": "Events for one farm. Optional event_type filter uses canonical names: vaccination, treatment, feeding, sale, task_created, task_completed.",
        "auth": "Cookie · farm access",
        "path_params": [("farm_id", "int", "Farm ID")],
        "query": [
            ("page", "int", "no", "Page"),
            ("page_size", "int", "no", "Page size"),
            ("event_type", "string", "no", "Canonical event name"),
        ],
        "success": envelope([EVENT], "Timeline fetched successfully.", page_meta()),
        "error": AUTH_401,
    },
    {
        "tag": "Farms",
        "method": "GET",
        "path": "/api/v2/farms/{farm_id}/people/",
        "title": "Farm people",
        "explain": "Staff assigned to this farm (plus org owner). Use for assign-task pickers.",
        "auth": "Cookie · farm access",
        "path_params": [("farm_id", "int", "Farm ID")],
        "success": envelope(
            [
                {
                    "id": WORKER_ID,
                    "email": "ibrahim@farm.example",
                    "username": "ibrahim",
                    "is_owner": False,
                    "roles": [{"role": "Field Worker", "role_code": "e2e_field", "farm_id": 1}],
                }
            ],
            "People fetched successfully.",
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Farms",
        "method": "GET",
        "path": "/api/v2/farms/{farm_id}/units/",
        "title": "Housing and farm units",
        "explain": "housing_units are v2 livestock housing (housing_unit_id). farm_units are legacy pens. Prefer housing_units for new UI.",
        "auth": "Cookie · farm access",
        "path_params": [("farm_id", "int", "Farm ID")],
        "success": envelope(
            {
                "housing_units": [
                    {
                        "id": 4,
                        "kind": "housing_unit",
                        "name": "Pen A",
                        "status": "active",
                        "capacity": 20,
                        "occupancy": 12,
                        "location": "North",
                    }
                ],
                "farm_units": [
                    {"id": 2, "kind": "farm_unit", "name": "Barn 1", "code": "B1", "status": "active", "capacity": 30, "unit_type": "barn"}
                ],
            },
            "Units fetched successfully.",
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Farms",
        "method": "GET",
        "path": "/api/v2/farms/{farm_id}/alerts/",
        "title": "Farm attention alerts",
        "explain": "These are farm attention items, not tasks and not the notification inbox. Do not merge with /operations or /notifications.",
        "auth": "Cookie · farm access",
        "path_params": [("farm_id", "int", "Farm ID")],
        "query": [
            ("page", "int", "no", "Page"),
            ("page_size", "int", "no", "Page size"),
            ("status", "string", "no", "open (default) or resolved"),
        ],
        "success": envelope(
            [
                {
                    "id": 9,
                    "alert_type": "vaccination_due",
                    "priority": "warning",
                    "title": "Vaccination due",
                    "message": "COW-001 CBPP due",
                    "status": "open",
                    "due_date": "2026-08-29T00:00:00+00:00",
                    "created_at": "2026-08-20T00:00:00+00:00",
                }
            ],
            "Alerts fetched successfully.",
            page_meta(total=1),
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Animals",
        "method": "GET",
        "path": "/api/v2/animals/",
        "title": "List animals",
        "explain": "Herd cards. Each row is the same card shape as create/profile (id, tag_id, flags, lifecycle_status). Filter; do not infer pregnancy/sold from this list’s flags for writes.",
        "auth": "Cookie · view_animal_details",
        "query": [
            ("page", "int", "no", "Page"),
            ("page_size", "int", "no", "Page size"),
            ("farm_id", "int", "no", "Farm"),
            ("search", "string", "no", "Tag, notes, or numeric id"),
            ("livestock_species_id", "int", "no", "Species"),
            ("livestock_breed_id", "int", "no", "Breed"),
            ("gender", "string", "no", "female | male"),
            ("lifecycle_status", "string", "no", "active | sold | dead | transferred_out | culled"),
            ("health_status", "string", "no", "healthy | sick | at_risk | recovering"),
            ("housing_unit_id", "int", "no", "Housing unit"),
            ("is_pregnant", "bool", "no", "Filter pregnant"),
            ("is_lactating", "bool", "no", "Filter lactating"),
            ("is_quarantine", "bool", "no", "Filter quarantine"),
            ("needs_attention", "bool", "no", "sick, at_risk, or quarantine"),
            ("sort", "string", "no", "id | -id | tag_id | -tag_id | status | created_at"),
        ],
        "success": envelope([ANIMAL_CARD], "Animals fetched successfully.", page_meta(total=120)),
        "error": AUTH_401,
    },
    {
        "tag": "Animals",
        "method": "POST",
        "path": "/api/v2/animals/",
        "title": "Progressive animal create",
        "explain": "status must be active | sold | dead | transferred_out | culled (not pregnant/sick). tag_id is optional; empty/null generates INT-{uuid}. Breed and housing are optional. Born animals still need mother_id and dob. Optional client_request_id for offline retries.",
        "auth": "Cookie · add_animal_details",
        "request": {
            "farm_id": 1,
            "tag_id": None,
            "gender": "female",
            "source_type": "opening_record",
            "status": "active",
            "livestock_species_id": 1,
            "livestock_breed_id": 2,
            "housing_unit_id": 4,
            "estimated_age_months": 18,
            "notes": "Untagged opening record",
            "client_request_id": "create-untagged-001",
        },
        "success": envelope(
            {
                "id": 16,
                "tag_id": "INT-A1B2C3D4E5F6",
                "status": "active",
                "health_status": "healthy",
                "flags": {
                    "is_pregnant": False,
                    "is_lactating": False,
                    "is_quarantine": False,
                    "needs_attention": False,
                },
                "card": {**ANIMAL_CARD, "id": 16, "tag_id": "INT-A1B2C3D4E5F6"},
            },
            "Animal created successfully.",
        ),
        "error": err("DUPLICATE_RECORD", "Tag ID already exists.", "409"),
    },
    {
        "tag": "Animals",
        "method": "PATCH",
        "path": "/api/v2/animals/{animal_id}/",
        "title": "Partial animal update",
        "explain": "Identity/housing/notes only. Do not send is_pregnant, is_lactating, is_quarantine, or sold/dead via PATCH — those change through operations (pregnancy_check, mortality, sale). Sold/dead via PATCH is rejected.",
        "auth": "Cookie · update_animal_details",
        "path_params": [("animal_id", "int", "Animal ID")],
        "request": {"notes": "Moved to Pen A", "housing_unit_id": 4, "tag_id": "COW-001"},
        "success": envelope(
            {"id": 15, "tag_id": "COW-001", "overview": {"farm_id": 1, "farm": "North Paddock", "housing_unit_id": 4}},
            "Animal updated successfully.",
        ),
        "error": err("VALIDATION_ERROR", "Sold or dead status must be recorded through operations.", "422"),
    },
    {
        "tag": "Animals",
        "method": "GET",
        "path": "/api/v2/animals/{animal_id}/profile/",
        "title": "Animal operational profile",
        "explain": "Single screen payload: card, overview, reproduction, production, health, feeding, movement, sale_readiness, open_tasks. Keep GET /api/animals/animal-profile/v2/{id} working for old clients; new UI should use this path.",
        "auth": "Cookie · view_animal_details",
        "path_params": [("animal_id", "int", "Animal ID")],
        "success": envelope(
            {
                "id": 15,
                "tag_id": "COW-001",
                "status": "active",
                "health_status": "healthy",
                "flags": {
                    "is_pregnant": False,
                    "is_lactating": False,
                    "is_quarantine": False,
                    "needs_attention": False,
                },
                "card": ANIMAL_CARD,
                "overview": {
                    "species": "Cattle",
                    "livestock_species_id": 1,
                    "breed": "White Fulani",
                    "livestock_breed_id": 2,
                    "housing_unit": "Pen A",
                    "housing_unit_id": 4,
                    "farm_id": 1,
                    "farm": "North Paddock",
                    "mother_tag": None,
                    "source": "Purchased",
                    "entry_date": "2026-01-10",
                },
                "reproduction": {
                    "last_insemination_date": None,
                    "expected_delivery_date": None,
                    "pregnancy_status": "Not Pregnant",
                },
                "production": {"lactation_status": "Not Lactating", "milk_production_today": 0},
                "health": {
                    "health_status": "healthy",
                    "is_quarantine": False,
                    "last_vaccination": {
                        "vaccine_name": "CBPP",
                        "date_given": "2026-08-27",
                        "next_due_date": "2026-09-26",
                    },
                    "last_treatment": None,
                },
                "feeding": {"last_feed_issuance": None},
                "movement": {"last_move_date": None, "from_unit": None, "to_unit": None},
                "sale_readiness": {
                    "status": "not_ready_for_sale",
                    "restrictions": [],
                    "manual_review_reasons": [],
                    "factors": {},
                },
                "open_tasks": [TASK],
            },
            "Animal profile fetched successfully.",
        ),
        "error": err("ANIMAL_NOT_FOUND", "Animal could not be found.", "404"),
    },
    {
        "tag": "Animals",
        "method": "GET",
        "path": "/api/v2/animals/{animal_id}/timeline/",
        "title": "Animal timeline",
        "explain": "Convenience filter of the unified timeline for one animal.",
        "auth": "Cookie · view_animal_details",
        "path_params": [("animal_id", "int", "Animal ID")],
        "query": [("page", "int", "no", "Page"), ("page_size", "int", "no", "Page size")],
        "success": envelope([EVENT], "Timeline fetched successfully.", page_meta(total=1)),
        "error": AUTH_401,
    },
    {
        "tag": "Animals",
        "method": "GET",
        "path": "/api/v2/animals/resolve-tag/{tag_id}/",
        "title": "Resolve ear tag",
        "explain": "Scanner / search jump. Optional farm_id query scopes the lookup. Tags are unique in this backend.",
        "auth": "Cookie · view_animal_details",
        "path_params": [("tag_id", "string", "Ear tag, e.g. COW-001")],
        "query": [("farm_id", "int", "no", "Limit to one farm")],
        "success": envelope(
            {"id": 15, "tag_id": "COW-001", "farm_id": 1, "status": "active", "health_status": "healthy"},
            "Tag resolved successfully.",
        ),
        "error": err("TAG_NOT_FOUND", "No animal found for this tag.", "404"),
    },
    {
        "tag": "Operations",
        "method": "POST",
        "path": "/api/v2/operations/tasks/",
        "title": "Create a task",
        "explain": "task_type: vaccination | treatment | feed_issuance | sale | movement | observation | weight | pregnancy_check | mortality | generic. If assignee_id is set, status becomes assigned and the worker is notified.",
        "auth": "Cookie · create health/feed/animal",
        "request": {
            "farm_id": 1,
            "task_type": "vaccination",
            "title": "Vaccinate COW-001 — CBPP",
            "description": "Annual CBPP shot",
            "animal_id": 15,
            "due_at": "2026-08-28T08:00:00Z",
            "priority": "high",
            "assignee_id": WORKER_ID,
            "client_request_id": "task-create-001",
        },
        "success": envelope(TASK, "Task created successfully."),
        "error": err("VALIDATION_ERROR", "Invalid task type.", "422", {"task_type": "weigh"}),
    },
    {
        "tag": "Operations",
        "method": "GET",
        "path": "/api/v2/operations/tasks/",
        "title": "List tasks",
        "explain": "Manager queue. status=open excludes completed/cancelled. status=overdue is due_at in the past and still open.",
        "auth": "Cookie · view health/feed/animal",
        "query": [
            ("page", "int", "no", "Page"),
            ("page_size", "int", "no", "Page size"),
            ("farm_id", "int", "no", "Filter farm"),
            ("status", "string", "no", "open | overdue | assigned | …"),
            ("task_type", "string", "no", "vaccination, treatment, …"),
            ("assigned_to_me", "bool", "no", "true to hide others’ tasks"),
        ],
        "success": envelope([TASK], "Tasks fetched successfully.", page_meta(total=1)),
        "error": AUTH_401,
    },
    {
        "tag": "Operations",
        "method": "GET",
        "path": "/api/v2/operations/tasks/{task_id}/",
        "title": "Task detail",
        "explain": "Single task. status may render as overdue when due_at is past and the task is still open.",
        "auth": "Cookie",
        "path_params": [("task_id", "int", "Task ID")],
        "success": envelope(TASK, "Task fetched successfully."),
        "error": err("TASK_NOT_FOUND", "Task could not be found.", "404"),
    },
    {
        "tag": "Operations",
        "method": "POST",
        "path": "/api/v2/operations/tasks/{task_id}/assign/",
        "title": "Assign or reassign",
        "explain": "Replaces the current assignee. Previous pending assignment is superseded. Worker gets a notification.",
        "auth": "Cookie · update_farm / owner",
        "path_params": [("task_id", "int", "Task ID")],
        "request": {"assignee_id": WORKER_ID},
        "success": envelope({**TASK, "status": "assigned"}, "Task assigned successfully."),
        "error": err("TASK_INVALID_STATE", "Completed or cancelled tasks cannot be assigned.", "409"),
    },
    {
        "tag": "Operations",
        "method": "POST",
        "path": "/api/v2/operations/tasks/{task_id}/accept/",
        "title": "Accept task",
        "explain": "Only the assignee (or org owner). Empty JSON body is fine. Moves status to accepted.",
        "auth": "Cookie · assignee",
        "path_params": [("task_id", "int", "Task ID")],
        "request": {},
        "success": envelope(
            {**TASK, "status": "accepted", "accepted_at": "2026-08-27T08:05:00+00:00"},
            "Task accepted successfully.",
        ),
        "error": PERM_403,
    },
    {
        "tag": "Operations",
        "method": "POST",
        "path": "/api/v2/operations/tasks/{task_id}/start/",
        "title": "Start task",
        "explain": "Optional. Auto-accepts if still assigned. Sets in_progress. complete() can skip this step.",
        "auth": "Cookie · assignee",
        "path_params": [("task_id", "int", "Task ID")],
        "request": {},
        "success": envelope({**TASK, "status": "in_progress"}, "Task started successfully."),
        "error": err("TASK_INVALID_STATE", "Task cannot be started.", "409"),
    },
    {
        "tag": "Operations",
        "method": "POST",
        "path": "/api/v2/operations/tasks/{task_id}/complete/",
        "title": "Complete task (writes the domain record)",
        "explain": "This is the important call. It runs in one DB transaction: validate → write the domain record → mark task completed → emit timeline. Body fields depend on task_type — see the complete() payload appendix. Weight writes AnimalWeight; pregnancy_check writes PregnancyRecord and sets is_pregnant; mortality writes MortalityRecord, marks the animal dead, and cancels open tasks. If stock is short the task stays incomplete. Send client_request_id (or header X-Client-Request-Id) so a retry does not double-write.",
        "auth": "Cookie · assignee with create permission",
        "path_params": [("task_id", "int", "Task ID")],
        "request": {
            "vaccine_name": "CBPP",
            "date_given": "2026-08-27",
            "next_due_date": "2026-09-26",
            "notes": "Given in paddock",
            "client_request_id": "complete-12",
        },
        "success": envelope(
            {
                **TASK,
                "status": "completed",
                "completed_at": "2026-08-27T09:15:00+00:00",
                "result_reference_table": "vaccination_record",
                "result_reference_id": 41,
            },
            "Task completed successfully.",
        ),
        "error": err(
            "INSUFFICIENT_DRUG_STOCK",
            "Insufficient stock available in the selected drug batch.",
            "409",
        ),
    },
    {
        "tag": "Operations",
        "method": "POST",
        "path": "/api/v2/operations/tasks/{task_id}/cancel/",
        "title": "Cancel task",
        "explain": "Open tasks only. Notifies the assignee.",
        "auth": "Cookie · update_farm / owner",
        "path_params": [("task_id", "int", "Task ID")],
        "request": {"reason": "Animal sold before visit"},
        "success": envelope({**TASK, "status": "cancelled"}, "Task cancelled successfully."),
        "error": err("TASK_INVALID_STATE", "Task cannot be cancelled.", "409"),
    },
    {
        "tag": "Operations",
        "method": "POST",
        "path": "/api/v2/operations/tasks/{task_id}/unable-to-complete/",
        "title": "Unable to complete",
        "explain": "Assignee (or owner) records that the work could not be done. reason_code: animal_unavailable | animal_moved | animal_sick | material_unavailable | medicine_unavailable | equipment_unavailable | incorrect_assignment | unable_to_identify_subject | unsafe_to_proceed | other. Status becomes unable_to_complete. Not the same as cancel.",
        "auth": "Cookie · assignee",
        "path_params": [("task_id", "int", "Task ID")],
        "request": {"reason_code": "animal_unavailable", "notes": "Moved to another paddock", "client_request_id": "unable-12"},
        "success": envelope(
            {**TASK, "status": "unable_to_complete", "unable_reason_code": "animal_unavailable", "unable_to_complete_at": "2026-08-27T11:00:00+00:00"},
            "Unable-to-complete recorded.",
        ),
        "error": err("TASK_ALREADY_COMPLETED", "Completed tasks cannot be marked unable.", "409"),
    },
    {
        "tag": "Operations",
        "method": "POST",
        "path": "/api/v2/operations/tasks/{task_id}/reopen/",
        "title": "Reopen task",
        "explain": "Manager/owner only. Reopens unable_to_complete or cancelled tasks (not completed). Optional new assignee_id and due_at. Status becomes assigned if an assignee is set, otherwise draft.",
        "auth": "Cookie · assign_operation / owner",
        "path_params": [("task_id", "int", "Task ID")],
        "request": {"reason": "Animal returned", "assignee_id": WORKER_ID},
        "success": envelope({**TASK, "status": "assigned", "unable_reason_code": None}, "Task reopened successfully."),
        "error": err("TASK_CANNOT_BE_REOPENED", "Ordinary workers must not reopen completed tasks.", "409"),
    },
    {
        "tag": "Operations",
        "method": "GET",
        "path": "/api/v2/operations/my-work/",
        "title": "My Work inbox",
        "explain": "Open tasks assigned to the current user. Primary field-worker screen.",
        "auth": "Cookie",
        "query": [
            ("page", "int", "no", "Page"),
            ("page_size", "int", "no", "Page size"),
            ("farm_id", "int", "no", "Filter farm"),
        ],
        "success": envelope([TASK], "My work fetched successfully.", page_meta(total=1)),
        "error": AUTH_401,
    },
    {
        "tag": "Operations",
        "method": "GET",
        "path": "/api/v2/operations/today/",
        "title": "Due today",
        "explain": "Assigned to me, due_at date = today, not completed/cancelled.",
        "auth": "Cookie",
        "query": [("page", "int", "no", "Page"), ("page_size", "int", "no", "Page size"), ("farm_id", "int", "no", "Farm")],
        "success": envelope([TASK], "Today's work fetched successfully.", page_meta(total=1)),
        "error": AUTH_401,
    },
    {
        "tag": "Operations",
        "method": "GET",
        "path": "/api/v2/operations/overdue/",
        "title": "Overdue work",
        "explain": "Assigned to me, due_at in the past, still open.",
        "auth": "Cookie",
        "query": [("page", "int", "no", "Page"), ("page_size", "int", "no", "Page size"), ("farm_id", "int", "no", "Farm")],
        "success": envelope([{**TASK, "status": "overdue"}], "Overdue work fetched successfully.", page_meta(total=1)),
        "error": AUTH_401,
    },
    {
        "tag": "Operations",
        "method": "GET",
        "path": "/api/v2/operations/schedules/",
        "title": "List schedules",
        "explain": "Recurring templates. List GET also runs due schedules (process_due_schedules). A cron command `run_due_schedules` does the same on sandbox start.",
        "auth": "Cookie",
        "query": [("page", "int", "no", "Page"), ("page_size", "int", "no", "Page size"), ("farm_id", "int", "no", "Farm")],
        "success": envelope(
            [
                {
                    "id": 1,
                    "farm_id": 1,
                    "task_type": "vaccination",
                    "title": "Monthly CBPP round",
                    "description": "",
                    "recurrence": "monthly",
                    "next_run_at": "2026-09-01T07:00:00+00:00",
                    "is_active": True,
                    "assignee_id": WORKER_ID,
                    "animal_id": None,
                    "group_id": None,
                    "created_at": "2026-08-01T07:00:00+00:00",
                }
            ],
            "Schedules fetched successfully.",
            page_meta(total=1),
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Operations",
        "method": "POST",
        "path": "/api/v2/operations/schedules/",
        "title": "Create schedule",
        "explain": "recurrence: once | daily | weekly | monthly. run_now true immediately creates a task.",
        "auth": "Cookie",
        "request": {
            "farm_id": 1,
            "task_type": "vaccination",
            "title": "Monthly CBPP round",
            "recurrence": "monthly",
            "next_run_at": "2026-09-01T07:00:00Z",
            "assignee_id": WORKER_ID,
            "run_now": False,
        },
        "success": envelope({"id": 1, "title": "Monthly CBPP round", "recurrence": "monthly", "is_active": True}, "Schedule created successfully."),
        "error": err("VALIDATION_ERROR", "Invalid recurrence.", "422"),
    },
    {
        "tag": "Operations",
        "method": "POST",
        "path": "/api/v2/operations/schedules/{schedule_id}/run/",
        "title": "Run schedule",
        "explain": "Creates one task from the template and bumps next_run_at (or deactivates once schedules).",
        "auth": "Cookie",
        "path_params": [("schedule_id", "int", "Schedule ID")],
        "request": {},
        "success": envelope(TASK, "Schedule run successfully."),
        "error": err("SCHEDULE_NOT_FOUND", "Schedule could not be found.", "404"),
    },
    {
        "tag": "Operations",
        "method": "GET",
        "path": "/api/v2/operations/schedules/{schedule_id}/",
        "title": "Schedule detail",
        "explain": "One recurring template.",
        "auth": "Cookie · view_operation",
        "path_params": [("schedule_id", "int", "Schedule ID")],
        "success": envelope(
            {
                "id": 1,
                "farm_id": 1,
                "task_type": "vaccination",
                "title": "Monthly CBPP round",
                "recurrence": "monthly",
                "next_run_at": "2026-09-01T07:00:00+00:00",
                "is_active": True,
            },
            "Schedule fetched successfully.",
        ),
        "error": err("SCHEDULE_NOT_FOUND", "Schedule could not be found.", "404"),
    },
    {
        "tag": "Operations",
        "method": "PATCH",
        "path": "/api/v2/operations/schedules/{schedule_id}/",
        "title": "Update schedule",
        "explain": "Partial update. Send only fields to change, including is_active.",
        "auth": "Cookie · create_operation",
        "path_params": [("schedule_id", "int", "Schedule ID")],
        "request": {"title": "Monthly CBPP round", "next_run_at": "2026-10-01T07:00:00Z"},
        "success": envelope({"id": 1, "title": "Monthly CBPP round", "is_active": True}, "Schedule updated successfully."),
        "error": AUTH_401,
    },
    {
        "tag": "Operations",
        "method": "POST",
        "path": "/api/v2/operations/schedules/{schedule_id}/deactivate/",
        "title": "Deactivate schedule",
        "explain": "Sets is_active false. Does not delete history. Reactivate with PATCH is_active true.",
        "auth": "Cookie · create_operation",
        "path_params": [("schedule_id", "int", "Schedule ID")],
        "request": {},
        "success": envelope({"id": 1, "title": "Monthly CBPP round", "is_active": False}, "Schedule deactivated successfully."),
        "error": err("SCHEDULE_NOT_FOUND", "Schedule could not be found.", "404"),
    },
    {
        "tag": "Timeline",
        "method": "GET",
        "path": "/api/v2/timeline/",
        "title": "Unified timeline",
        "explain": "Do not invent history in the client. Filter with farm_id, animal_id, event_type. Events are written when domain records and tasks save.",
        "auth": "Cookie",
        "query": [
            ("page", "int", "no", "Page"),
            ("page_size", "int", "no", "Page size"),
            ("farm_id", "int", "no", "Farm"),
            ("animal_id", "int", "no", "Animal"),
            ("event_type", "string", "no", "vaccination, treatment, task_completed, …"),
        ],
        "success": envelope([EVENT], "Timeline fetched successfully.", page_meta()),
        "error": AUTH_401,
    },
    {
        "tag": "Health",
        "method": "POST",
        "path": "/api/v2/health/observations/",
        "title": "Record observation",
        "explain": "Thin clinical note. Optional case_id. create_case true opens a HealthCase; default false does not auto-create a case. create_task true opens a follow-up observation task. Treatments still use task complete() or legacy POST /api/health/treatment/.",
        "auth": "Cookie · add_health",
        "request": {
            "farm_id": 1,
            "animal_id": 15,
            "symptoms": "Limping on front left",
            "severity": "mild",
            "create_case": False,
            "create_task": False,
            "client_request_id": "obs-standalone-001",
        },
        "success": envelope(
            {
                "id": 3,
                "farm_id": 1,
                "animal_id": 15,
                "group_id": None,
                "case_id": None,
                "observed_at": "2026-08-27T10:00:00+00:00",
                "symptoms": "Limping on front left",
                "severity": "mild",
                "created_at": "2026-08-27T10:00:00+00:00",
            },
            "Observation recorded successfully.",
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Health",
        "method": "GET",
        "path": "/api/v2/health/observations/",
        "title": "List observations",
        "explain": "Filter by farm_id and animal_id.",
        "auth": "Cookie · view_health",
        "query": [
            ("page", "int", "no", "Page"),
            ("page_size", "int", "no", "Page size"),
            ("farm_id", "int", "no", "Farm"),
            ("animal_id", "int", "no", "Animal"),
        ],
        "success": envelope(
            [
                {
                    "id": 3,
                    "farm_id": 1,
                    "animal_id": 15,
                    "case_id": 1,
                    "observed_at": "2026-08-27T10:00:00+00:00",
                    "symptoms": "Limping on front left",
                    "severity": "mild",
                    "created_at": "2026-08-27T10:00:00+00:00",
                }
            ],
            "Observations fetched successfully.",
            page_meta(total=1),
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Health",
        "method": "POST",
        "path": "/api/v2/health/cases/",
        "title": "Open health case",
        "explain": "Groups observations. Does not replace TreatmentRecord.",
        "auth": "Cookie · add_health",
        "request": {"farm_id": 1, "animal_id": 15, "title": "Lameness", "notes": "Seen at morning check"},
        "success": envelope(
            {
                "id": 1,
                "farm_id": 1,
                "animal_id": 15,
                "group_id": None,
                "title": "Lameness",
                "notes": "Seen at morning check",
                "status": "open",
                "opened_at": "2026-08-27T10:00:00+00:00",
                "closed_at": None,
            },
            "Health case opened successfully.",
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Health",
        "method": "GET",
        "path": "/api/v2/health/cases/",
        "title": "List health cases",
        "explain": "Default status=open.",
        "auth": "Cookie · view_health",
        "query": [
            ("page", "int", "no", "Page"),
            ("page_size", "int", "no", "Page size"),
            ("farm_id", "int", "no", "Farm"),
            ("status", "string", "no", "open | closed"),
        ],
        "success": envelope(
            [{"id": 1, "farm_id": 1, "animal_id": 15, "title": "Lameness", "status": "open", "opened_at": "2026-08-27T10:00:00+00:00", "closed_at": None}],
            "Health cases fetched successfully.",
            page_meta(total=1),
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Health",
        "method": "GET",
        "path": "/api/v2/health/cases/{case_id}/",
        "title": "Health case detail",
        "explain": "Case plus observations, treatments, follow_up, and open_tasks. Does not rewrite the Health engine.",
        "auth": "Cookie · view_health",
        "path_params": [("case_id", "int", "Case ID")],
        "success": envelope(
            {
                "id": 1,
                "farm_id": 1,
                "animal_id": 15,
                "title": "Lameness",
                "status": "open",
                "animal": {"id": 15, "tag_id": "COW-001"},
                "observations": [{"id": 3, "symptoms": "Limping on front left", "severity": "mild"}],
                "diagnosis": None,
                "treatments": [],
                "follow_up": {"required": False, "next_due_at": None},
                "open_tasks": [],
            },
            "Health case fetched successfully.",
        ),
        "error": err("HEALTH_CASE_NOT_FOUND", "Health case could not be found.", "404"),
    },
    {
        "tag": "Health",
        "method": "POST",
        "path": "/api/v2/health/cases/{case_id}/close/",
        "title": "Close health case",
        "explain": "Sets status closed. Optional notes are appended.",
        "auth": "Cookie · update_health",
        "path_params": [("case_id", "int", "Case ID")],
        "request": {"notes": "Resolved after treatment"},
        "success": envelope(
            {"id": 1, "title": "Lameness", "status": "closed", "closed_at": "2026-08-28T16:00:00+00:00"},
            "Health case closed successfully.",
        ),
        "error": err("CONFLICT", "Health case is already closed.", "409"),
    },
    {
        "tag": "Health",
        "method": "GET",
        "path": "/api/v2/health/alerts/",
        "title": "Actionable health alerts",
        "explain": "HealthAlert rows with subject (animal/farm) and reference. Distinct from farm attention alerts at /farms/{id}/alerts/ and from the notification inbox.",
        "auth": "Cookie · view_health",
        "query": [
            ("page", "int", "no", "Page"),
            ("page_size", "int", "no", "Page size"),
            ("farm_id", "int", "no", "Farm"),
            ("status", "string", "no", "open (default) or resolved"),
        ],
        "success": envelope(
            [
                {
                    "id": 9,
                    "alert_type": "vaccination_due",
                    "priority": "warning",
                    "title": "Vaccination Due",
                    "message": "COW-001 CBPP due",
                    "status": "open",
                    "subject": SUBJECT,
                    "reference": {"type": "health_alert", "id": 9},
                    "available_actions": ["view_subject", "create_task"],
                    "detected_date": "2026-08-20",
                }
            ],
            "Alerts fetched successfully.",
            page_meta(total=1),
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Notifications",
        "method": "GET",
        "path": "/api/v2/notifications/unread-count/",
        "title": "Unread badge count",
        "explain": "Lightweight badge. Prefer this over paging the inbox just to count unread.",
        "auth": "Cookie",
        "success": envelope({"count": 4}, "Unread notification count fetched successfully."),
        "error": AUTH_401,
    },
    {
        "tag": "Notifications",
        "method": "GET",
        "path": "/api/v2/notifications/",
        "title": "Notification inbox",
        "explain": "Per-user inbox (task assigned, completed, cancelled). Not the same as farm alerts.",
        "auth": "Cookie",
        "query": [
            ("page", "int", "no", "Page"),
            ("page_size", "int", "no", "Page size"),
            ("unread_only", "bool", "no", "true for badge list"),
        ],
        "success": envelope(
            [
                {
                    "id": 21,
                    "category": "task",
                    "title": "Task assigned",
                    "body": "Vaccinate COW-001 — CBPP",
                    "is_read": False,
                    "read_at": None,
                    "farm_id": 1,
                    "reference_table": "task",
                    "reference_id": 12,
                    "created_at": "2026-08-27T07:00:00+00:00",
                }
            ],
            "Notifications fetched successfully.",
            page_meta(total=1),
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Notifications",
        "method": "POST",
        "path": "/api/v2/notifications/{notification_id}/read/",
        "title": "Mark one read",
        "explain": "Idempotent if already read.",
        "auth": "Cookie",
        "path_params": [("notification_id", "int", "Notification ID")],
        "request": {},
        "success": envelope(
            {"id": 21, "is_read": True, "read_at": "2026-08-27T07:10:00+00:00", "title": "Task assigned"},
            "Notification marked as read.",
        ),
        "error": err("NOTIFICATION_NOT_FOUND", "Notification could not be found.", "404"),
    },
    {
        "tag": "Notifications",
        "method": "POST",
        "path": "/api/v2/notifications/read-all/",
        "title": "Mark all read",
        "explain": "Clears the badge. Body optional.",
        "auth": "Cookie",
        "request": {},
        "success": envelope({"updated": 4}, "Notifications marked as read."),
        "error": AUTH_401,
    },
    {
        "tag": "Search",
        "method": "GET",
        "path": "/api/v2/search/",
        "title": "Search",
        "explain": "q is required. Returns animals (tag + farm + species), people (display_name), and tasks (subject + assignee). Each bucket is omitted unless the caller has that capability. limit default 10, max 25.",
        "auth": "Cookie",
        "query": [
            ("q", "string", "yes", "Search text"),
            ("farm_id", "int", "no", "Scope to farm"),
            ("limit", "int", "no", "Max hits per bucket"),
        ],
        "success": envelope(
            {
                "query": "COW-001",
                "animals": [
                    {
                        "id": 15,
                        "tag_id": "COW-001",
                        "species": "Cattle",
                        "breed": "White Fulani",
                        "farm": "North Paddock",
                        "farm_id": 1,
                        "status": "active",
                    }
                ],
                "people": [{"id": WORKER_ID, "display_name": "Ibrahim Musa", "email": "ibrahim@farm.example", "role": None, "farm": None}],
                "tasks": [{"id": 12, "title": "Vaccinate COW-001 — CBPP", "status": "assigned", "subject": SUBJECT, "assignee": "Ibrahim Musa"}],
            },
            "Search completed.",
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Dashboard",
        "method": "GET",
        "path": "/api/v2/dashboard/organization/",
        "title": "Organization home",
        "explain": "One call for org home. Timezone Africa/Lagos. livestock / operations / attention / upcoming / farm_breakdown / recent_activity. Do not fan out the 29 legacy dashboard routes for this screen.",
        "auth": "Cookie",
        "success": envelope(
            {
                "organization": {"id": ORG_ID, "name": "Zaima Farms", "status": "active", "timezone": "Africa/Lagos"},
                "livestock": {"total": 120, "active": 110, "sold": 6, "dead": 4},
                "operations": {"scheduled_today": 6, "completed_today": 2, "in_progress": 1, "overdue": 1},
                "attention": {"critical_health": 8, "feed_risk": 0, "quarantine": 2, "overdue_operations": 1},
                "upcoming": {"vaccinations_7_days": 3, "followups_7_days": 1, "expected_births_14_days": 2},
                "farm_breakdown": [
                    {
                        "farm_id": 1,
                        "name": "North Paddock",
                        "active_animals": 110,
                        "open_alerts": 3,
                        "overdue_tasks": 1,
                        "work_completion_percent": 80,
                    }
                ],
                "recent_activity": [EVENT],
            },
            "Organization dashboard fetched successfully.",
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Dashboard",
        "method": "GET",
        "path": "/api/v2/dashboard/farm/{farm_id}/",
        "title": "Farm home",
        "explain": "Role-aware farm aggregate. timezone Africa/Lagos. today bucket is scheduled/completed/in_progress/pending/overdue.",
        "auth": "Cookie · farm access",
        "path_params": [("farm_id", "int", "Farm ID")],
        "success": envelope(
            {
                "farm": {"id": 1, "name": "North Paddock", "status": "active", "timezone": "Africa/Lagos"},
                "livestock": {"total": 120, "active": 110, "sold": 6, "dead": 4, "quarantine": 2},
                "today": {"scheduled": 6, "completed": 2, "in_progress": 1, "pending": 3, "overdue": 1},
                "attention": [{"type": "alert", "id": 9, "title": "vaccination_due", "animal_id": 15}],
                "upcoming": [TASK],
                "team_work": [
                    {
                        "user_id": WORKER_ID,
                        "display_name": "Ibrahim Musa",
                        "assigned_today": 2,
                        "completed_today": 1,
                        "overdue": 0,
                    }
                ],
                "recent_activity": [EVENT],
            },
            "Farm dashboard fetched successfully.",
        ),
        "error": NOT_FOUND,
    },
    {
        "tag": "Dashboard",
        "method": "GET",
        "path": "/api/v2/dashboard/my-work/",
        "title": "My Work dashboard",
        "explain": "Buckets: today, overdue, upcoming. Optional farm_id.",
        "auth": "Cookie",
        "query": [("farm_id", "int", "no", "Filter farm")],
        "success": envelope(
            {
                "summary": {"open_tasks": 2, "overdue_tasks": 1, "completed_today": 1},
                "today": [TASK],
                "overdue": [],
                "upcoming": [],
            },
            "My work dashboard fetched successfully.",
        ),
        "error": AUTH_401,
    },
    {
        "tag": "Dashboard",
        "method": "GET",
        "path": "/api/v2/dashboard/health/",
        "title": "Health workspace",
        "explain": "Veterinarian home: active cases, due treatments/vaccinations, quarantine, mortality count, and my_tasks. Optional farm_id.",
        "auth": "Cookie · view_health",
        "query": [("farm_id", "int", "no", "Scope to one farm")],
        "success": envelope(
            {
                "active_health_cases": 4,
                "critical_cases": 1,
                "new_observations": 2,
                "treatments_due": 3,
                "followups_due": 1,
                "vaccinations_due": 5,
                "quarantined_animals": 2,
                "mortality_cases": 1,
                "withdrawal_animals": 2,
                "my_tasks": [TASK],
            },
            "Health dashboard fetched successfully.",
        ),
        "error": AUTH_401,
    },
]


def escape(text) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def dumps(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=True)


def build_html() -> str:
    tags = []
    for ep in ENDPOINTS:
        if ep["tag"] not in tags:
            tags.append(ep["tag"])

    parts = [f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>FarmOS Frontend API Contract v2.1</title>
<style>
  :root {{
    --primary: {PRIMARY};
    --primary-dark: {PRIMARY_DARK};
    --ink: {INK};
    --muted: {MUTED};
    --mint: {MINT};
    --line: {LINE};
    --page: {PAGE_BG};
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: Inter, "Helvetica Neue", Helvetica, Arial, sans-serif;
    color: var(--ink); margin: 0; background: #fff; line-height: 1.5; font-size: 13px;
  }}
  .page {{ max-width: 920px; margin: 0 auto; padding: 28px 28px 72px; }}
  .cover {{
    background: linear-gradient(180deg, var(--mint) 0%, #fff 70%);
    border: 1px solid var(--line); border-radius: 20px; padding: 36px 32px 28px; margin-bottom: 28px;
  }}
  .brand {{ color: var(--primary); font-weight: 700; letter-spacing: .04em; font-size: 12px; text-transform: uppercase; }}
  h1 {{ font-size: 28px; margin: 8px 0 10px; color: var(--ink); }}
  h1 span {{ color: var(--primary); }}
  h2 {{ font-size: 18px; color: var(--primary-dark); margin: 36px 0 10px; page-break-before: always; border-bottom: 2px solid var(--mint); padding-bottom: 6px; }}
  h2:nth-of-type(1), h2:nth-of-type(2) {{ page-break-before: auto; }}
  h3 {{ font-size: 14px; margin: 0; }}
  p {{ margin: 0 0 10px; }}
  .muted {{ color: var(--muted); }}
  .endpoint {{
    border: 1px solid var(--line); border-radius: 16px; margin: 14px 0 22px;
    page-break-inside: avoid; overflow: hidden;
  }}
  .endpoint-hd {{ padding: 12px 14px; background: var(--mint); border-bottom: 1px solid var(--line); }}
  .endpoint-bd {{ padding: 14px; }}
  .method {{
    display: inline-block; font-weight: 700; font-size: 10px; letter-spacing: .06em;
    padding: 3px 8px; border-radius: 999px; margin-right: 8px; color: #fff;
  }}
  .GET {{ background: var(--primary); }}
  .POST {{ background: #1D4ED8; }}
  .PATCH {{ background: #B45309; }}
  .DELETE {{ background: #B91C1C; }}
  code, pre {{ font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 11px; }}
  .path {{ font-weight: 650; color: var(--ink); }}
  table {{ width: 100%; border-collapse: collapse; margin: 8px 0 12px; font-size: 12px; }}
  th, td {{ border: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }}
  th {{ background: var(--page); }}
  pre {{
    background: {INK}; color: #ECFDF5; padding: 12px; border-radius: 12px;
    overflow-x: auto; white-space: pre-wrap; word-break: break-word;
    border-left: 4px solid var(--primary);
  }}
  .label {{
    font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
    color: var(--primary-dark); margin: 12px 0 6px;
  }}
  .pill {{
    display: inline-block; background: var(--mint); color: var(--primary-dark);
    padding: 2px 8px; border-radius: 99px; font-size: 11px; margin-right: 6px; font-weight: 600;
  }}
  .toc a {{ color: var(--primary-dark); text-decoration: none; }}
  .toc li {{ margin: 4px 0; }}
  .note {{ background: var(--mint); border-radius: 12px; padding: 12px 14px; margin: 12px 0; }}
  @media print {{
    .endpoint {{ page-break-inside: avoid; }}
    a {{ color: inherit; text-decoration: none; }}
  }}
</style>
</head>
<body>
<div class="page">
<div class="cover">
  <div class="brand">TATI FarmOS · Livestock</div>
  <h1>Building the frontend for <span>African Agriculture</span></h1>
  <p class="muted">Official Web/Mobile contract v2.1 · sandbox <code>http://127.0.0.1:8082/api/v2/</code> · Swagger <code>/api/v2/docs</code></p>
  <p>v2.1 completes v2.0 — it does not rewrite it. Every route below is what new screens should call. Brand primary from tatifarmos.com: <code>{PRIMARY}</code>.</p>
</div>
"""]

    parts.append("<h2 id='howto'>How frontend should call this API</h2>")
    parts.append(f"""
<div class="note">
<p><span class="pill">Base</span> Nginx sandbox <code>http://127.0.0.1:8082</code> · direct app <code>http://127.0.0.1:8001</code>. Live stack is unchanged on 8081/8000.</p>
<p><span class="pill">Prefix</span> Official contract is <code>/api/v2/</code> version <strong>2.1</strong>. Legacy <code>/api/*</code> (240 routes) stays for existing clients. Do not mix envelopes. GET <code>/api/v2/registry/</code> lists v2 vs approved-legacy vs deprecated.</p>
<p><span class="pill">Auth</span> <code>POST /api/auth/login</code> sets <code>client_access_token</code> (HTTP-only). Send cookies on v2 requests. Unauthenticated v2 calls return <code>AUTHENTICATION_REQUIRED</code>.</p>
<p><span class="pill">IDs</span> Use <code>livestock_species_id</code>, <code>livestock_breed_id</code>, <code>housing_unit_id</code>, integer <code>farm_id</code> / <code>animal_id</code>, UUID <code>organization_id</code> / user ids. People screens use <code>display_name</code>. Tasks and timeline include <code>actor</code>, <code>subject</code>, <code>source</code>, <code>result</code>.</p>
<p><span class="pill">Idempotency</span> On writes send <code>client_request_id</code> in JSON or header <code>X-Client-Request-Id</code>. Same key + same user returns the first JSON body and must not create a second vaccination/feed/sale.</p>
<p><span class="pill">Timezone</span> Dashboard clocks use <code>Africa/Lagos</code>.</p>
</div>
<div class="label">What’s new in 2.1</div>
<p>Animal list + PATCH, optional untagged create (<code>INT-…</code>), statuses <code>transferred_out</code> / <code>culled</code>, people/roles/permissions GETs, unable-to-complete + reopen, schedule GET/PATCH/deactivate + due-schedule runner, observation <code>create_case</code>, case detail, health alerts, health dashboard, unread-count, weight / pregnancy_check / mortality complete handlers. Reproduction, feed, finance, reports, movement, and master data stay on approved legacy <code>/api/*</code>.</p>
<div class="label">Success envelope (every v2 200)</div>
<pre>{escape(dumps({
    "success": True,
    "code": "REQUEST_SUCCESSFUL",
    "message": "Human-readable summary",
    "data": {},
    "meta": None,
}))}</pre>
<div class="label">List envelope — read meta.pagination (never current_page / num_pages)</div>
<pre>{escape(dumps(envelope([{"id": 1}], "Fetched successfully.", page_meta(total=42))))}</pre>
<div class="label">Error envelope (v2)</div>
<pre>{escape(dumps({
    "success": False,
    "code": "AUTHENTICATION_REQUIRED",
    "message": "Authentication is required.",
    "data": None,
    "errors": {},
    "retryable": False,
}))}</pre>
<p class="muted">Login errors are the old shape <code>{{"status":"Error","message":"Invalid credentials"}}</code> — only on <code>/api/auth/login</code>.</p>
<h3>Frontend screen map</h3>
<table>
<tr><th>Screen</th><th>Call these</th></tr>
<tr><td>App shell / nav</td><td><code>GET /users/me/</code> then <code>GET /users/me/capabilities/</code></td></tr>
<tr><td>Org home</td><td><code>GET /dashboard/organization/</code> and <code>GET /organizations/{{id}}/summary/</code></td></tr>
<tr><td>Farm home</td><td><code>GET /dashboard/farm/{{id}}/</code>, overview, people, units, alerts</td></tr>
<tr><td>Herd list</td><td><code>GET /animals/</code> with filters; PATCH for identity/housing only</td></tr>
<tr><td>Animal page</td><td><code>GET /animals/{{id}}/profile/</code> + <code>/timeline/</code></td></tr>
<tr><td>Scanner</td><td><code>GET /animals/resolve-tag/{{tag}}/</code> or <code>GET /search/?q=</code></td></tr>
<tr><td>My Work</td><td><code>GET /operations/my-work/</code>, today, overdue; accept / start / complete / unable-to-complete</td></tr>
<tr><td>Ops manager</td><td><code>POST /operations/tasks/</code>, assign, reopen, schedules, <code>GET /registry/</code></td></tr>
<tr><td>People</td><td><code>GET /users/</code>, <code>/roles/</code>, <code>/permissions/</code> — invite stays <code>POST /api/admin/invite/</code></td></tr>
<tr><td>Health workspace</td><td><code>GET /dashboard/health/</code>, cases, observations (<code>create_case</code>), <code>/health/alerts/</code></td></tr>
<tr><td>Inbox</td><td><code>GET /notifications/unread-count/</code> then <code>GET /notifications/</code> — not farm alerts</td></tr>
</table>
<h3>Ibrahim vaccination flow</h3>
<ol>
<li>Owner <code>POST /operations/tasks/</code> with <code>task_type: vaccination</code> and Ibrahim’s <code>assignee_id</code>.</li>
<li>Ibrahim <code>GET /operations/my-work/</code> — task is in <code>data[]</code>.</li>
<li><code>POST .../accept/</code> then optional <code>.../start/</code>.</li>
<li><code>POST .../complete/</code> with <code>vaccine_name</code> + <code>date_given</code> (+ <code>client_request_id</code>).</li>
<li>Backend writes the existing <code>VaccinationRecord</code>, emits timeline events, creates a follow-up task if <code>next_due_date</code> is set, and the task leaves My Work.</li>
<li>Retry the same complete with the same <code>client_request_id</code> — still one vaccination row.</li>
</ol>
<h3>complete() JSON by task_type</h3>
<table>
<tr><th>task_type</th><th>Required JSON fields</th><th>Writes</th></tr>
<tr><td><code>vaccination</code></td><td><code>vaccine_name</code>, optional <code>date_given</code>, <code>next_due_date</code>, <code>notes</code></td><td>VaccinationRecord + follow-up task</td></tr>
<tr><td><code>treatment</code></td><td><code>diagnosis</code>, <code>treatment</code>, <code>severity</code>; optional drug_batch + quantity</td><td>TreatmentRecord (deducts drug stock)</td></tr>
<tr><td><code>feed_issuance</code></td><td><code>feed_inventory_id</code>, <code>quantity_issued</code>, <code>target_type</code></td><td>FeedIssuanceRecord (deducts feed)</td></tr>
<tr><td><code>sale</code></td><td><code>buyer_name</code>, <code>price</code>; <code>override_reason</code> if restricted</td><td>SalesRecord (sale_readiness rules)</td></tr>
<tr><td><code>movement</code></td><td><code>to_housing_unit_id</code> or <code>to_unit_id</code></td><td>MovementRecord</td></tr>
<tr><td><code>observation</code></td><td><code>symptoms</code></td><td>HealthObservation</td></tr>
<tr><td><code>weight</code></td><td><code>weight</code>, optional <code>unit</code>, <code>measured_at</code></td><td>AnimalWeight (one per animal per day)</td></tr>
<tr><td><code>pregnancy_check</code></td><td><code>result</code> (pregnant | not_pregnant); <code>expected_delivery_date</code> if pregnant</td><td>PregnancyRecord + <code>is_pregnant</code></td></tr>
<tr><td><code>mortality</code></td><td>optional <code>cause</code>, <code>died_at</code></td><td>MortalityRecord + mark_dead + cancel open tasks</td></tr>
<tr><td><code>generic</code></td><td>none</td><td>Task only + timeline</td></tr>
</table>
<p class="muted">Useful error codes: <code>TASK_ASSIGNMENT_REQUIRED</code>, <code>TASK_ALREADY_COMPLETED</code>, <code>INSUFFICIENT_FEED_STOCK</code>, <code>INSUFFICIENT_DRUG_STOCK</code>, <code>INVALID_ANIMAL_STATE</code> (sale blocked), <code>SESSION_EXPIRED</code>.</p>
""")

    parts.append("<h2 id='toc'>Endpoints</h2><ol class='toc'>")
    for tag in tags:
        n = sum(1 for e in ENDPOINTS if e["tag"] == tag)
        slug = tag.lower().replace(" ", "-").replace("(", "").replace(")", "")
        parts.append(f"<li><a href='#{slug}'>{escape(tag)}</a> ({n})</li>")
    parts.append("</ol>")

    current = None
    for ep in ENDPOINTS:
        if ep["tag"] != current:
            current = ep["tag"]
            slug = current.lower().replace(" ", "-").replace("(", "").replace(")", "")
            parts.append(f"<h2 id='{slug}'>{escape(current)}</h2>")
        parts.append('<div class="endpoint">')
        parts.append('<div class="endpoint-hd">')
        parts.append(
            f'<span class="method {ep["method"]}">{ep["method"]}</span>'
            f'<span class="path">{escape(ep["path"])}</span>'
        )
        parts.append(f"<h3 style='margin-top:8px'>{escape(ep['title'])}</h3>")
        parts.append("</div><div class='endpoint-bd'>")
        parts.append(f"<p>{escape(ep['explain'])}</p>")
        parts.append(f"<p><span class='pill'>Auth</span> {escape(ep['auth'])}</p>")
        if ep.get("path_params"):
            parts.append("<div class='label'>URL parameters</div><table>")
            parts.append("<tr><th>Name</th><th>Type</th><th>What to send</th></tr>")
            for name, typ, help_ in ep["path_params"]:
                parts.append(
                    f"<tr><td><code>{escape(name)}</code></td><td>{escape(typ)}</td><td>{escape(help_)}</td></tr>"
                )
            parts.append("</table>")
        if ep.get("query"):
            parts.append("<div class='label'>Query parameters</div><table>")
            parts.append("<tr><th>Name</th><th>Type</th><th>Required</th><th>What to send</th></tr>")
            for name, typ, req, help_ in ep["query"]:
                parts.append(
                    "<tr>"
                    f"<td><code>{escape(name)}</code></td><td>{escape(typ)}</td>"
                    f"<td>{escape(req)}</td><td>{escape(help_)}</td></tr>"
                )
            parts.append("</table>")
        if "request" in ep:
            parts.append("<div class='label'>Example request JSON</div>")
            parts.append(f"<pre>{escape(dumps(ep['request']))}</pre>")
        else:
            parts.append("<p class='muted'>No JSON body. Input is the URL and query string.</p>")
        success = ep["success"]
        parts.append("<div class='label'>Example success JSON</div>")
        parts.append(f"<pre>{escape(dumps(success))}</pre>")
        raw_err = ep["error"]
        note = ep.get("error_http")
        if isinstance(raw_err, dict):
            note = note or raw_err.get("_http")
            err_body = {k: v for k, v in raw_err.items() if k != "_http"}
        else:
            err_body = raw_err
        parts.append("<div class='label'>Example error JSON" + (f" · HTTP {escape(note)}" if note else "") + "</div>")
        parts.append(f"<pre>{escape(dumps(err_body))}</pre>")
        parts.append("</div></div>")

    parts.append(
        f"<p class='muted'>TATI FarmOS Frontend API Contract v2.1 · primary {PRIMARY} · "
        "do not parse legacy list keys (<code>current_page</code>, <code>num_pages</code>) on these routes. "
        "Evidence uploads, bootstrap, retag history, and birth/offspring integrity enforcement are deferred.</p>"
        "</div></body></html>"
    )
    return "".join(parts)


def html_to_pdf(html_path: Path, pdf_path: Path) -> None:
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
        subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                f"--print-to-pdf={pdf_path}",
                "--no-pdf-header-footer",
                html_path.as_uri(),
            ],
            check=True,
        )
        return
    try:
        from weasyprint import HTML

        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        return
    except Exception:
        pass
    raise SystemExit(f"HTML ready at {html_path} but no Chrome/WeasyPrint for PDF.")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html = build_html()
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {HTML_PATH}")
    html_to_pdf(HTML_PATH, PDF_PATH)
    print(f"Wrote {PDF_PATH}")
    shutil.copyfile(HTML_PATH, HTML_ALIAS)
    shutil.copyfile(PDF_PATH, PDF_ALIAS)
    print(f"Updated {PDF_ALIAS}")


if __name__ == "__main__":
    main()
