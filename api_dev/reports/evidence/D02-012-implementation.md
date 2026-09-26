# D02-012 Notifications & Alerts — Implementation Evidence

## Implemented

- Retained the recipient-scoped in-app Notification Center, unread count, and
  owner-only read/read-all mutations at `/api/v2/notifications/`.
- Added structured `notification_type` to the canonical notification record and
  API serialization. Assignment, reassignment, cancellation, unable-to-complete
  and reopening notifications now expose a machine-readable type.
- Applied `operations.0003_notification_notification_type_and_more` to the
  development database.
- Removed blanket routine completion notifications to the task creator; task
  completion remains authoritative through Task state, canonical events,
  activity, and reporting rather than creating manager/owner notification noise.
- Unable-to-complete reports now resolve notification recipients from current
  active farm assignments plus `assign_operation` capability. They do not
  broadcast to organization members or rely on the task creator being a
  manager.
- Existing farm-scoped Health/Farm alert resources and dashboard attention
  projections remain condition-based and separate from Task lifecycle state.

## Enforcement and tests

- Notification list, unread count, individual read, and read-all are filtered
  by authenticated recipient and organization. A read operation cannot mutate
  another recipient's notification.
- Notifications retain farm and authoritative record references; navigation
  continues to re-enter the protected source endpoint, where current access is
  checked.
- Focused tests passed: `test_task_reassignment_revokes_previous_assignee_and_preserves_history` asserts `task_assigned` and `task_reassigned` recipient types; `test_operational_exceptions_queue_is_server_scoped` asserts an authorized manager receives `operational_exception_created`.

## Unresolved product decisions

No policy was invented for due-soon threshold, overdue escalation, previous
assignee reassignment notice, critical completion, severity, persisted alerts,
preferences, organization configuration, retention, external delivery channels,
or final notification route alignment. D02-012 is therefore not lock-ready.
