# D02-013 Failure, Idempotency & Concurrency — Implementation Evidence

## Implemented

- Added `IdempotencyKey.request_fingerprint` and migration
  `operations.0004_idempotencykey_request_fingerprint`.
- The atomic mutation wrapper now compares method, path, and canonical payload
  fingerprint before replaying a stored response. Same key/different request
  returns canonical `409 CONFLICT`; same request replays its committed result.
- Existing transaction boundaries, `select_for_update` lifecycle transitions,
  schedule occurrence uniqueness, and typed completion atomicity remain the
  authoritative consistency controls.

## Verification

- `test_idempotency_key_reuse_with_different_request_conflicts` passed.
- Focused D02-013 regression passed: **4 tests** covering same-key conflict,
  completion replay/duplicate-event prevention, once-only due schedule
  generation, and schedule occurrence history.

## Concurrency and lifecycle enforcement

- `atomic_mutation` serializes same-user idempotency handling within a database
  transaction; committed replays return the stored response and no second
  mutation is executed.
- Completion locks the Task row and creates required typed result, Task state,
  and event inside one transaction. A second non-replay completion is rejected
  by the authoritative lifecycle guard.
- Schedule generation locks the schedule row and uses the occurrence key to
  prevent duplicate generated Tasks.

## Unresolved decisions

Idempotency-key transport finalization, retention, record-version/ETag
contract, offline business-conflict policy, bulk/sync-batch policies, and
engineering alert thresholds remain policy-required. D02-013 is not locked.
