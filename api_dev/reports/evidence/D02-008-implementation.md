# D02-008 — My Work / Field Execution Reconciliation

Date: 2026-09-23  
Scope: `api_dev/` only

## Implemented

- Preserved `/api/v2/operations/my-work/` as a server-scoped, paginated inbox
  of open tasks assigned to the authenticated user, never a client-filtered
  farm-wide task listing.
- Strengthened `/api/v2/dashboard/my-work/`: it requires `view_operation`,
  applies authorized-farm scope to all personal summary counts, and applies
  `farm_id` consistently to the summary and temporal buckets.
- Enforced `complete_operation` at the Task's current farm for Accept, Start,
  Complete, and Unable-to-Complete mutations; Cancel now evaluates
  `cancel_operation` at that same farm.
- Retained task subject and farm authority through the existing typed
  completion path, domain capability checks, lifecycle constraints, and
  idempotency handling. Completion removes the task from the open inbox.
- Updated the frontend integration guide with My Work data-source, execution,
  farm-filter, offline-intent, and retry guidance.
- Verified the existing personal-history/activity v2 resources and aligned
  their optional `farm_id` filters with authorized-farm scope.

## Verification

- Passed syntax compilation for modified modules.
- Passed focused My Work tests covering personal task visibility, farm-filter
  denial, farm-scoped dashboard summary, and execution-capability denial.
- Passed complete development regression suite: **57 tests**.

## Remaining client-scope item

- Personal task history is `GET /api/v2/users/me/tasks/`; personal activity is
  `GET /api/v2/users/me/activity/`. Both are now documented and scoped.
- Mobile offline queue/Sync Centre is a client capability; backend mutation
  revalidation and idempotency are supported, but no mobile client exists in
  `api_dev/` to implement local capture, sync-state UI, or conflict handling.

## Status

**IMPLEMENTATION, QA, MOBILE JWT API, AND END-TO-END VERIFICATION — LOCKED.**

## Final end-to-end verification

- Repaired the development HTTP E2E harness to create active, revocable
  session-backed JWTs and to use the current capability/payload contracts.
- Passed **48 of 48** HTTP checks against the running `farmos_dev` backend,
  including My Work, task lifecycle, typed completion, idempotency, timeline,
  dashboards, health workflows, notifications, search, and no-v2-500 checks.
