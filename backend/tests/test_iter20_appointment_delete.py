# Iteration 20: DELETE /api/appointments/{id} - success, notifications+audit, cross-tenant isolation, work_order guard, 404
import asyncio
import os
import re
import sys
import uuid

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
sys.path.insert(0, "/app/backend")
from tenant_context import OPERATIONAL_COLLECTIONS  # noqa: E402

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
_txt = open("/app/memory/test_credentials.md").read()
OWNER_PW = re.search(r"andrei\.melek@gmail\.com / (\S+)", _txt).group(1)
SUF = uuid.uuid4().hex[:6]
T1, B1 = f"TEMP-ad1-{SUF}", f"TEMP-adb1-{SUF}"
T2, B2 = f"TEMP-ad2-{SUF}", f"TEMP-adb2-{SUF}"
U1, U2 = f"temp_ad1_{SUF}@example.com", f"temp_ad2_{SUF}@example.com"
PW = "TempPass2026!"
TENANTS = [T1, T2]
LOOP = asyncio.new_event_loop()
_cli = None


def run(c):
    return LOOP.run_until_complete(c)


def rdb():
    global _cli
    if _cli is None:
        asyncio.set_event_loop(LOOP)
        _cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return _cli[os.environ["DB_NAME"]]


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="module")
def env():
    owner = login("andrei.melek@gmail.com", OWNER_PW)
    db = rdb()
    for t in TENANTS:
        run(db.tenants.insert_one({"_id": t, "company_name": f"TEMP {t}", "cui": f"CUI-{t}", "subscription_plan": "FULL",
                                   "max_branches_allowed": 2, "status": "ACTIVE"}))
    for t, b, u in ((T1, B1, U1), (T2, B2, U2)):
        r = owner.post(f"{BASE}/platform/tenants/{t}/branches", json={"branch_id": b, "branch_name": f"TEMP {b}"})
        assert r.status_code == 200, r.text
        r = owner.post(f"{BASE}/platform/tenants/{t}/admins", json={"email": u, "name": "TEMP AD", "password": PW, "branch_ids": [b]})
        assert r.status_code == 200, r.text
    yield
    for c in run(db.list_collection_names()):
        if c in OPERATIONAL_COLLECTIONS:
            run(db[c].delete_many({"tenant_id": {"$in": TENANTS}}))
    run(db.users.delete_many({"email": {"$regex": f"_{SUF}@example.com$"}}))
    run(db.branches.delete_many({"tenant_id": {"$in": TENANTS}}))
    run(db.tenants.delete_many({"_id": {"$in": TENANTS}}))
    run(db.login_attempts.delete_many({"identifier": {"$regex": SUF}}))
    run(db.audit_logs.delete_many({"user_email": {"$regex": f"_{SUF}@example.com$"}}))
    run(db.counters.delete_many({"_id": {"$regex": "^TEMP-"}}))


@pytest.fixture(scope="module")
def a1(env):
    return login(U1, PW)


@pytest.fixture(scope="module")
def a2(env):
    return login(U2, PW)


@pytest.fixture(scope="module")
def cv(a1):
    c = a1.post(f"{BASE}/clients", json={"name": f"TEMP AD Client {SUF}", "phone": "0700000111", "email": "temp_ad@example.com"})
    assert c.status_code == 200, c.text
    cid = c.json()["id"]
    v = a1.post(f"{BASE}/vehicles", json={"client_id": cid, "vin": f"TMPAD{SUF.upper()}0000000"[:17], "plate": f"TAD{SUF[:3]}",
                                          "make": "Test", "model": "AD", "mileage": 100})
    assert v.status_code == 200, v.text
    return cid, v.json()["id"]


def mk_appt(s, cv, hour, title):
    cid, vid = cv
    r = s.post(f"{BASE}/appointments", json={"client_id": cid, "vehicle_id": vid, "title": title,
                                              "starts_at": f"2030-03-0{hour % 9 + 1}T{hour:02d}:00:00Z",
                                              "ends_at": f"2030-03-0{hour % 9 + 1}T{hour + 1:02d}:00:00Z"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_delete_success_removes_notifications_and_audits(a1, cv):
    aid = mk_appt(a1, cv, 8, f"TEMP del {SUF}")
    db = rdb()
    assert run(db.notifications.count_documents({"appointment_id": aid, "tenant_id": T1})) == 1
    r = a1.delete(f"{BASE}/appointments/{aid}")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}
    assert run(db.appointments.find_one({"_id": ObjectId(aid)})) is None
    assert run(db.notifications.count_documents({"appointment_id": aid})) == 0
    audit = run(db.audit_logs.find_one({"action": "delete_appointment", "entity_id": aid}))
    assert audit and audit["tenant_id"] == T1 and audit["branch_id"] == B1 and audit["detail"] == f"TEMP del {SUF}"
    lst = a1.get(f"{BASE}/appointments", params={"start": "2030-03-01T00:00:00Z", "end": "2030-03-31T00:00:00Z"})
    assert lst.status_code == 200 and aid not in [a["id"] for a in lst.json()]
    # second delete -> 404
    assert a1.delete(f"{BASE}/appointments/{aid}").status_code == 404


def test_cross_tenant_delete_blocked(a1, a2, cv):
    aid = mk_appt(a1, cv, 10, f"TEMP xt {SUF}")
    r = a2.delete(f"{BASE}/appointments/{aid}")
    assert r.status_code == 404, r.text
    db = rdb()
    assert run(db.appointments.find_one({"_id": ObjectId(aid)})) is not None
    assert run(db.notifications.count_documents({"appointment_id": aid})) == 1
    assert a1.delete(f"{BASE}/appointments/{aid}").status_code == 200


def test_delete_with_work_order_blocked(a1, cv):
    aid = mk_appt(a1, cv, 12, f"TEMP wo {SUF}")
    db = rdb()
    run(db.appointments.update_one({"_id": ObjectId(aid)}, {"$set": {"work_order_id": "TEMPWOID"}}))
    r = a1.delete(f"{BASE}/appointments/{aid}")
    assert r.status_code == 400, r.text
    assert "comandă" in r.json().get("detail", "")
    assert run(db.appointments.find_one({"_id": ObjectId(aid)})) is not None
    assert run(db.notifications.count_documents({"appointment_id": aid})) == 1
    assert run(db.audit_logs.count_documents({"action": "delete_appointment", "entity_id": aid})) == 0


def test_delete_invalid_id_and_unauth(a1):
    r = a1.delete(f"{BASE}/appointments/notanid")
    assert r.status_code in (400, 404, 422), r.text
    assert requests.delete(f"{BASE}/appointments/{ObjectId()}").status_code == 401
