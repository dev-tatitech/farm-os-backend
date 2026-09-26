# D02-002 Task Creation & Subject Model — Implementation Evidence

Date: 2026-09-23

## Implemented

- Preserved the existing ten canonical v2.2 task types; no new enum values.
- Enforced supported task-type/subject combinations and single-subject choice.
- Enforced female-animal subjects for pregnancy-check tasks.
- Required `due_at` for manual v2 task creation and reject invalid priorities.
- Derived titles for typed tasks; generic tasks require an explicit title.
- Enforced active, farm-scoped, capability-eligible individual assignees on
  create and reassignment.
- Updated the frontend integration guide and task verification payloads.

## Verification and lock status

- Python compilation and development-container imports passed.
- Focused D02 regression tests passed: derived titles, subject restrictions,
  direct-action isolation, and idempotent task completion.
- Full shared API/access regression suite passed: **41 tests**.
- The regenerated integration guide contains the D02-002 planning section.

**Status: IMPLEMENTATION AND QA VERIFIED — LOCKED.**
