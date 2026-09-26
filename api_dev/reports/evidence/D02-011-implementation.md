# D02-011 Events, Audit & Activity — Implementation Evidence

## Implemented reconciliation

- Extended the existing append-only `animals.AnimalEvent` store instead of
  creating a parallel activity history: canonical `event_name`, actor type and
  historical display snapshot, source module, correlation ID, structured
  metadata and changeset are now persisted.
- Existing `event_date` is the authoritative `occurred_at`; immutable
  `created_at` is exposed as `recorded_at`. Human actions retain the durable
  actor foreign key and a display snapshot; scheduler events retain a system
  actor context.
- Operations emits canonical events for creation, initial assignment,
  assignment/reassignment, acceptance, start, completion, cancellation,
  unable-to-complete, reopening, schedule creation/update/deactivation, and
  schedule task generation. Completion includes its result reference and a
  correlation ID shared with its typed domain-result event.
- Existing `/api/v2/timeline/` remains the paginated, authorization-scoped
  canonical event projection for farm/subject timeline use. Dashboard recent
  activity already consumes this same event store.

## Contract and enforcement

- Event writes occur after successful state persistence; `complete_task` and
  schedule expansion emit within their existing database transactions.
- The retry-safe completion path returns its stored response, so it does not
  create a second completion event.
- Timeline and dashboard queries begin with `authorized_farms(user, org)`;
  `farm_id`, `animal_id`, and event type filters only narrow that scope.
- Events have no ordinary write/delete endpoint. History is append-only to
  product users; corrections are represented by new events and changesets.
- Event metadata is minimized to lifecycle, result-reference, and changed
  fields. It does not duplicate completion payloads or attachments.

## Requirement-to-test/evidence matrix

| Requirement | Implementation location | Endpoint/service | Automated test | Result | Evidence |
|---|---|---|---|---|---|
| Structured canonical, append-only event facts | `animals/models.py:AnimalEvent`; `animals/event.py:new_event` | Event store / `/api/v2/timeline/` | `test_task_completion_retry_exactly_once` | Passed | This file |
| Creation, assignment, acceptance, and start history | `operations/services.py:create_task`, `assign_task`, `accept_task`, `start_task` | Task lifecycle services | `test_task_lifecycle_events_are_canonical_and_append_only` | Passed | This file |
| Completion result correlation and duplicate-event protection | `operations/services.py:complete_task` | `POST /api/v2/operations/tasks/{id}/complete/` | `test_task_completion_retry_exactly_once` | Passed: one `operation.completed` event with correlation ID | This file |
| Schedule event history | `contract/ops.py` schedule endpoints; `operations/services.py:run_schedule` | Schedule create/update/deactivate/run | `test_schedule_generation_validates_template_and_preserves_schedule_history` | Passed: create, generated-task, and deactivation event names asserted | This file |
| Farm-scoped activity projection and pagination | `contract/timeline.py:list_timeline` | `GET /api/v2/timeline/` | Existing authorization/timeline regression; full suite | Passed | This file |

## Verification

- Focused D02-011 lifecycle and schedule event regression: **4 tests passed**.
- Schema migration applied to the development database:
  `animals.0002_animalevent_actor_display_snapshot_and_more`.
- Full development regression: **60 tests discovered; completed with no reported failures**.

## Explicitly unresolved locked decisions

No behaviour was inferred for:

1. `operation.became_overdue` versus a derived overdue condition (D02-COR-297).
2. Offline activity ordering by occurrence time, recording time, or a defined combination (D02-COR-280).
3. Event retention/archive/deletion policy (D02-COR-299).
4. Final dedicated activity endpoint route contract (D02-COR-303). The existing `/api/v2/timeline/` is documented as the current scoped projection only.

## Status

**PARTIALLY IMPLEMENTED — ready for focused review; cannot be locked until the four product/API decisions above are resolved and the full regression is completed.**
