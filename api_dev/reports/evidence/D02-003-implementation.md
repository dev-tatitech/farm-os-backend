# D02-003 Backend Execution & Authorization — Implementation Evidence

Date: 2026-09-23

## Endpoint authorization matrix

| Endpoint | Required authority | Additional server checks |
|---|---|---|
| `POST /operations/tasks/` | `create_operation` | Active account, organization and farm scope, task-type subject compatibility, active eligible assignee, due datetime and priority. |
| `GET /operations/tasks/` | `view_operation` | Query is scoped to authorized farms. |
| `GET /operations/tasks/{id}/` | `view_operation`, unless current assignee | Current farm scope always required. |
| `POST /tasks/{id}/assign/` | `assign_operation` or `reassign_operation` at the task farm | Current task state, assignee organization/account/farm/capability eligibility. |
| `POST /tasks/{id}/accept/` | Current assignee or organization owner | Current farm scope and task state. |
| `POST /tasks/{id}/start/` | Current assignee or organization owner | Current farm scope and task state; auto-accepts where permitted. |
| `POST /tasks/{id}/complete/` | `complete_operation` plus typed domain capability | Current farm scope, current assignee/owner relationship, task state and domain validation. |
| `POST /tasks/{id}/unable-to-complete/` | Current assignee or organization owner | Current farm scope and reason-code validation. |
| `POST /tasks/{id}/cancel/` | `cancel_operation` | Current farm scope and task state. |
| `POST /tasks/{id}/reopen/` | `assign_operation` | Current farm scope and permitted lifecycle state. |
| `GET /operations/my-work/` | `view_operation` | Authenticated principal only; current authorized farms and current assignments only. |

Channel entitlement and active-account validation are enforced by the existing authenticated request path; role names are never authorization inputs.

## Assignee validation and assignment history

- Assignees must exist in the task organization, be active, and have active
  farm authority; an assignment cannot create farm access.
- Typed tasks additionally require current `complete_operation` plus an
  applicable domain capability at the selected farm.
- Assignment/reassignment locks the task row, supersedes pending historical
  assignments, sets exactly one current assignee, emits a durable timeline
  event with actor/previous/new assignee context, and notifies the new assignee.
- Accept, start, and completion re-read current task state inside the mutation
  path, preventing an obsolete assignee from acting after reassignment.

## Product decisions resolved

| Decision | Current behavior | Reason |
|---|---|---|
| D02-BE-PD-001: open tasks after assignee deactivation | Automatically unassign every affected open task, reset it to draft, preserve assignment history as superseded, and emit a task-unassigned event. | Product Owner decision: automatically unassign. |
| D02-BE-PD-002: open tasks after farm-assignment revocation | Automatically unassign every affected open task for that farm, reset it to draft, preserve assignment history as superseded, and emit a task-unassigned event. | Product Owner decision: automatically unassign. |

## Automated verification

- Focused D02-003 authorization and access-loss regression tests: **5 passed**.
- Complete shared API/access regression suite: **44 passed**.
- D02-003 coverage includes farm-isolated task detail, unassigned assignee
  rejection, reassignment replacement/history, and denial of a stale previous
  assignee's accept attempt.

**Status: IMPLEMENTATION AND INTERNAL QA VERIFIED. Independent Domain 02 QA
remains required by the source specification before product acceptance/lock.**
