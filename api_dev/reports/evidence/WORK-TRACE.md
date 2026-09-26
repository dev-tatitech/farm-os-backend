# FarmOS Development Work Trace

This is the continuing evidence log for work performed in `api_dev/`. Add a
new dated entry whenever implementation, documentation, verification, or an
environmental blocker changes.

## 2026-09-23 — D02-COR-001 Operations architecture correction

### Scope

- Source specification: `TATI_FarmOS_Domain_02_D02-001_Operations_Architecture_Correction_Specification.pdf`.
- Development scope only: `api_dev/`. The live `api/` backend was not changed.

### Delivered

- Created `POST /api/v2/domain-actions/` for authorized, ad-hoc typed domain
  actions that must not require a fabricated Operations task.
- Reused the typed task domain-workflow handlers so direct actions retain the
  same validation, audit/timeline events, side effects, follow-up generation,
  transactions, and idempotency behavior.
- Preserved task-driven execution at
  `POST /api/v2/operations/tasks/{task_id}/complete/` and its task-to-result
  reference model.
- Added regression coverage for direct vaccination: it returns an authoritative
  result, creates no task, and safely replays with the same client request ID.
- Documented the direct-action API in the v2 registry.

### Documentation delivered

- Regenerated `api_dev/docs/FarmOS-Frontend-Integration-Guide.pdf`.
- Added direct-vs-task execution guidance, endpoint request/response examples,
  supported types, authorization rules, and current verification status.
- Added `reportlab==4.4.3` to `api_dev/requirements.txt` so PDF generation is
  reproducible in development images.

### Verification

- Passed: `python -m compileall -q contract operations common` in `farmos_dev`.
- Passed: Django configuration check and URL resolution for
  `/api/v2/domain-actions/` in `farmos_dev`.
- Passed: regenerated PDF extraction and visual layout check.
- Blocked: focused database-backed tests could not initialize because the
  `farmos_dev_db` hostname was unavailable to the running development
  container. This is an environment availability issue pending restoration of
  that service.

### Related evidence

- `D02-COR-001-implementation.md`
- `api_dev/docs/FarmOS-Frontend-Integration-Guide.pdf`

## 2026-09-23 — D02-002 Task Creation & Subject Model

### Delivered

- Enforced the reconciled canonical task-type vocabulary already defined by the
  v2.2 task model; no new enum values were introduced.
- Enforced current subject compatibility: animal-only treatment, health
  observation, weight, pregnancy check, sale, and mortality; animal-or-group
  vaccination, feed issuance, and movement; optional context for generic.
- Enforced female-animal eligibility for pregnancy-check tasks and rejected
  simultaneous animal and group subjects.
- Made manual task `due_at` required by the v2 creation schema and reject
  invalid priority values instead of silently replacing them.
- Derived typed task titles from the canonical type and selected subject.
  Generic tasks retain an explicit title because no generic derivation rule was
  invented.
- Validated an individual assignee's active farm access, Operations completion
  authority, and applicable domain capability before assignment or reassignment.
- Updated the frontend integration-guide generator with the corrected task
  planning and subject rules.

### Verification

- Restored the stopped development PostgreSQL and Redis services.
- Passed: Python compilation and development-container imports.
- Passed: focused D02 regression tests (3 tests).
- Passed: full shared API/access regression suite (41 tests).
- Status: **IMPLEMENTATION AND QA VERIFIED — LOCKED.**

## 2026-09-23 — D02-003 Backend Execution & Authorization

### Delivered

- Scoped assignment/reassignment capability checks to the task farm.
- Added row locking for assignment, acceptance, and start mutations so current
  task state is re-evaluated inside the mutation path.
- Added durable assignment/reassignment timeline events with actual actor,
  previous assignee, and new assignee context.
- Added regression coverage for reassignment history, stale previous-assignee
  denial, farm-isolated task detail, and unassigned-assignee rejection.

### Verification

- Passed: focused D02-003 authorization regression tests (3 tests).
- Passed: complete shared API/access regression suite (43 tests).
- Product decisions D02-BE-PD-001 and D02-BE-PD-002 remain deliberately
  resolved by Product Owner: automatically unassign affected open tasks on
  account deactivation or farm-access revocation.
- Passed: automatic-unassignment regression tests (2 tests) and the complete
  shared API/access suite (44 tests).
- Passed: complete development backend suite (46 tests).
- Added `D02-003-qa-readiness.md` for independent Domain 02 QA handoff.

## 2026-09-23 — D02-004 Task Lifecycle Reconciliation

### Delivered

- Corrected direct completion timestamps, draft execution restrictions, closed
  state restrictions, and exception/cancellation cleanup on reopen.
- Preserved the canonical persisted state set; no overdue, pending,
  reassigned, or rescheduled status was introduced.

### Verification

- Passed: focused lifecycle/access-loss checks (2 tests).
- Passed: complete development backend suite (47 tests).
- Evidence: `D02-004-implementation.md`.
- Product policy selected: no standalone rescheduling endpoint in this MVP;
  reassignment resets accepted/in-progress work to assigned for the new user.
- Passed: focused policy checks (4 tests) and complete development suite
  (48 tests).

## 2026-09-23 — D02-005 Completion & Domain Result

### Delivered

- Normalized public v2 task and direct-action result references to canonical
  completion types while retaining internal model/table references.
- Verified generic result-free completion, direct completion, and idempotent
  completion behavior.

### Verification

- Passed: focused D02-005 checks (3 tests).
- Passed: complete development backend suite (48 tests).
- Evidence: `D02-005-implementation.md`.
- Product lock authorized for D02-005 after internal verification; independent
  Domain 02 QA remains recorded as recommended post-lock assurance.

## 2026-09-23 — D02-006 Unable to Complete & Operational Exceptions

### Delivered

- Added the server-scoped Operational Exceptions queue with canonical reason
  filtering; it is a view over unable-to-complete tasks.
- Verified exception lifecycle, authority, recovery, and data-integrity rules.

### Verification

- Passed: focused exception checks (2 tests).
- Passed: complete development suite (49 tests).
- Evidence: `D02-006-implementation.md`.
- Locked policy decisions: notes required for `other`; no inferred alert or
  inventory links; reopen before cancellation. Full development suite passed:
  50 tests. Product lock authorized after internal verification.

## 2026-09-23 — D02-007 Scheduling & Recurring Work Reconciliation

### Delivered

- Verified and strengthened the existing server-side Schedule-to-Task model:
  schedule source linkage, row locking, unique occurrence protection, once
  deactivation, active/inactive lifecycle, and farm-scoped endpoints remain in
  place.
- Validated schedule templates with the normal task subject and assignee
  authorization rules, retained explicit schedule titles on generated tasks,
  and implemented correct calendar-month advancement.
- Ensured automatic scheduler runs do not falsely attribute generated work to
  the original schedule creator; automated tasks/events retain no human actor.
- Updated and regenerated the frontend integration guide and added
  `D02-007-implementation.md` evidence.

### Verification

- Passed focused D02-007 regressions (2 tests) in the development container.
- Passed complete development backend suite: **52 tests**.
- Product decisions authorized: generate one missed task when reactivating,
  calculate recurrence in Africa/Lagos, and deactivate any schedule whose
  stored assignee becomes ineligible. Added focused regression coverage for
  both reactivation and automatic deactivation. Passed complete development
  backend suite: **54 tests**. **D02-007 is locked.**

## 2026-09-23 — D02-008 My Work / Field Execution Reconciliation

### Delivered

- Preserved My Work as the authenticated user's personal, server-scoped open
  task inbox and aligned its dashboard aggregates with authorized farm scope.
- Added farm-scoped effective-capability enforcement to the personal execution
  actions: accept, start, complete, unable-to-complete, and cancel.
- Updated the frontend integration guide and added D02-008 evidence.

### Verification

- Passed focused My Work scope and execution-capability checks (2 tests).
- Passed complete development backend suite: **56 tests**.
- Resolved All Tasks and Activity through the existing scoped v2 user task and
  activity resources, with a regression covering personal historical scope.
  Passed complete development backend suite: **57 tests**. Local offline Sync
  Centre implementation remains outside this backend-only scope.

### Mobile API extension

- Added `/mobile/api/` JWT Bearer field-execution surface and Swagger at
  `/mobile/api/docs`; evidence: `D02-008-mobile-api.md`.
- Repaired the development HTTP E2E fixture/session setup and dashboard
  response defects. Final running-backend HTTP E2E: **48/48 passed**.
  **D02-008 is locked.**

## 2026-09-23 — D02-009 Manager Operations Dashboard

- Added the server-authoritative Operations dashboard aggregate with locked KPI definitions, Lagos reporting time, scoped authorization, and no side effects.
- Evidence: `D02-009-implementation.md`.

## 2026-09-24 — D02-011 Events, Audit & Activity

- Extended the existing canonical event store with structured business-event,
  actor snapshot/type, correlation, metadata, and changeset fields.
- Added event coverage for Operations lifecycle and schedule actions, retaining
  authorization-scoped timeline/dashboard projections.
- Applied `animals.0002_animalevent_actor_display_snapshot_and_more`; focused
  lifecycle/schedule event regression passed (4 tests).
- Evidence: `D02-011-implementation.md`. Four explicitly required product/API
  decisions remain open; D02-011 is not locked.

## 2026-09-24 — D02-012 Notifications & Alerts

- Added structured notification types and removed blanket routine completion
  notifications. Applied `operations.0003_notification_notification_type_and_more`.
- Focused assignment/reassignment notification regression passed.
- Evidence: `D02-012-implementation.md`; unresolved notification policies mean
  D02-012 is not locked.

## 2026-09-24 — D02-013 Failure, Idempotency & Concurrency

- Added same-key/different-request fingerprint conflict enforcement and applied
  `operations.0004_idempotencykey_request_fingerprint`.
- Focused retry, duplicate-event, and schedule generation regression passed
  (4 tests). Evidence: `D02-013-implementation.md`.
- Version/ETag, retention, offline conflict, bulk/sync, and engineering policy
  decisions remain open; D02-013 is not locked.

## 2026-09-24 — Domain 02 open decision register

- Added the unresolved D02-010 through D02-014 policy decisions to the
  Frontend Integration Guide so API consumers do not infer unsupported client
  behavior. These are product decisions, not backend defects.

## 2026-09-25 — D02-010 Farm / Subject / Data Isolation

- Implemented the product-locked concealed-404 object authorization policy,
  preserving 403 only for capability denial within a visible scope.
- Added authoritative mobile sync-scope cache invalidation guidance and kept
  all queued writes subject to live server-side revalidation.
- Protected Farms with authoritative Operations history from destructive
  deletion while retaining Domain 01 status-based deactivation and historical
  Farm attribution after Animal transfer.
- Added D02-010 regression coverage and evidence:
  `D02-010-implementation.md`.
- Passed development-container compilation and Django checks, focused D02-010
  regression coverage (4 tests), and complete authorization regression suite
  (64 tests). **D02-010 PRODUCT LOCKED.** D02-011 was not changed.
