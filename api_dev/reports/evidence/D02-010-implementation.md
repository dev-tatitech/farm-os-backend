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

| Locked requirement | Automated coverage | Expected result |
|---|---|---|
| Cross-Farm direct object enumeration is concealed | `test_d020_direct_object_concealment_and_visible_capability_denial` | Farm B Task cancellation by Farm A-only manager is `404 FARM_NOT_FOUND`. |
| Capability denial is distinct from concealed scope denial | `test_d020_direct_object_concealment_and_visible_capability_denial` | Farm A Task cancellation without `cancel_operation` is `403 PERMISSION_DENIED`. |
| Revoked mobile access invalidates scope and rejects queued work | `test_d020_mobile_revocation_rejects_queued_write_and_hides_work` | Sync scope is empty with the cache-removal directive; queued write is rejected with `403 CHANNEL_ACCESS_DENIED`; Task state is unchanged. |
| Farm deactivation preserves history | `test_d020_farm_deactivation_preserves_history_and_blocks_destructive_delete` | Farm becomes inactive and its completed Task remains linked to it. |
| Destructive deletion with authoritative dependencies is blocked | `test_d020_farm_deactivation_preserves_history_and_blocks_destructive_delete` | Instance and queryset deletion raise `ProtectedError`; Farm survives. |
| Inter-Farm transfer preserves original history scope | `test_d020_transfer_retains_historical_farm_scope` | Animal moves to Farm B; prior Task remains Farm A. |
| Current-Farm-only, dual-Farm, and Organization-wide visibility | `test_d020_transfer_retains_historical_farm_scope` | Farm B-only manager receives `404`; dual-Farm manager and Owner receive `200`. |
| Existing direct detail/list/filter isolation | `test_farm_isolation_lists_details_and_writes`, `test_operations_task_detail_and_assignment_remain_farm_scoped`, `test_my_work_and_dashboard_are_personal_and_farm_scoped` | Unauthorized scopes remain absent/concealed and filters never widen scope. |

## Verification

- Passed: `python -m compileall -q contract operations organization animals common`
  in the development container.
- Passed: `python manage.py check` in the development container (no issues).
- Passed: focused D02-010 regression coverage — **4 tests**.
- Passed: complete development authorization regression suite — **64 tests**.

## Status

**IMPLEMENTED AND VERIFIED — D02-010 PRODUCT LOCKED. D02-011 has not been
changed or advanced.**
