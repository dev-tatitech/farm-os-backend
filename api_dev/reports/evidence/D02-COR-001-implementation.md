# D02-COR-001 Operations Architecture Correction — Implementation Evidence

Date: 2026-09-23

## Implemented scope

The v2 development API now supports the two execution paths required by the
correction specification:

1. `POST /api/v2/operations/tasks/{id}/complete/` remains task-driven. It
   performs the typed domain transaction and retains the task-to-result
   reference.
2. `POST /api/v2/domain-actions/` records an authorized ad-hoc domain action
   directly. It does not create a Task and returns the authoritative result
   reference with `execution_context: "direct"`.

Supported direct typed actions are vaccination, treatment, feed issuance,
sale, movement, observation, weight, pregnancy check, and mortality. Generic
tasks are intentionally rejected because they have no authoritative domain
result.

The direct path uses the same domain workflow handlers as task completion,
therefore preserving existing validation, timeline events, inventory/state
effects, follow-up task generation, and transaction boundaries. Follow-up work
from a direct record records its source type and record ID without inventing a
parent task.

Authorization is domain-specific: the direct endpoint requires the relevant
domain capability and farm access, not `complete_operation`. This maintains the
specified separation between Operations and domain capabilities.

## Regression coverage

`common.tests.Domain01Tests.test_direct_v2_domain_action_creates_result_without_task`
verifies that a veterinarian can record a direct vaccination, receives an
authoritative result reference, creates no task, and gets an idempotent replay.

## Verification status

- `python -m compileall -q contract operations common` in `farmos_dev`: passed.
- Django URL resolution for `/api/v2/domain-actions/` in `farmos_dev`: passed.
- `python manage.py check --deploy` in `farmos_dev`: completed with five
  pre-existing deployment-security warnings (HSTS, SSL redirect, development
  secret key, and secure cookie settings); no implementation errors.
- Focused database test command was attempted in `farmos_dev` but could not
  initialize because hostname `farmos_dev_db` was unavailable on the container
  network. This is an environment availability issue, not a test failure.
