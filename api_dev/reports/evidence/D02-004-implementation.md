# D02-004 Task Lifecycle Reconciliation — Implementation Evidence

Date: 2026-09-23

## Implemented lifecycle rules

- Persisted states remain exactly: `draft`, `assigned`, `accepted`,
  `in_progress`, `completed`, `unable_to_complete`, and `cancelled`.
- Direct completion from `assigned` is valid and preserves null `accepted_at`
  and `started_at`; result creation and task completion remain transactional.
- `draft` cannot be accepted, started, or marked unable-to-complete.
- Start is valid only from `assigned` or `accepted`; starting assigned work
  auto-accepts it.
- Completed remains terminal.
- Unable-to-complete and cancelled tasks must be reopened before assignment,
  cancellation, or completion can proceed.
- Reopen clears stale exception/cancellation fields and returns to `draft` or
  `assigned` based on whether an assignee is supplied.
- Overdue and pending remain derived query/dashboard conditions, not persisted
  task states.

## Verification

- Focused lifecycle, access-loss, and reassignment-policy checks: **4 passed**.
- Complete development backend test suite: **48 passed**.
- Django system checks: no issues.

## Resolved lifecycle policy

1. **D02-COR-027: standalone rescheduling.** This MVP does not provide a
   standalone open-task rescheduling endpoint. Reopen may supply a new
   `due_at`; no undocumented `/reschedule/` endpoint or lifecycle state is
   introduced.
2. **D02-COR-029: reassignment of accepted/in-progress tasks.** Reassignment
   resets the task to `assigned`, clears acceptance/start timestamps, replaces
   the current assignee, and preserves history. The new assignee must accept or
   start the work themselves.

**Status: IMPLEMENTATION VERIFIED. Independent Domain 02 QA remains required
before formal product acceptance/lock.**
