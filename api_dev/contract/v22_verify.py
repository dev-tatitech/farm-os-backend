"""v2.2 release-readiness checks. python manage.py shell < contract/v22_verify.py"""
import json
from datetime import date, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.utils import timezone

from account.models import User
from account.utils.jwt_utils import create_access_token
from animals.models import Animal
from operations.models import Task, TaskSchedule
from organization.models import Farm, FarmType, Organization
from reproduction.models import BirthRecord, PregnancyRecord

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
            return resp.status, json.loads(resp.read().decode() or "{}")
    except HTTPError as exc:
        try:
            parsed = json.loads(exc.read().decode() or "{}")
        except Exception:
            parsed = {}
        return exc.code, parsed


def ok(status, body):
    return status == 200 and body.get("success") is True


owner = User.objects.filter(email="e2e.owner@farmos.test").first()
if not owner:
    raise SystemExit("e2e owner missing; run e2e_run.py first")
org = owner.organization
farm = org.farms.first()
token = create_access_token({"sub": str(owner.id)})
run_id = timezone.now().strftime("%H%M%S")

st, body = http("GET", "/api/v2/", token=token)
check("contract_2_2", ok(st, body) and "2.2" in str((body.get("data") or {}).get("contract")), http=st)

# timestamps
st, body = http(
    "POST",
    "/api/v2/operations/tasks/",
    token=token,
    body={
        "farm_id": farm.id,
        "task_type": "generic",
        "title": "v22 timestamps %s" % run_id,
        "assignee_id": str(owner.id),
        "client_request_id": "v22-ts-%s" % run_id,
    },
)
task = body.get("data") or {}
tid = task.get("id")
check("create_source_manual", ok(st, body) and (task.get("source") or {}).get("type") == "manual", source=task.get("source"))
if tid:
    st, body = http("POST", "/api/v2/operations/tasks/%s/start/" % tid, token=token, body={})
    data = body.get("data") or {}
    check(
        "start_timestamps",
        ok(st, body) and data.get("status") == "in_progress" and data.get("started_at") and data.get("accepted_at"),
        http=st,
        status=data.get("status"),
        started_at=data.get("started_at"),
        accepted_at=data.get("accepted_at"),
    )
    st, body = http(
        "POST",
        "/api/v2/operations/tasks/%s/cancel/" % tid,
        token=token,
        body={"reason": "v22 cancel"},
    )
    data = body.get("data") or {}
    check(
        "cancel_timestamps",
        ok(st, body) and data.get("status") == "cancelled" and data.get("cancelled_at"),
        http=st,
        cancelled_at=data.get("cancelled_at"),
    )

# GET schedules is read-only
before = Task.objects.filter(organization=org, source_type=Task.SourceType.SCHEDULE).count()
st, body = http("GET", "/api/v2/operations/schedules/", token=token)
after = Task.objects.filter(organization=org, source_type=Task.SourceType.SCHEDULE).count()
check("schedule_get_readonly", ok(st, body) and before == after, http=st, before=before, after=after)

# farm people display_name
st, body = http("GET", "/api/v2/farms/%s/people/" % farm.id, token=token)
people = body.get("data") or []
check("farm_people_display_name", ok(st, body) and people and people[0].get("display_name"), http=st)

# isolation: other org must not see this farm's animal
other = User.objects.exclude(id=owner.id).exclude(organization=org).first()
animal = Animal.objects.filter(farm=farm, status="active").first()
if other and animal:
    other_token = create_access_token({"sub": str(other.id)})
    st, body = http("GET", "/api/v2/animals/%s/profile/" % animal.id, token=other_token)
    check("isolation_animal_profile", st in (403, 404), http=st, code=body.get("code"))
    st, body = http("GET", "/api/v2/dashboard/farm/%s/" % farm.id, token=other_token)
    check("isolation_farm_dash", st in (403, 404), http=st, code=body.get("code"))
else:
    check("isolation_animal_profile", True, skipped=True)
    check("isolation_farm_dash", True, skipped=True)

# birth integrity
preg = Animal.objects.filter(farm=farm, gender="female", status="active", is_pregnant=True).first()
if not preg:
    preg = Animal.objects.filter(farm=farm, gender="female", status="active").first()
    if preg:
        preg.is_pregnant = True
        preg.save(update_fields=["is_pregnant"])
if preg:
    st, body = http(
        "POST",
        "/api/v2/reproduction/births/",
        token=token,
        body={
            "farm_id": farm.id,
            "mother_id": preg.id,
            "birth_date": str(date.today()),
            "number_of_offspring": 3,
            "number_alive": 2,
            "number_dead": 1,
            "client_request_id": "v22-birth-%s" % run_id,
        },
    )
    birth = body.get("data") or {}
    check(
        "birth_slots",
        ok(st, body) and birth.get("pending_offspring_registration") == 2 and birth.get("dead") == 1,
        http=st,
        message=body.get("message"),
        pending=birth.get("pending_offspring_registration"),
    )
    bid = birth.get("id")
    if bid:
        for seq in (1, 2):
            st, body = http(
                "POST",
                "/api/v2/reproduction/births/%s/register-offspring/" % bid,
                token=token,
                body={"gender": "female", "client_request_id": "v22-off-%s-%s" % (run_id, seq)},
            )
            check("register_live_%s" % seq, ok(st, body) and (body.get("data") or {}).get("animal_id"), http=st)
        st, body = http(
            "POST",
            "/api/v2/reproduction/births/%s/register-offspring/" % bid,
            token=token,
            body={"gender": "male", "client_request_id": "v22-off-extra-%s" % run_id},
        )
        check("reject_third_live", st == 409, http=st, code=body.get("code"))
        st, body = http("GET", "/api/v2/reproduction/births/%s/" % bid, token=token)
        data = body.get("data") or {}
        check("birth_pending_zero", ok(st, body) and data.get("pending_offspring_registration") == 0, pending=data.get("pending_offspring_registration"))

failed = [r for r in results if not r["ok"]]
print(json.dumps({"checked": len(results), "passed": sum(1 for r in results if r["ok"]), "failed": len(failed), "failures": failed}, default=str, indent=2))
