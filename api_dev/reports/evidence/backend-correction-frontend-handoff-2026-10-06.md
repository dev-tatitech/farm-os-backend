# Backend Correction — Frontend Handoff and Verification Evidence

Date: 2026-10-06  
Scope: `api_dev/` only  
Status: backend changes verified in development; frontend acceptance and live promotion are not claimed.

## Frontend contract additions

| Feature | Frontend endpoints / contract | Backend behavior and UI guidance | Evidence |
|---|---|---|---|
| Animal groups | `/api/v2/groups/`, `/{group_id}/`, `/{group_id}/members/`, and `/{group_id}/members/{animal_id}/` | Farm-scoped group management. Membership removal preserves history; rejoining creates a new row. Do not show cross-farm animals as eligible. | `contract/groups.py`; `common.tests.Domain01Tests.test_v2_group_membership_preserves_history_and_conceals_cross_farm_animal` |
| Farm labels | `/api/v2/settings/labels/`, `/api/v2/settings/animals/{animal_id}/labels/` | Labels classify animals but do not encode authoritative health or lifecycle state. Reserved state names are rejected; assignment requires same-farm scope. | `contract/settings.py`; `common.tests.Domain01Tests.test_farm_labels_cannot_replace_authoritative_health_state` |
| Animal gallery | `/api/v2/animals/{animal_id}/media/` and `/media/{media_id}/primary/` | Multipart image upload, multiple media rows, optional capture time, and primary-image selection. The legacy profile image pointer stays synchronized. | `contract/animals.py`; `animals.AnimalMedia`; migration `animals.0003_stage1_groups_labels_media` |
| Observation lifecycle | `/api/v2/health/observations/`, `/{observation_id}/acknowledge/`, and `/{observation_id}/assess/` | Field observations are not diagnoses. Assessment supports resolve or escalation to a clinical case and is capability-gated. | `contract/health.py`; `common.tests.Domain01Tests.test_field_observation_flags_attention_without_diagnosis_and_clinical_assessment_is_gated`; migration `health.0003_observation_lifecycle` |
| Schedule windows | Schedule create/patch accepts `starts_at`, `ends_at`, `priority` | `next_run_at` must be inside the window. Generated work inherits priority; ended windows stop producing occurrences. | `contract/ops.py`, `operations/services.py`; migration `operations.0005_schedule_window_priority` |
| Mobile field API | `/mobile/api/animals/`, `/work-types/{work_type}/eligible-targets/`, `/eligible-assignees/`, `/quick-record/`, `/health/cases/`, and `/notifications/` | JWT mobile session only; farm/capability scope is checked server-side; writes revalidate session and are idempotent where request IDs are supplied. | `contract/mobile.py`; mobile/auth regression coverage in `common.tests.py` |

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
| `git diff --check` and Python compilation | PASS | No whitespace errors or syntax errors in the edited development code. |

## Acceptance boundary

- These results establish development-backend and automated-test evidence only.
- No frontend application was changed or visually/behaviorally accepted in this work.
- Gallery upload, mobile quick-record, and some schedule-window edge cases still merit focused frontend/API acceptance scenarios beyond the recorded broad suite.
- The development API remains separate from live at `http://127.0.0.1:8001`; no promotion has been performed.
