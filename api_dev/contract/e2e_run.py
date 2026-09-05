"""Sandbox E2E runner. Invoked via: python manage.py shell < contract/e2e_run.py"""
import json
from datetime import date, timedelta
from decimal import Decimal
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.utils import timezone

from account.models import EmailValidation, User
from account.utils.jwt_utils import create_access_token
from animals.models import Animal
from common.permissions import Permissions
from feed.models import FeedInventory
from health.models import HealthCase, HealthObservation, TreatmentRecord, VaccinationRecord
from operations.models import Notification, Task
from organization.models import Farm, FarmType, Organization
from role.models import Permission, Role, RolePermission, UserRole

BASE = "http://127.0.0.1:8000"
results = []


def check(name, ok, **extra):
    results.append({"name": name, "ok": bool(ok), **extra})


def http(method, path, token=None, body=None):
    headers = {"Host": "127.0.0.1"}
    if token:
        headers["Cookie"] = "client_access_token=%s" % token
    data = None
    if body is not None:
        data = json.dumps(body, default=str).encode()
        headers["Content-Type"] = "application/json"
    req = Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=25) as resp:
            raw = resp.read()
            parsed = json.loads(raw.decode() or "{}") if raw else {}
            return resp.status, parsed
    except HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw.decode() or "{}")
        except Exception:
            parsed = {"raw": raw.decode()[:400]}
        return exc.code, parsed


def ok_success(status, body):
    return status == 200 and (body.get("success") is True or "paths" in body or "num_pages" in body)


def seed_user(email, username, org=None):
    user, _ = User.objects.get_or_create(
        email=email, defaults={"username": username, "account_status": "Active"}
    )
    user.set_password("E2ePass123!")
    user.is_superuser = False
    user.is_staff = False
    user.account_status = "Active"
    if org is not None:
        user.organization = org
    user.save()
    EmailValidation.objects.update_or_create(
        email=email,
        defaults={"code": "000000", "is_used": True, "expires_at": timezone.now()},
    )
    return user


owner = seed_user("e2e.owner@farmos.test", "e2e_owner")
org = owner.organization or owner.organizations.first()
if not org:
    org = Organization.objects.create(
        user=owner, name="E2E Org", code="E2EORG2", status="active"
    )
    owner.organization = org
    owner.save(update_fields=["organization"])
elif org.user_id != owner.id:
    org.user = owner
    org.save(update_fields=["user"])

ft, _ = FarmType.objects.get_or_create(code="e2e-livestock", defaults={"name": "Livestock"})
farm = Farm.objects.filter(organization=org).first()
if not farm:
    farm = Farm.objects.create(
        organization=org,
        name="E2E Farm",
        farm_code="E2EFARM2",
        farm_type=ft,
        is_primary=True,
        status="active",
    )

ibrahim = seed_user("e2e.ibrahim@farmos.test", "e2e_ibrahim", org=org)
role, _ = Role.objects.get_or_create(
    organization=org, code="e2e_field", defaults={"name": "E2E Field Worker"}
)
needed = [
    Permissions.Health.CREATE,
    Permissions.Health.VIEW,
    Permissions.Health.UPDATE,
    Permissions.Feed.CREATE,
    Permissions.Feed.VIEW,
    Permissions.Animal.VIEW,
    Permissions.Animal.CREATE,
    Permissions.SalesRecord.CREATE,
    Permissions.MovementRecord.CREATE,
    Permissions.Farm.UPDATE,
    Permissions.Reports.LIVESTOCK_DASHBOARD,
]
for code in needed:
    perm = Permission.objects.filter(code=code).first()
    if not perm:
        perm = Permission.objects.create(code=code, name=code, module="e2e")
    RolePermission.objects.get_or_create(role=role, permission=perm)
UserRole.objects.get_or_create(user=ibrahim, role=role, farm=farm)

tag = "E2E-IBRAHIM-%s" % timezone.now().strftime("%H%M%S")
animal = Animal(
    user=owner,
    farm=farm,
    tag_id=tag,
    gender="female",
    source_type="opening_record",
    status="active",
    estimated_age_months=18,
)
animal.save()

inventory, _ = FeedInventory.objects.get_or_create(
    farm=farm,
    feed_name="E2E Hay",
    defaults={"quantity_available": Decimal("100.00"), "unit": "kg"},
)
if inventory.quantity_available < Decimal("50.00"):
    inventory.quantity_available = Decimal("100.00")
    inventory.save(update_fields=["quantity_available"])

owner_token = create_access_token({"sub": str(owner.id)})
ibrahim_token = create_access_token({"sub": str(ibrahim.id)})

# --- isolation / auth ---
st, body = http("GET", "/api/openapi.json")
dev_paths = sorted((body or {}).get("paths", {}))
check("dev_openapi_unified", st == 200 and len(dev_paths) >= 290, http=st, count=len(dev_paths))
check("dev_has_login", "/api/auth/login" in dev_paths)
check("dev_has_v2_users_me", "/api/v2/users/me/" in dev_paths)
check("dev_omits_deprecated_profile", not any("animal-profile/v2/" in p for p in dev_paths))
st, body = http("GET", "/api/v2/openapi.json")
v2_paths = sorted((body or {}).get("paths", {}))
check("v2_openapi", st == 200 and len(v2_paths) >= 40, http=st, count=len(v2_paths))
check("v2_openapi_v2_only", "/api/auth/login" not in v2_paths and "/api/v2/users/me/" in v2_paths)

st, body = http("GET", "/api/v2/users/me/")
check("v2_unauth_me", st == 401 and body.get("code") == "AUTHENTICATION_REQUIRED", http=st, code=body.get("code"))
st, body = http("POST", "/api/auth/login", body={"email": "nobody@example.com", "password": "nope"})
check("legacy_login_error", st == 401 and body.get("status") == "Error", http=st, status=body.get("status"))

# --- legacy smoke ---
for name, path in [
    ("legacy_org", "/api/organization/oganization/"),
    ("legacy_farm", "/api/organization/farm/"),
    ("legacy_animals", "/api/animals/animal/1/20/%s" % farm.id),
    ("legacy_animal_profile_v2", "/api/animals/animal-profile/v2/%s" % animal.id),
    ("legacy_vaccinations", "/api/health/vaccination/1/20/%s" % farm.id),
    ("legacy_treatments", "/api/health/treatment/1/20/%s" % farm.id),
    ("legacy_feed_issue", "/api/feed/feed-issue/1/20/%s" % farm.id),
    ("legacy_farm_units", "/api/farm/all-farm-unit/1/20"),
    ("legacy_org_dashboard", "/api/organization/organization/dashboard/"),
]:
    st, body = http("GET", path, token=owner_token)
    check(name, ok_success(st, body), http=st, message=body.get("message"))

# --- Ibrahim vaccination E2E ---
st, me = http("GET", "/api/v2/users/me/", token=ibrahim_token)
check("ibrahim_me", ok_success(st, me) and (me.get("data") or {}).get("email") == ibrahim.email, http=st)
open_before = ((me.get("data") or {}).get("work_summary") or {}).get("open_tasks") or 0

st, dash_before = http("GET", "/api/v2/dashboard/farm/%s/" % farm.id, token=owner_token)
farm_open_before = (((dash_before.get("data") or {}).get("tasks") or {}).get("open") or 0)

due = (timezone.now() + timedelta(days=1)).isoformat()
st, created = http(
    "POST",
    "/api/v2/operations/tasks/",
    token=owner_token,
    body={
        "farm_id": farm.id,
        "task_type": "vaccination",
        "title": "Ibrahim vaccination",
        "animal_id": animal.id,
        "assignee_id": str(ibrahim.id),
        "due_at": due,
        "priority": "high",
    },
)
task_id = (created.get("data") or {}).get("id")
check("create_vaccination_task", ok_success(st, created) and task_id, http=st, task_id=task_id)

st, inbox = http("GET", "/api/v2/operations/my-work/", token=ibrahim_token)
ids = [row.get("id") for row in (inbox.get("data") or [])]
check("ibrahim_my_work_contains_task", ok_success(st, inbox) and task_id in ids, http=st, ids=ids)

st, today = http("GET", "/api/v2/operations/today/", token=ibrahim_token)
check("ibrahim_today", ok_success(st, today), http=st)

st, accepted = http("POST", "/api/v2/operations/tasks/%s/accept/" % task_id, token=ibrahim_token, body={})
check(
    "ibrahim_accept",
    ok_success(st, accepted) and (accepted.get("data") or {}).get("status") == "accepted",
    http=st,
    status=(accepted.get("data") or {}).get("status"),
)

st, started = http("POST", "/api/v2/operations/tasks/%s/start/" % task_id, token=ibrahim_token, body={})
check(
    "ibrahim_start",
    ok_success(st, started) and (started.get("data") or {}).get("status") == "in_progress",
    http=st,
    status=(started.get("data") or {}).get("status"),
)

idem_key = "e2e-vax-%s" % task_id
next_due = (date.today() + timedelta(days=30)).isoformat()
complete_body = {
    "vaccine_name": "Ibrahim-CBPP",
    "date_given": date.today().isoformat(),
    "next_due_date": next_due,
    "notes": "field complete",
    "client_request_id": idem_key,
}
st, completed = http(
    "POST",
    "/api/v2/operations/tasks/%s/complete/" % task_id,
    token=ibrahim_token,
    body=complete_body,
)
check(
    "ibrahim_complete",
    ok_success(st, completed) and (completed.get("data") or {}).get("status") == "completed",
    http=st,
    status=(completed.get("data") or {}).get("status"),
    result_id=(completed.get("data") or {}).get("result_reference_id"),
    error=completed.get("message") or completed.get("raw"),
)

st, replay = http(
    "POST",
    "/api/v2/operations/tasks/%s/complete/" % task_id,
    token=ibrahim_token,
    body=complete_body,
)
check(
    "idempotent_replay",
    ok_success(st, replay) and (replay.get("data") or {}).get("id") == task_id,
    http=st,
    status=(replay.get("data") or {}).get("status"),
)

vax_count = VaccinationRecord.objects.filter(animal=animal, vaccine_name="Ibrahim-CBPP").count()
check("one_vaccination_record", vax_count == 1, count=vax_count)

st, inbox2 = http("GET", "/api/v2/operations/my-work/", token=ibrahim_token)
ids2 = [row.get("id") for row in (inbox2.get("data") or [])]
check("completed_task_left_my_work", task_id not in ids2, ids=ids2)

follow = Task.objects.filter(parent_id=task_id, task_type=Task.Type.VACCINATION).first()
check("follow_up_task_created", follow is not None and follow.is_open, follow_id=getattr(follow, "id", None))

st, timeline = http("GET", "/api/v2/timeline/?animal_id=%s" % animal.id, token=owner_token)
titles = [row.get("event_title") for row in (timeline.get("data") or [])]
check(
    "timeline_has_vaccination_and_task",
    ok_success(st, timeline)
    and any("Ibrahim-CBPP" in (t or "") for t in titles)
    and any("completed" in (t or "").lower() for t in titles),
    titles=titles[:10],
)

st, me2 = http("GET", "/api/v2/users/me/", token=ibrahim_token)
open_after = ((me2.get("data") or {}).get("work_summary") or {}).get("open_tasks")
check(
    "work_summary_not_stuck_on_completed",
    ok_success(st, me2) and task_id not in ids2,
    open_before=open_before,
    open_after=open_after,
)

st, dash_after = http("GET", "/api/v2/dashboard/farm/%s/" % farm.id, token=owner_token)
farm_open_after = (((dash_after.get("data") or {}).get("tasks") or {}).get("open") or 0)
check(
    "farm_dashboard_open_tasks_sane",
    ok_success(st, dash_after) and farm_open_after >= 0,
    before=farm_open_before,
    after=farm_open_after,
)

st, legacy_vax = http("GET", "/api/health/vaccination/1/20/%s" % farm.id, token=owner_token)
names = [row.get("vaccine_name") for row in (legacy_vax.get("data") or [])]
check("legacy_lists_ibrahim_vaccination", ok_success(st, legacy_vax) and "Ibrahim-CBPP" in names, names=names)

st, profile = http("GET", "/api/v2/animals/%s/profile/" % animal.id, token=owner_token)
last_vax = (((profile.get("data") or {}).get("health") or {}).get("last_vaccination") or {})
check(
    "v2_profile_shows_vaccination",
    ok_success(st, profile) and last_vax.get("vaccine_name") == "Ibrahim-CBPP",
    last_vax=last_vax,
)

st, resolved = http("GET", "/api/v2/animals/resolve-tag/%s/" % tag, token=owner_token)
check("resolve_tag", ok_success(st, resolved) and (resolved.get("data") or {}).get("id") == animal.id, http=st)

# --- treatment ---
st, tcreated = http(
    "POST",
    "/api/v2/operations/tasks/",
    token=owner_token,
    body={
        "farm_id": farm.id,
        "task_type": "treatment",
        "title": "Ibrahim treatment",
        "animal_id": animal.id,
        "assignee_id": str(ibrahim.id),
    },
)
tid = (tcreated.get("data") or {}).get("id")
http("POST", "/api/v2/operations/tasks/%s/accept/" % tid, token=ibrahim_token, body={})
st, tdone = http(
    "POST",
    "/api/v2/operations/tasks/%s/complete/" % tid,
    token=ibrahim_token,
    body={"diagnosis": "fever", "treatment": "supportive", "severity": "mild", "treatment_date": date.today().isoformat()},
)
treat_count = TreatmentRecord.objects.filter(animal=animal, diagnosis="fever").count()
check("treatment_complete", ok_success(st, tdone) and treat_count == 1, http=st, count=treat_count, error=tdone.get("message"))

# --- feed stock deduct ---
stock_before = FeedInventory.objects.get(pk=inventory.pk).quantity_available
st, fcreated = http(
    "POST",
    "/api/v2/operations/tasks/",
    token=owner_token,
    body={
        "farm_id": farm.id,
        "task_type": "feed_issuance",
        "title": "Ibrahim feed",
        "animal_id": animal.id,
        "assignee_id": str(ibrahim.id),
    },
)
fid = (fcreated.get("data") or {}).get("id")
http("POST", "/api/v2/operations/tasks/%s/accept/" % fid, token=ibrahim_token, body={})
st, fdone = http(
    "POST",
    "/api/v2/operations/tasks/%s/complete/" % fid,
    token=ibrahim_token,
    body={
        "feed_inventory_id": inventory.id,
        "quantity_issued": 10,
        "target_type": "animal",
        "issue_date": date.today().isoformat(),
    },
)
stock_after = FeedInventory.objects.get(pk=inventory.pk).quantity_available
check(
    "feed_complete_deducts_stock",
    ok_success(st, fdone) and stock_after == stock_before - Decimal("10.00"),
    http=st,
    before=str(stock_before),
    after=str(stock_after),
    error=fdone.get("message") or fdone.get("raw"),
)

# --- observation / case ---
st, case_body = http(
    "POST",
    "/api/v2/health/cases/",
    token=ibrahim_token,
    body={"farm_id": farm.id, "animal_id": animal.id, "title": "Lameness case"},
)
case_id = (case_body.get("data") or {}).get("id")
check("open_health_case", ok_success(st, case_body) and case_id, http=st)
st, obs = http(
    "POST",
    "/api/v2/health/observations/",
    token=ibrahim_token,
    body={
        "farm_id": farm.id,
        "animal_id": animal.id,
        "case_id": case_id,
        "symptoms": "limping",
        "severity": "mild",
    },
)
check("record_observation", ok_success(st, obs) and HealthObservation.objects.filter(animal=animal).exists(), http=st)
st, closed = http(
    "POST",
    "/api/v2/health/cases/%s/close/" % case_id,
    token=ibrahim_token,
    body={"notes": "resolved"},
)
check("close_health_case", ok_success(st, closed) and (closed.get("data") or {}).get("status") == "closed", http=st)

# --- notifications ---
st, notes = http("GET", "/api/v2/notifications/", token=ibrahim_token)
check("ibrahim_notifications", ok_success(st, notes) and len(notes.get("data") or []) >= 1, http=st, count=len(notes.get("data") or []))
nid = (notes.get("data") or [{}])[0].get("id")
if nid:
    st, read = http("POST", "/api/v2/notifications/%s/read/" % nid, token=ibrahim_token, body={})
    check("mark_notification_read", ok_success(st, read) and (read.get("data") or {}).get("is_read") is True, http=st)

# --- search / dashboards / capabilities ---
st, search = http("GET", "/api/v2/search/?q=%s" % tag, token=owner_token)
animal_hits = [a.get("tag_id") for a in ((search.get("data") or {}).get("animals") or [])]
check("search_finds_tag", ok_success(st, search) and tag in animal_hits, hits=animal_hits)

st, caps = http("GET", "/api/v2/users/me/capabilities/", token=ibrahim_token)
nav = (caps.get("data") or {}).get("navigation") or {}
check("capabilities_my_work_true", ok_success(st, caps) and nav.get("my_work") is True, nav=nav)

st, org_dash = http("GET", "/api/v2/dashboard/organization/", token=owner_token)
check("org_dashboard", ok_success(st, org_dash), http=st)
st, mydash = http("GET", "/api/v2/dashboard/my-work/", token=ibrahim_token)
check("my_work_dashboard", ok_success(st, mydash), http=st)

# --- all authenticated v2 GET routes from OpenAPI ---
skip = {"/api/v2/"}
v2_get_failures = []
for path, ops in (http("GET", "/api/v2/openapi.json")[1].get("paths") or {}).items():
    if "get" not in ops:
        continue
    if path in skip:
        continue
    filled = (
        path.replace("{organization_id}", str(org.id))
        .replace("{farm_id}", str(farm.id))
        .replace("{animal_id}", str(animal.id))
        .replace("{tag_id}", tag)
        .replace("{task_id}", str(task_id or 0))
        .replace("{schedule_id}", "1")
        .replace("{notification_id}", str(nid or 0))
        .replace("{case_id}", str(case_id or 0))
    )
    if "{" in filled:
        continue
    if filled.endswith("/search/"):
        filled = filled + "?q=E2E"
    st, body = http("GET", filled, token=owner_token)
    if st >= 500:
        v2_get_failures.append({"path": filled, "http": st})
check("v2_get_no_500s", len(v2_get_failures) == 0, failures=v2_get_failures)

# --- legacy still healthy after writes ---
st, legacy_after = http("GET", "/api/animals/animal-profile/v2/%s" % animal.id, token=owner_token)
check("legacy_profile_after_writes", ok_success(st, legacy_after), http=st)
st, body = http("GET", "/api/openapi.json")
check("dev_openapi_still_unified", st == 200 and len((body or {}).get("paths", {})) >= 290, count=len((body or {}).get("paths", {})))

failed = [r for r in results if not r["ok"]]
print(json.dumps({
    "checked": len(results),
    "passed": sum(1 for r in results if r["ok"]),
    "failed": len(failed),
    "failures": failed,
    "results": results,
}, default=str, indent=2))
