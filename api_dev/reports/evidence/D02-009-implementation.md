# D02-009 Manager Operations Dashboard

## Implementation

- Added `GET /api/v2/operations/dashboard/` as a read-only, server-authoritative operational aggregate.
- Reuses authorized organization/farm task scope; non-management Operations users receive only their personal assigned population.
- Implements locked KPI math: completed, actionable, Due Today, overdue, completion percentage, and team progress.
- Uses one evaluation timestamp and `Africa/Lagos` day boundary; Due Today and overdue are non-overlapping.
- No new task states, persisted KPI records, events, or mutations were introduced.

## Authorization and error contract

- Requires `view_operation`; `farm_id` is validated through the existing farm authorization service and returns the canonical farm-access error when unauthorized.
- Response uses the standard v2 envelope and exposes evaluation time, timezone, and scope metadata.

## Verification

- Focused KPI/farm-scope regression passed.
- Complete development suite executed: **59 tests**.
- Frontend Integration Guide updated and regenerated with the dashboard API,
  KPI definitions, Lagos reporting boundary, scope, and read-only behavior.

## Status

**IMPLEMENTATION, API CONTRACT, AUTHORIZATION, TESTS, EVIDENCE, AND FRONTEND
GUIDE UPDATED — READY FOR LOCK REVIEW.**

## Requirement-to-test/evidence matrix

| Requirement | Implementation location | Endpoint/service | Automated test | Result | Evidence |
|---|---|---|---|---|---|
| Server-authoritative, read-only aggregate; no KPI persistence or mutation | `contract/ops.py:operations_dashboard` | `GET /api/v2/operations/dashboard/` | `test_operations_dashboard_uses_locked_progress_math_and_farm_scope`; complete suite | Passed | This file; `WORK-TRACE.md` |
| Authorized organization/farm scope; `farm_id` narrows only | `contract/ops.py:operations_dashboard`, `contract/authz.py:require_farm` | Dashboard aggregate | Focused dashboard scope test | Passed: unauthorized Farm B returns 403 | This file |
| Personal scope for non-management Operations users | `contract/ops.py:operations_dashboard` | Dashboard aggregate | `test_operations_dashboard_uses_locked_progress_math_and_farm_scope`; complete suite | Passed: a field worker receives only their assigned KPI population and `personal_scope: true` | This file |
| Completed/actionable/team-progress math and zero-safe percentage | `contract/ops.py:operations_dashboard` | Dashboard aggregate | Focused dashboard KPI test | Passed: `total = completed + actionable`; percentages agree | This file |
| Due Today/Overdue non-overlap and executable lifecycle semantics | `contract/ops.py:operations_dashboard` | Dashboard aggregate | Focused dashboard KPI test | Passed: assigned work is counted; completed, cancelled, and draft work are excluded | This file |
| One Lagos evaluation time and response freshness metadata | `contract/ops.py:operations_dashboard` | Dashboard aggregate | Focused dashboard KPI test; complete suite | Passed: asserts `Africa/Lagos` and `evaluation_time` metadata | This file |
| OpenAPI standard envelope / frontend contract | Ninja route registration in `contract/ops.py` | `/api/v2/operations/dashboard/` | `test_openapi_references_resolve`; complete suite | Passed | Frontend Integration Guide; this file |
