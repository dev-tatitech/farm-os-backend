# D02-006 Unable to Complete & Operational Exceptions — Implementation Evidence

Date: 2026-09-23

## Implemented

- Preserved the ten canonical unable-to-complete reason codes and optional
  contextual notes/client request ID.
- Enforced current assignee or organization-owner authority and only allows
  the transition from `assigned`, `accepted`, or `in_progress`.
- Kept exception recording distinct from cancellation and completion failure;
  it creates no typed domain result or subject state change.
- Preserved idempotent exception mutation behavior and current task-state
  checks for stale/offline requests.
- Added `GET /api/v2/operations/exceptions/`: a server-scoped management queue
  over `unable_to_complete` tasks, optionally filtered by canonical
  `reason_code`. It is not a task type or lifecycle state.
- Confirmed exception recovery uses `reopen` with optional assignee/due date;
  standalone exception assignment is rejected until reopened.

## Exception history

The active task fields are cleared when reopened so that the current task state
is accurate. The prior unable event, including actor, reason, notes, task,
farm, subject, and timestamp, remains in the immutable timeline/event history.

## Verification

- Focused exception queue/lifecycle/policy checks: **4 passed**.
- Complete development backend suite: **50 passed**.
- Django system checks: no issues.

## Locked policy decisions

- `other` requires non-empty explanatory notes.
- This MVP does not create inferred structured exception links to alerts or
  inventory records without an explicit relationship contract.
- Cancellation does not transition directly from `unable_to_complete`; an
  authorized user must reopen the work before cancelling it.

**Status: PRODUCT LOCKED — D02-006.** Product lock was authorized by the user
on 2026-09-23 after internal verification. Independent Domain 02 QA remains a
recommended post-lock assurance activity.
