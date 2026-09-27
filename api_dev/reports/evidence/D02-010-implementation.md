# D02-010 — Farm / Subject / Data Isolation

Date: 2026-09-25  
Scope: `api_dev/` only

## Locked decisions implemented

- Direct objects outside the caller's authorized Organization/Farm scope are
  concealed as `404` with the relevant `*_NOT_FOUND` contract code. The
  capability-denied `403 PERMISSION_DENIED` response remains for an object in
  the caller's visible Farm scope when the requested action is not allowed.
- Web and mobile Operations task and schedule detail/mutation paths resolve
  Farm scope before evaluating the requested capability. Lists, dashboards,
  reports, timelines, and subject lookups remain authorization-scoped before
  client filters are applied.
- `GET /mobile/api/sync-scope/` returns the authenticated user's authoritative
  `authorized_farm_ids` plus `remove_revoked_farm_operational_data`. A client
  must apply that directive on successful synchronization. Mobile queued
  mutations continue to revalidate live account/session, channel, Farm,
  capability, task relationship, lifecycle, and typed-domain state.
- Farm deactivation uses the established Domain 01 `status` lifecycle and
  retains all D02 history. `Farm.delete()` now raises `ProtectedError` when
  Tasks, Schedules, or canonical Events exist; empty Farms retain the Domain
  01 deletion behavior.
- Historical Tasks retain their own `farm_id` when an Animal changes Farm.
  Access to the historical record continues to be authorized by that original
  Farm scope. The legacy transfer destination lookup is now scoped to the
  caller's Organization and authorized Farms.

## Requirement-to-test matrix

The requirement matrix below maps each required rule to its implementation,
public endpoint or model/service path, automated regression, observed result,
and evidence source. File line numbers refer to the checked-in development
backend at the time this evidence was prepared.

| Requirement | Implementation Location | Endpoint/Service | Automated Test | Result | Evidence |
|---|---|---|---|---|---|
| Cross-Farm direct object enumeration is concealed as 404 | `contract/authz.py::require_farm`; `contract/ops.py::task_cancel` | `POST /api/v2/operations/tasks/{task_id}/cancel/` | `common.tests.Domain01Tests.test_d020_direct_object_concealment_and_visible_capability_denial` | **PASS (previous development-container run):** Farm A-only manager targeting Farm B task receives `404 FARM_NOT_FOUND`. Fresh rerun unavailable in this shell. | Regression assertions at `common/tests.py:992-1000`; prior verification recorded below. |
| Capability denial within visible Farm remains 403 | `contract/ops.py::task_cancel`; `contract/authz.py::require_permission` | `POST /api/v2/operations/tasks/{task_id}/cancel/` | `common.tests.Domain01Tests.test_d020_direct_object_concealment_and_visible_capability_denial` | **PASS (previous development-container run):** visible Farm A task without `cancel_operation` receives `403 PERMISSION_DENIED`. Fresh rerun unavailable in this shell. | Regression assertions at `common/tests.py:1001-1007`; prior verification recorded below. |
| Revoked mobile Farm scope is returned authoritatively; queued writes are reauthorized | `contract/mobile.py::sync_scope`, `MobileSyncJWT`, mobile task mutation handlers; live channel/session checks | `GET /mobile/api/sync-scope/`; queued `POST /mobile/api/tasks/{task_id}/unable-to-complete/` | `common.tests.Domain01Tests.test_d020_mobile_revocation_rejects_queued_write_and_hides_work` | **PASS (previous development-container run):** sync scope has no authorized farms and returns `remove_revoked_farm_operational_data`; queued mutation returns `403 CHANNEL_ACCESS_DENIED`, work is denied, task stays assigned. Fresh rerun unavailable in this shell. | Regression assertions at `common/tests.py:1009-1029`; endpoint at `contract/mobile.py:93-107`. |
| Farm deactivation preserves authoritative history | `contract/farms.py::patch_farm`; Farm status field | `PATCH /api/v2/farms/{farm_id}/` | `common.tests.Domain01Tests.test_d020_farm_deactivation_preserves_history_and_blocks_destructive_delete` | **PASS (previous development-container run):** status becomes inactive and completed task remains linked to original Farm. Fresh rerun unavailable in this shell. | Regression assertions at `common/tests.py:1031-1042`. |
| Destructive Farm deletion is blocked when Tasks, Schedules, or Events exist | `organization/models.py::Farm.delete`; `organization/signals.py::prevent_farm_history_deletion` | Django instance and queryset deletion paths | `common.tests.Domain01Tests.test_d020_farm_deactivation_preserves_history_and_blocks_destructive_delete` | **PASS (previous development-container run):** both deletion paths raise `ProtectedError`; Farm remains. Fresh rerun unavailable in this shell. | Regression assertions at `common/tests.py:1043-1047`; guards at `organization/models.py:78-98` and `organization/signals.py:10-26`. |
| Inter-Farm transfer retains historical task Farm attribution and authorization scope | Task stores its own Farm FK; `contract/ops.py::task_detail`; `common/access.py::authorized_farms` | Animal Farm reassignment; `GET /api/v2/operations/tasks/{task_id}/` | `common.tests.Domain01Tests.test_d020_transfer_retains_historical_farm_scope` | **PASS (previous development-container run):** Animal moves to Farm B while prior Task remains on Farm A. Fresh rerun unavailable in this shell. | Regression assertions at `common/tests.py:1049-1057`. |
| Farm-B-only access does not reveal Farm-A historical Task | `contract/ops.py::task_detail`; `contract/authz.py::require_farm` | `GET /api/v2/operations/tasks/{task_id}/` | `common.tests.Domain01Tests.test_d020_transfer_retains_historical_farm_scope` | **PASS (previous development-container run):** manager assigned only to Farm B receives `404`. Fresh rerun unavailable in this shell. | Regression assertions at `common/tests.py:1058-1061`. |
| Dual-Farm access can read the historical Task under original Farm A scope | `contract/ops.py::task_detail`; `contract/authz.py::require_farm` | `GET /api/v2/operations/tasks/{task_id}/` | `common.tests.Domain01Tests.test_d020_transfer_retains_historical_farm_scope` | **PASS (previous development-container run):** after restoring Farm A assignment alongside Farm B, manager receives `200`. Fresh rerun unavailable in this shell. | Regression assertions at `common/tests.py:1062-1064`. |
| Organization-wide owner authority can read historical Task | `contract/authz.py::is_organization_owner`, `require_farm`; `contract/ops.py::task_detail` | `GET /api/v2/operations/tasks/{task_id}/` | `common.tests.Domain01Tests.test_d020_transfer_retains_historical_farm_scope` | **PASS (previous development-container run):** Organization owner receives `200`. Fresh rerun unavailable in this shell. | Regression assertion at `common/tests.py:1064`. |
| Existing direct detail/list/filter isolation remains enforced | `contract/farms.py`, `contract/ops.py`, `common/access.py` scoped query paths | Farm, animal, task, My Work, dashboard and report endpoints | `test_farm_isolation_lists_details_and_writes`; `test_operations_task_detail_and_assignment_remain_farm_scoped`; `test_my_work_and_dashboard_are_personal_and_farm_scoped` | **PASS (prior authorization-suite run):** scope is applied before filters; unauthorized detail is hidden and filters do not widen access. Fresh rerun unavailable in this shell. | `common/tests.py:157` onward, `:492` onward, `:883` onward; prior 64-test suite recorded below. |

## Verification

- Passed: `python -m compileall -q contract operations organization animals common`
  in the development container.
- Passed: `python manage.py check` in the development container (no issues).
- Passed: focused D02-010 regression coverage — **4 tests**.
- Passed: complete development authorization regression suite — **64 tests**.
- Fresh focused rerun: **4 tests passed** in the running `farmos_dev`
  development container using the existing isolated Django test database
  (`--keepdb`). Django system check reported no issues. The database was
  preserved after the run.
- Initial test invocation without `--keepdb` could not create
  `test_farmos_dev` because that test database already existed; reran with
  `--keepdb` to reuse the isolated test database without deleting it.

## Status

**IMPLEMENTED AND VERIFIED — D02-010 PRODUCT LOCKED. Focused D02-010 rerun
passed 4/4. This evidence matrix is prepared for final implementation-lock
review. No Product semantics were changed. D02-011 has not been changed or
advanced.**
