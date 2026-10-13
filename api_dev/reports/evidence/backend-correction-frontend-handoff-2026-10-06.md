# Backend Correction — Frontend Handoff and Verification Evidence

Updated: 2026-10-13
Scope: `api_dev/` only
Status: backend changes verified in development; frontend acceptance and live promotion are not claimed.

## Frontend contract additions

| Feature | Frontend endpoints / contract | Backend behavior and UI guidance | Evidence |
|---|---|---|---|
| Animal groups | `/api/v2/groups/`, `/{group_id}/`, `/{group_id}/members/`, and `/{group_id}/members/{animal_id}/` | Farm-scoped group management. Membership removal preserves history; rejoining creates a new row. Do not show cross-farm animals as eligible. | `contract/groups.py`; `common.tests.Domain01Tests.test_v2_group_membership_preserves_history_and_conceals_cross_farm_animal` |
| Farm labels | `/api/v2/settings/labels/`, `/api/v2/settings/animals/{animal_id}/labels/` | Labels classify animals but do not encode authoritative health or lifecycle state. Reserved state names are rejected; assignment requires same-farm scope. | `contract/settings.py`; `common.tests.Domain01Tests.test_farm_labels_cannot_replace_authoritative_health_state` |
| Animal gallery | `/api/v2/animals/{animal_id}/media/` and `/media/{media_id}/primary/` | Multipart image upload, multiple media rows, optional capture time, and primary-image selection. The legacy profile image pointer stays synchronized. | `contract/animals.py`; `animals.AnimalMedia`; migration `animals.0003_stage1_groups_labels_media` |
| Observation lifecycle | `/api/v2/health/observations/`, `/{observation_id}/acknowledge/`, and `/{observation_id}/assess/` | Field observations are not diagnoses. Assessment supports resolve or escalation to a clinical case and is capability-gated. | `contract/health.py`; `common.tests.Domain01Tests.test_field_observation_flags_attention_without_diagnosis_and_clinical_assessment_is_gated`; migration `health.0003_observation_lifecycle` |
| Schedule windows and generated-task history | Schedule create/patch accepts `starts_at`, `ends_at`, `priority`; `GET /api/v2/operations/schedules/{schedule_id}/tasks/` lists generated work | `next_run_at` must be inside the window. Generated work inherits priority; ended windows stop producing occurrences. History is read from the canonical Task-to-Schedule relationship and retains source references. | `contract/ops.py`, `operations/services.py`; migration `operations.0005_schedule_window_priority`; `test_schedule_generation_validates_template_and_preserves_schedule_history` |
| Schedule display context | Schedule create/list/detail responses | Includes nested Farm, target, default-assignee, and creator display context while retaining the corresponding IDs. | `contract/ops.py`; `test_schedule_generation_validates_template_and_preserves_schedule_history` |
| Task selector and My Work contract | Eligible-target and eligible-assignee routes; dashboard/work endpoints | Selectors return current eligible targets and server-filtered, paginated capable assignees; task/dashboard data supports actionable My Work views. | `test_work_selectors_return_context_and_search_only_eligible_assignees`; current `common.tests` suite |
| Animal profile-name search and sorting | Web/mobile animal list filters | Search and name sorting use the saved profile name with deterministic tag/id fallbacks; unsupported sort keys return structured validation errors. | `test_animal_search_and_name_sort_use_profile_name_attribute`; current `common.tests` suite |
| Group vaccination execution roster | `/api/v2/operations/tasks/{task_id}/vaccination-roster/`; `/mobile/api/tasks/{task_id}/vaccination-roster/` | Paginated current group members include server-derived eligibility and reason. Mobile access is assignment/capability constrained; completion rechecks eligibility. | `test_group_vaccination_roster_returns_current_eligibility_and_reason` |
| Mobile field API | `/mobile/api/animals/`, `/work-types/{work_type}/eligible-targets/`, `/eligible-assignees/`, `/tasks/{task_id}/vaccination-roster/`, `/quick-record/`, `/health/cases/`, and `/notifications/` | JWT mobile session only; farm/capability scope is checked server-side; writes revalidate session and are idempotent where request IDs are supplied. The group vaccination roster is limited to the assigned worker and returns server-derived eligibility. | `contract/mobile.py`, `contract/ops.py`; mobile/auth regression coverage in `common.tests.py` |

The refreshed PDF is generated from `api_dev/docs/generate_frontend_integration_guide.py` and saved as `api_dev/docs/FarmOS-Frontend-Integration-Guide.pdf`. It includes endpoint examples, request fields, lifecycle guidance, authorization notes, the development base URL, and an explicit statement that backend verification is not frontend acceptance.

## Verification run

All runtime checks below targeted `farmos_dev` or a fresh Django temporary test database. The live `api/` backend was not modified or used.

| Check | Result | Notes |
|---|---:|---|
| Apply migrations to development database | PASS | `animals.0003_stage1_groups_labels_media`, `health.0003_observation_lifecycle`, and `operations.0005_schedule_window_priority` applied. |
| `manage.py check` | PASS | No system-check issues. |
| `makemigrations --check --dry-run` | PASS | No model/migration drift detected. |
| Main development HTTP E2E runner | PASS, 48/48 | Existing sandbox runner exercised auth, operations, health, notifications, search, dashboards, and legacy compatibility. |
| v2.2 release verifier | PASS, 28/28 | Updated verifier to use session-bound access tokens and to fetch the exact overdue Task rather than relying on first-page ordering. |
| Full Django suite | PASS, 69/69 | Ran against a fresh unique temporary database; it was destroyed by Django after completion. |
| Latest Django common contract suite | PASS, 74/74 | Ran 2026-10-13 in the development container against a uniquely named temporary test database; Django destroyed it after completion. Includes group filters, animal profile-name search/sort, task selectors, and My Work contract coverage. |
| Focused follow-up regressions | PASS, 1/1 each | Schedule history/context; work selector; animal name search/sort; group vaccination roster (web/mobile). Each run used a unique temporary database. |
| `git diff --check` and Python compilation | PASS | No whitespace errors or syntax errors in the edited development code. |

## Latest development-container run (2026-10-13)

- Started `farmos_dev_db`, Redis, and `farmos_dev` only; the live API service was not started or used.
- `contract/e2e_run.py`: PASS, 48/48. `contract/v22_verify.py`: PASS, 28/28.
- `manage.py test common.tests`: PASS, 74/74, using an isolated temporary database. The pre-existing `test_farmos_dev` database was left untouched.
- `manage.py check`: PASS. `makemigrations --check --dry-run`: PASS, no changes detected. Development OpenAPI endpoint on port 8001 returned HTTP 200.
- The E2E runner seeded test-only users and operational records in the development database; those records remain there. No E2E data was written to the live database.

## Acceptance boundary

- These results establish development-backend and automated-test evidence only.
- No frontend application was changed or visually/behaviorally accepted in this work.
- Frontend acceptance remains open. The frontend team should record results for: (1) gallery list, upload, primary-image selection, upload failure, and refresh; (2) mobile quick-record success and duplicate retry with the same `client_request_id`, plus denied farm/capability access; (3) schedule create/edit inside and outside its window, generated-task history pagination, and inactive/ended behavior; and (4) vaccination roster pagination, ineligible rows, assigned-worker access, and completion-time revalidation.
- For each frontend scenario, record the frontend build/commit, development environment, device/browser, steps, expected and observed result, and any defect. Backend automated results above do not imply these UI scenarios passed.
- The development API remains separate from live at `http://127.0.0.1:8001`; no promotion has been performed.
- Product status is not locked: frontend acceptance is still required. No lock or live promotion is claimed by this handoff.
