# Development Scope

All implementation work must stay in `api_dev/`, the existing development
backend directory. The user's reference to `dev_api` means `api_dev/` in this
repository; do not create or rename a directory to `dev_api/`.

Do not edit the live backend in `api/`. Do not modify files outside `api_dev/`
unless the user explicitly requests an exception. Reading other project files
for context is allowed.

Run application checks and tests against the development backend. Do not
promote development changes to live without an explicit user request.
