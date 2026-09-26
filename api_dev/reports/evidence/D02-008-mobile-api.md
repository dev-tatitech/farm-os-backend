# D02-008 Mobile JWT Field API

Date: 2026-09-23  
Scope: `api_dev/` only

## Delivered

- Added JWT Bearer-only mobile API at `/mobile/api/`.
- Added mobile Swagger UI at `/mobile/api/docs` and OpenAPI at
  `/mobile/api/openapi.json`.
- Restricted the mobile surface to My Work dashboard/inbox, personal task
  detail, Accept, Start, Complete, and Unable-to-Complete.
- Validates a live access token, active refresh session, active account, and
  mobile channel before every request; browser cookies are not accepted.
- Each task operation revalidates authorized farm, personal task relationship,
  lifecycle, Operations capability, and typed domain permission. Completion
  and exception retries retain existing idempotency behavior.

## Verification

- Passed Django system check.
- Passed focused JWT My Work, cookie rejection, task-detail, and Swagger-route
  regression.
