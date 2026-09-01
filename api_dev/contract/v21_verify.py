"""v2.1 verification. python manage.py shell < contract/v21_verify.py"""
import json
from datetime import date, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.utils import timezone

from account.models import EmailValidation, User
from account.utils.jwt_utils import create_access_token
from animals.models import Animal, AnimalWeight
from health.models import HealthCase, HealthObservation, MortalityRecord
from operations.models import Task, TaskSchedule
from organization.models import Organization
from reproduction.models import PregnancyRecord
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
            parsed = json.loads(resp.read().decode() or "{}")
            return resp.status, parsed
    except HTTPError as exc:
        try:
            parsed = json.loads(exc.read().decode() or "{}")
        except Exception:
            parsed = {}
        return exc.code, parsed


def ok(status, body):
    return status == 200 and body.get("success") is True


owner = User.objects.filter(email="e2e.owner@farmos.test").first()
ibrahim = User.objects.filter(email="e2e.ibrahim@farmos.test").first()
if not owner:
    raise SystemExit("e2e owner missing; run e2e_run.py first or seed users")
org = owner.organization
farm = org.farms.first()
animal = Animal.objects.filter(farm=farm, status="active").order_by("-id").first()
owner_token = create_access_token({"sub": str(owner.id)})
ibrahim_token = create_access_token({"sub": str(ibrahim.id)}) if ibrahim else owner_token
run_id = timezone.now().strftime("%H%M%S")

st, body = http("GET", "/api/v2/registry/", token=owner_token)
entries = (body.get("data") or {}).get("entries") or []
check("registry", ok(st, body) and len(entries) >= 20, http=st, n=len(entries))

st, body = http("GET", "/api/v2/", token=owner_token)
check("contract_version_2_2", ok(st, body) and "2.2" in str((body.get("data") or {}).get("contract")), http=st)

st, body = http("GET", "/api/v2/animals/?page=1&page_size=5", token=owner_token)
data = body.get("data") or []
check("animal_list", ok(st, body) and isinstance(data, list), http=st, n=len(data))
if data:
    card = data[0]
    check("animal_list_card_shape", all(k in card for k in ("id", "tag_id", "flags", "lifecycle_status")), card_keys=list(card))

if animal:
    st, body = http(
        "PATCH",
        "/api/v2/animals/%s/" % animal.id,
        token=owner_token,
        body={"notes": "v21 verify note"},
    )
    check("animal_patch", ok(st, body) and ((body.get("data") or {}).get("overview") or {}).get("farm_id") == farm.id, http=st)

    st, body = http(
        "POST",
        "/api/v2/animals/",
        token=owner_token,
        body={
            "farm_id": farm.id,
            "tag_id": None,
            "gender": "female",
            "source_type": "opening_record",
            "status": "active",
            "notes": "untagged opening",
            "client_request_id": "v21-untagged-%s" % run_id,
        },
    )
    check("untagged_create", ok(st, body) and (body.get("data") or {}).get("id"), http=st, code=body.get("code"))

    st, body = http("GET", "/api/v2/users/%s/" % owner.id, token=owner_token)
    check("user_profile", ok(st, body) and (body.get("data") or {}).get("display_name"), http=st)

    st, body = http("GET", "/api/v2/users/", token=owner_token)
    check("people_list", ok(st, body) and isinstance(body.get("data"), list), http=st)

    st, body = http("GET", "/api/v2/roles/", token=owner_token)
    check("roles_list", ok(st, body), http=st)
    st, body = http("GET", "/api/v2/permissions/", token=owner_token)
    check("permissions_list", ok(st, body), http=st)

    st, body = http("GET", "/api/v2/notifications/unread-count/", token=owner_token)
    check("unread_count", ok(st, body) and "count" in (body.get("data") or {}), http=st, count=(body.get("data") or {}).get("count"))

    st, body = http("GET", "/api/v2/dashboard/organization/", token=owner_token)
    dash = body.get("data") or {}
    check("org_dash_ops", ok(st, body) and "operations" in dash and "attention" in dash, http=st, keys=list(dash))

    st, body = http("GET", "/api/v2/dashboard/farm/%s/" % farm.id, token=owner_token)
    check("farm_dash_today", ok(st, body) and "today" in (body.get("data") or {}), http=st)

    st, body = http("GET", "/api/v2/dashboard/health/", token=owner_token)
    check("health_dash", ok(st, body) and "active_health_cases" in (body.get("data") or {}), http=st)

    st, body = http(
        "POST",
        "/api/v2/health/observations/",
        token=owner_token,
        body={
            "farm_id": farm.id,
            "animal_id": animal.id,
            "symptoms": "Standalone verify observation",
            "severity": "mild",
            "create_case": False,
            "client_request_id": "v21-obs-standalone-%s" % run_id,
        },
    )
    obs = body.get("data") or {}
    check("observation_no_auto_case", ok(st, body) and obs.get("case_id") in (None, ""), http=st, case_id=obs.get("case_id"))

    st, body = http(
        "POST",
        "/api/v2/health/observations/",
        token=owner_token,
        body={
            "farm_id": farm.id,
            "animal_id": animal.id,
            "symptoms": "Create case observation",
            "severity": "moderate",
            "create_case": True,
            "client_request_id": "v21-obs-case-%s" % run_id,
        },
    )
    obs = body.get("data") or {}
    check("observation_create_case", ok(st, body) and obs.get("case_id"), http=st, case_id=obs.get("case_id"))
    case_id = obs.get("case_id")
    if case_id:
        st, body = http("GET", "/api/v2/health/cases/%s/" % case_id, token=owner_token)
        detail = body.get("data") or {}
        check("case_detail", ok(st, body) and "observations" in detail and "treatments" in detail, http=st)

    # weight task
    st, body = http(
        "POST",
        "/api/v2/operations/tasks/",
        token=owner_token,
        body={
            "farm_id": farm.id,
            "task_type": "weight",
            "title": "Weigh verify",
            "animal_id": animal.id,
            "assignee_id": str(owner.id),
            "client_request_id": "v21-weight-task-%s" % run_id,
        },
    )
    task_id = (body.get("data") or {}).get("id")
    check("weight_task_create", ok(st, body) and task_id, http=st)
    if task_id:
        st, body = http(
            "POST",
            "/api/v2/operations/tasks/%s/complete/" % task_id,
            token=owner_token,
            body={"weight": 356, "unit": "kg", "client_request_id": "v21-weight-complete-%s" % run_id},
        )
        check("weight_complete", ok(st, body) and (body.get("data") or {}).get("result"), http=st)
        check("weight_record", AnimalWeight.objects.filter(animal=animal, weight=356).exists())

    # unable + reopen
    st, body = http(
        "POST",
        "/api/v2/operations/tasks/",
        token=owner_token,
        body={
            "farm_id": farm.id,
            "task_type": "generic",
            "title": "Unable verify",
            "animal_id": animal.id,
            "assignee_id": str(owner.id),
            "client_request_id": "v21-unable-task-%s" % run_id,
        },
    )
    unable_id = (body.get("data") or {}).get("id")
    if unable_id:
        st, body = http(
            "POST",
            "/api/v2/operations/tasks/%s/unable-to-complete/" % unable_id,
            token=owner_token,
            body={"reason_code": "animal_unavailable", "notes": "moved", "client_request_id": "v21-unable-%s" % run_id},
        )
        check(
            "unable_to_complete",
            ok(st, body) and (body.get("data") or {}).get("status") == "unable_to_complete",
            http=st,
            status=(body.get("data") or {}).get("status"),
        )
        st, body = http(
            "POST",
            "/api/v2/operations/tasks/%s/reopen/" % unable_id,
            token=owner_token,
            body={"reason": "returned", "assignee_id": str(owner.id)},
        )
        check("reopen_task", ok(st, body) and (body.get("data") or {}).get("status") in ("assigned", "draft"), http=st)

    # pregnancy check — use a female that is not already pregnant
    preg_animal = (
        Animal.objects.filter(farm=farm, gender="female", status="active", is_pregnant=False)
        .exclude(id=animal.id)
        .first()
    )
    if not preg_animal:
        preg_animal = Animal(
            user=owner,
            farm=farm,
            tag_id="V21-PREG-%s" % run_id,
            gender="female",
            source_type="opening_record",
            status="active",
            is_pregnant=False,
            estimated_age_months=24,
        )
        preg_animal.save()
    st, body = http(
        "POST",
        "/api/v2/operations/tasks/",
        token=owner_token,
        body={
            "farm_id": farm.id,
            "task_type": "pregnancy_check",
            "title": "Preg check verify",
            "animal_id": preg_animal.id,
            "assignee_id": str(owner.id),
            "client_request_id": "v21-preg-task-%s" % run_id,
        },
    )
    preg_id = (body.get("data") or {}).get("id")
    if preg_id:
        st, body = http(
            "POST",
            "/api/v2/operations/tasks/%s/complete/" % preg_id,
            token=owner_token,
            body={
                "result": "pregnant",
                "expected_delivery_date": str(date.today() + timedelta(days=180)),
                "client_request_id": "v21-preg-complete-%s" % run_id,
            },
        )
        check("pregnancy_complete", ok(st, body), http=st, message=body.get("message"), errors=body.get("errors"))
        check("pregnancy_record", PregnancyRecord.objects.filter(animal=preg_animal, result="pregnant").exists())

    # schedule detail + deactivate
    schedule = TaskSchedule.objects.filter(organization=org).first()
    if not schedule:
        st, body = http(
            "POST",
            "/api/v2/operations/schedules/",
            token=owner_token,
            body={
                "farm_id": farm.id,
                "task_type": "observation",
                "title": "V21 schedule %s" % run_id,
                "recurrence": "weekly",
                "next_run_at": timezone.now().isoformat(),
            },
        )
        check("schedule_create", ok(st, body) and (body.get("data") or {}).get("id"), http=st)
        schedule = TaskSchedule.objects.filter(organization=org).first()
    if schedule:
        st, body = http("GET", "/api/v2/operations/schedules/%s/" % schedule.id, token=owner_token)
        check("schedule_detail", ok(st, body), http=st)
        st, body = http(
            "POST",
            "/api/v2/operations/schedules/%s/deactivate/" % schedule.id,
            token=owner_token,
            body={},
        )
        check("schedule_deactivate", ok(st, body) and (body.get("data") or {}).get("is_active") is False, http=st)
        schedule.is_active = True
        schedule.save(update_fields=["is_active"])

    st, body = http("GET", "/api/v2/search/?q=%s" % (animal.tag_id or animal.id), token=owner_token)
    search = body.get("data") or {}
    check("search_rich_animal", ok(st, body) and (search.get("animals") or [{}])[0].get("farm"), http=st)

    st, body = http("GET", "/api/v2/health/alerts/", token=owner_token)
    check("health_alerts", ok(st, body), http=st)

failed = [r for r in results if not r["ok"]]
print(json.dumps({"checked": len(results), "passed": sum(1 for r in results if r["ok"]), "failed": len(failed), "failures": failed, "results": results}, default=str, indent=2))
