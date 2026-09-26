# D02-014 Reporting & Traceability — Implementation Evidence

## Implemented

- Added read-only `GET /api/v2/reports/operations/overview/`.
- The projection is built from authorized Task, Schedule, and canonical event
  datasets and exposes task status summary, overdue drill-down, operational
  exceptions, workload by assignee, schedule state, and paginated task history.
- Farm filters narrow current authorized scope only; the response includes an
  evaluation timestamp and scope metadata.

## Verification

- `test_operations_reporting_overview_is_farm_scoped_and_read_only` passed:
  authorized Farm A data is returned and direct Farm B access is denied.

## Deferred policy-dependent metrics

Completion rate, on-time completion, overdue rate, reporting timezone,
duration rules, export formats, historical labels, and export/job policy are
not exposed until their locked definitions are supplied. D02-014 is not locked.
