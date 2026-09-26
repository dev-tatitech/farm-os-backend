# D02-007 — Scheduling & Recurring Work Reconciliation

Date: 2026-09-23  
Scope: `api_dev/` only

## Implemented

- Preserved Schedule and Task as independent records. A run creates a normal
  Operations Task with `source.type = schedule`, `source.id = schedule_id`,
  and a unique schedule occurrence key.
- Kept the authoritative recurrence vocabulary: `once`, `daily`, `weekly`,
  and `monthly`. Once schedules deactivate after their run.
- Kept automatic due execution server-side through
  `operations.management.commands.run_due_schedules` and protected each run
  with a schedule row lock plus the unique occurrence constraint.
- Validated schedule templates against the same canonical task-type, subject,
  active-assignee, farm-access, Operations capability, and domain-capability
  requirements used for manual task creation.
- Kept the Schedule's explicit title on generated Tasks; typed manual task
  title derivation does not overwrite the schedule template label.
- Corrected monthly recurrence to use calendar months and the last valid day
  of the destination month (for example, Jan 31 to Feb 28/29), rather than a
  30-day approximation.
- Retained manual-run traceability: manually created occurrences record the
  initiating user while retaining schedule source linkage. Automated runs have
  no fabricated human actor (`created_by` is null).
- Preserved farm-scoped schedule listing, detail, run, patch, and deactivation
  checks. Deactivation does not alter generated Task records.
- Updated the frontend integration-guide source and regenerated PDF with the
  schedule API, recurrence, Run Now, lifecycle, and backend-authority rules.

## Verification

- Passed Python syntax compilation for modified modules.
- Passed focused scheduling regressions in `farmos_dev`:
  - explicit title/source linkage and calendar-month handling;
  - deactivation/history retention and ineligible-assignee rejection;
  - server-generated once occurrence, null automatic actor, and no duplicate
    occurrence on a repeated scheduler pass.
- Passed complete development regression suite after the lock decisions: **54 tests**.

## Deliberately unresolved product/API decisions

The Product Owner resolved the scheduling decisions on 2026-09-23:

- Reactivation generates **one** missed occurrence, then advances a recurring
  schedule to its next future occurrence; it does not backfill every missed
  interval.
- Recurrence is calculated in the `Africa/Lagos` timezone.
- If a stored assignee becomes ineligible, the schedule is automatically
  deactivated and no unauthorized task is created.

Schedule Activity remains derived from generated Tasks through their schedule
source linkage; no separate activity resource has been introduced.

## Status

**IMPLEMENTATION, QA, AND PRODUCT DECISIONS VERIFIED — LOCKED.**
