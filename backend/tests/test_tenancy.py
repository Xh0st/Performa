# Tenancy P0 retest: per-branch singletons, per-branch counters, cross-tenant CRUD/aggregation fail-closed,
# quotas, branch switch, SUPERADMIN protection, multi-branch cron, suspended tenant, OAuth callback scope.
import asyncio
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
sys.path.insert(0, "/app/backend")
from core import hash_password  # noqa: E402
from tenant_context import OPERATIONAL_COLLECTIONS  # noqa: E402

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
SECRET = os.environ["WEBHOOK_CRON_SECRET"]
TXT = open("/app/memory/test_credentials.md").read()
OWNER_PW = re.search(r"andrei\.melek@gmail\.com / (\S+)", TXT).group(1)
ADMIN_PW = re.search(r"admin@serviceauto\.ro / (\S+)", TXT).group(1)
SUF = uuid.uuid4().hex[:6]
T1, B1 = f"TEST-q1-{SUF}", f"TEST-q1-b-{SUF}"
T2, B2A, B2B = f"TEST-q2-{SUF}", f"TEST-q2-ba-{SUF}", f"TEST-q2-bb-{SUF}"
U1, U2, UV = f"test_q1_{SUF}@example.com", f"test_q2_{SUF}@example.com", f"test_victim_{SUF}@example.com"
PW = "TestPass2026!"
TENANTS = [T1, T2]
STATE = {}


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def rdb():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


def switch(s, branch):
    r = s.post(f"{BASE}/auth/active-branch", json={"branch_id": branch})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"


@pytest.fixture(scope="module")
def owner():
    return login("andrei.melek@gmail.com", OWNER_PW)


@pytest.fixture(scope="module")
def demo_admin():
    return login("admin@serviceauto.ro", ADMIN_PW)


@pytest.fixture(scope="module")
def env(owner):
    db = rdb()
    counters_before = {c["_id"]: c["seq"] for c in run(db.counters.find().to_list(500))}
    notif_before = [n["_id"] for n in run(db.notifications.find({}, {"_id": 1}).to_list(5000))]
    for t, q in ((T1, 1), (T2, 2)):
        r = owner.post(f"{BASE}/platform/tenants", json={"tenant_id": t, "company_name": f"TEST {t}", "max_branches_allowed": q})
        assert r.status_code == 200, r.text
    for t, b in ((T1, B1), (T2, B2A), (T2, B2B)):
        r = owner.post(f"{BASE}/platform/tenants/{t}/branches", json={"branch_id": b, "branch_name": f"TEST {b}"})
        assert r.status_code == 200, r.text
    h = hash_password(PW)
    run(db.users.insert_many([
        {"email": U1, "name": "TEST Q1", "role": "admin", "active": True, "password_hash": h, "tenant_id": T1,
         "assigned_branch_ids": [B1], "active_branch_id": B1},
        {"email": UV, "name": "TEST Victim", "role": "admin", "active": True, "password_hash": h, "platform_role": "SUPERADMIN",
         "tenant_id": T1, "assigned_branch_ids": [B1], "active_branch_id": B1},
        {"email": U2, "name": "TEST Q2", "role": "admin", "active": True, "password_hash": h, "tenant_id": T2,
         "assigned_branch_ids": [B2A, B2B], "active_branch_id": B2A},
    ]))
    yield
    names = run(db.list_collection_names())
    for c in names:
        if c in OPERATIONAL_COLLECTIONS:
            run(db[c].delete_many({"tenant_id": {"$in": TENANTS}}))
    run(db.notifications.delete_many({"_id": {"$nin": notif_before}}))
    run(db.users.delete_many({"email": {"$in": [U1, U2, UV]}}))
    run(db.branches.delete_many({"tenant_id": {"$in": TENANTS}}))
    run(db.tenants.delete_many({"_id": {"$in": TENANTS}}))
    run(db.login_attempts.delete_many({"identifier": {"$regex": SUF}}))
    run(db.audit_logs.delete_many({"user_email": {"$regex": SUF}}))
    for k, v in counters_before.items():
        run(db.counters.update_one({"_id": k}, {"$set": {"seq": v}}))
    run(db.counters.delete_many({"_id": {"$nin": list(counters_before)}}))
    run(db.cron_runs.delete_many({"_id": {"$regex": SUF}}))


@pytest.fixture(scope="module")
def q1(env):
    return login(U1, PW)


@pytest.fixture(scope="module")
def q2(env):
    return login(U2, PW)


def mk_wo(s, tag):
    c = s.post(f"{BASE}/clients", json={"type": "pf", "name": f"TEST {tag} {SUF}", "email": f"c_{tag}_{SUF}@example.com"})
    assert c.status_code == 200, c.text
    vin = (f"TST{tag}{SUF}".upper().replace("-", "") + "0" * 17)[:17]
    v = s.post(f"{BASE}/vehicles", json={"client_id": c.json()["id"], "vin": vin, "plate": f"TS{tag[:4]}", "make": "Dacia", "model": "Logan"})
    assert v.status_code == 200, v.text
    w = s.post(f"{BASE}/work-orders", json={"client_id": c.json()["id"], "vehicle_id": v.json()["id"], "mileage_in": 1000,
                                           "complaint": "TEST", "photos": {}, "signature": "data:image/png;base64,TEST"})
    assert w.status_code == 200, w.text
    return c.json()["id"], v.json()["id"], w.json()


# ---- Quotas ----
def test_quota_limits(owner, env):
    r = owner.post(f"{BASE}/platform/tenants/{T1}/branches", json={"branch_id": f"TEST-q1-x-{SUF}", "branch_name": "TEST X"})
    assert r.status_code == 403 and "limita" in r.json()["detail"].lower()
    r = owner.post(f"{BASE}/platform/tenants/{T2}/branches", json={"branch_id": f"TEST-q2-x-{SUF}", "branch_name": "TEST X"})
    assert r.status_code == 403


# ---- Per-branch singletons ----
def test_singletons_per_branch(q2):
    switch(q2, B2A)
    assert q2.put(f"{BASE}/settings", json={"name": f"TEST CoA {SUF}", "series_invoice": "TSA"}).status_code == 200
    r = q2.put(f"{BASE}/rar-autopass/config", json={"branch_name": "TEST A", "authorization_code": "AUTH-A", "service_cui": "RO1", "environment": "test"})
    assert r.status_code == 200, r.text
    r = q2.put(f"{BASE}/efactura/config", json={"environment": "test", "client_id": "TEST-CID-A"})
    assert r.status_code == 200, r.text
    switch(q2, B2B)
    assert (q2.get(f"{BASE}/settings").json().get("name") or "") == ""
    assert q2.get(f"{BASE}/efactura/config").json()["environment"] == "simulare"
    assert q2.get(f"{BASE}/rar-autopass/config").json().get("authorization_code", "") in ("", None)
    assert q2.put(f"{BASE}/settings", json={"name": f"TEST CoB {SUF}"}).status_code == 200
    r = q2.put(f"{BASE}/rar-autopass/config", json={"branch_name": "TEST B", "authorization_code": "AUTH-B", "service_cui": "RO2", "environment": "test"})
    assert r.status_code == 200, r.text
    assert q2.put(f"{BASE}/efactura/config", json={"environment": "simulare", "client_id": "TEST-CID-B"}).status_code == 200
    switch(q2, B2A)
    assert q2.get(f"{BASE}/settings").json()["name"] == f"TEST CoA {SUF}"
    assert q2.get(f"{BASE}/efactura/config").json()["environment"] == "test"
    db = rdb()
    for coll in ("settings", "rar_autopass_config", "efactura_config"):
        docs = run(db[coll].find({"tenant_id": T2}).to_list(10))
        assert sorted(d["branch_id"] for d in docs) == sorted([B2A, B2B]), f"{coll}: {[(d['_id'], d.get('branch_id')) for d in docs]}"
    demo = run(db.settings.find_one({"tenant_id": "demo-tenant-001", "kind": "company"}))
    assert demo and f"TEST" not in (demo.get("name") or "")


# ---- Per tenant+branch counters ----
def test_counters_per_branch(q1, q2, owner):
    db = rdb()
    demo_before = run(db.counters.find_one({"_id": "demo-tenant-001:demo-branch-001:work_order"}))["seq"]
    _, _, w1 = mk_wo(q1, "q1")
    switch(q2, B2A)
    ca, va, wa = mk_wo(q2, "ba")
    switch(q2, B2B)
    cb, vb, wb = mk_wo(q2, "bb")
    STATE.update(q2a=(ca, va, wa["id"]), q2b=(cb, vb, wb["id"]), q1_wo=w1["id"])
    for w in (w1, wa, wb):
        assert w["number"].endswith("00001"), w["number"]
    assert run(db.counters.find_one({"_id": "demo-tenant-001:demo-branch-001:work_order"}))["seq"] == demo_before
    for t, b in ((T1, B1), (T2, B2A), (T2, B2B)):
        assert run(db.counters.find_one({"_id": f"{t}:{b}:work_order"}))["seq"] == 1
    # same VIN reusable in another tenant (compound index)
    demo_vin = run(db.vehicles.find_one({"tenant_id": "demo-tenant-001"}))["vin"]
    cid = q1.get(f"{BASE}/clients").json()[0]["id"]
    r = q1.post(f"{BASE}/vehicles", json={"client_id": cid, "vin": demo_vin, "plate": "TSTVIN", "make": "Dacia", "model": "Logan"})
    assert r.status_code == 200, r.text
    demo_code = run(db.products.find_one({"tenant_id": "demo-tenant-001"}))["code"]
    r = q1.post(f"{BASE}/products", json={"code": demo_code, "name": f"TEST prod {SUF}"})
    assert r.status_code == 200, r.text
    STATE["q1_product"] = r.json()["id"]
    r = q1.post(f"{BASE}/products", json={"code": demo_code, "name": f"TEST dup {SUF}"})
    assert r.status_code in (400, 409), f"dup code in same branch -> {r.status_code} {r.text[:150]}"


# ---- Cross-tenant CRUD by id ----
def test_cross_tenant_by_id_fail_closed(q1):
    db = rdb()
    demo = {c: str(run(db[c].find_one({"tenant_id": "demo-tenant-001"}))["_id"])
            for c in ("clients", "vehicles", "work_orders", "invoices", "products", "appointments", "warranty_claims", "payments", "nirs")}
    checks = [("get", f"/clients/{demo['clients']}"), ("put", f"/clients/{demo['clients']}"), ("delete", f"/clients/{demo['clients']}"),
              ("get", f"/vehicles/{demo['vehicles']}"), ("put", f"/vehicles/{demo['vehicles']}"),
              ("get", f"/work-orders/{demo['work_orders']}"), ("put", f"/work-orders/{demo['work_orders']}"),
              ("get", f"/invoices/{demo['invoices']}"), ("post", f"/invoices/{demo['invoices']}/storno"),
              ("put", f"/products/{demo['products']}"), ("get", f"/products/{demo['products']}/moves"),
              ("put", f"/appointments/{demo['appointments']}"), ("put", f"/warranty-claims/{demo['warranty_claims']}"),
              ("get", f"/payments/{demo['payments']}"), ("get", f"/nirs/{demo['nirs']}"),
              ("get", f"/warranties/invoices/{demo['invoices']}"), ("post", f"/invoices/from-work-order/{demo['work_orders']}")]
    before = {c: run(db[c].find_one({"_id": __import__("bson").ObjectId(i)})) for c, i in demo.items()}
    bad = []
    for m, p in checks:
        r = getattr(q1, m)(f"{BASE}{p}", json={} if m in ("put", "post") else None)
        if r.status_code not in (403, 404, 422) or (r.status_code == 422 and m == "get"):
            bad.append((m, p, r.status_code, r.text[:80]))
        # 422 for PUT/POST is validation-before-lookup; verify data untouched below
    for c, i in demo.items():
        after = run(db[c].find_one({"_id": __import__("bson").ObjectId(i)}))
        assert after == before[c], f"demo {c} modified"
    assert not bad, bad


def test_cross_tenant_lists_aggregates_empty(q1):
    for ep in ["/clients", "/vehicles", "/work-orders", "/invoices", "/payments", "/suppliers", "/nirs", "/supplier-returns",
               "/mechanics", "/warranties", "/warranty-claims", "/efactura/inbox", "/efactura/logs", "/rar-autopass/outbox",
               "/rar-autopass/logs", "/closure-exceptions/work-orders", "/ai/history",
               "/appointments?start=2020-01-01T00:00:00%2B00:00&end=2030-01-01T00:00:00%2B00:00"]:
        r = q1.get(f"{BASE}{ep}")
        assert r.status_code == 200, f"{ep} {r.status_code} {r.text[:120]}"
        data = r.json()
        items = data if isinstance(data, list) else data.get("items", data.get("rows", []))
        leaked = [x for x in items if isinstance(x, dict) and ("demo" in str(x.get("tenant_id", "")) or x.get("tenant_id") not in (None, T1))]
        names = [x.get("name", "") or x.get("client_name", "") for x in items if isinstance(x, dict)]
        assert not leaked and all(("TEST" in n or n == "") for n in names), f"{ep} leaked {names[:3]}"
    d = q1.get(f"{BASE}/dashboard").json()
    rep = q1.get(f"{BASE}/reports/final-inspections?start=2020-01-01&end=2030-12-31")
    assert rep.status_code == 200
    cash = q1.get(f"{BASE}/cash-register")
    assert cash.status_code == 200, cash.text[:200]
    exp = q1.get(f"{BASE}/expirations")
    assert exp.status_code == 200
    STATE["dash"] = d


def test_cross_branch_same_tenant(q2):
    switch(q2, B2B)
    ca, va, wa = STATE["q2a"]
    for p in (f"/clients/{ca}", f"/vehicles/{va}", f"/work-orders/{wa}"):
        assert q2.get(f"{BASE}{p}").status_code == 404, p
    names = [c["name"] for c in q2.get(f"{BASE}/clients").json()]
    assert names == [f"TEST bb {SUF}"], names
    switch(q2, B2A)
    names = [c["name"] for c in q2.get(f"{BASE}/clients").json()]
    assert names == [f"TEST ba {SUF}"], names


# ---- SUPERADMIN protection / platform RBAC ----
def test_superadmin_protection(q1, demo_admin):
    db = rdb()
    victim = run(db.users.find_one({"email": UV}))
    r = q1.put(f"{BASE}/users/{victim['_id']}", json={"email": UV, "name": "x", "role": "admin", "password": "Escalated2026!"})
    assert r.status_code == 403, r.text
    r = q1.delete(f"{BASE}/users/{victim['_id']}")
    assert r.status_code == 403, r.text
    assert run(db.users.find_one({"email": UV}))["password_hash"] == victim["password_hash"]
    owner_doc = run(db.users.find_one({"email": "andrei.melek@gmail.com"}))
    # no-op payload so nothing changes even on failure
    r = demo_admin.put(f"{BASE}/users/{owner_doc['_id']}", json={"email": owner_doc["email"], "name": owner_doc["name"],
                                                                 "role": owner_doc["role"], "active": owner_doc.get("active", True)})
    assert r.status_code == 403, r.text
    # cross-tenant user mgmt
    assert q1.put(f"{BASE}/users/{owner_doc['_id']}", json={"email": "x@x.ro", "name": "x", "role": "admin"}).status_code == 404
    assert q1.delete(f"{BASE}/users/{owner_doc['_id']}").status_code == 404
    for s in (q1, demo_admin):
        assert s.get(f"{BASE}/platform/tenants").status_code == 403
        assert s.get(f"{BASE}/platform/tenants/{T1}/branches").status_code == 403
        assert s.put(f"{BASE}/platform/tenants/{T1}", json={"subscription_plan": "PRO", "max_branches_allowed": 9, "status": "ACTIVE"}).status_code == 403
    assert run(db.tenants.find_one({"_id": T1}))["max_branches_allowed"] == 1


# ---- Cron multi-branch ----
def test_cron_multi_branch(q2):
    start = (datetime.now(timezone.utc) + timedelta(hours=24)).replace(microsecond=0)
    for b, key in ((B2A, "q2a"), (B2B, "q2b")):
        switch(q2, b)
        cid, vid, _ = STATE[key]
        r = q2.post(f"{BASE}/appointments", json={"client_id": cid, "vehicle_id": vid, "starts_at": start.isoformat(),
                                                  "ends_at": (start + timedelta(hours=1)).isoformat(), "title": f"TEST appt {b}"})
        assert r.status_code == 200, r.text
    hdr = {"Authorization": f"Bearer {SECRET}"}
    logf = max(["/var/log/supervisor/" + f for f in os.listdir("/var/log/supervisor") if f.startswith("backend") and "err" in f], key=os.path.getmtime)
    log_pos = os.path.getsize(logf)
    assert requests.post(f"{BASE}/cron/appointments/reminders").status_code == 401
    t0 = time.time()
    r = requests.post(f"{BASE}/cron/appointments/reminders", headers={**hdr, "X-Webhook-Id": f"TEST-rem-{SUF}"})
    assert r.status_code == 200 and time.time() - t0 < 5, r.text
    for job in ("tokens", "status", "inbox"):
        r = requests.post(f"{BASE}/cron/efactura/{job}", headers={**hdr, "X-Webhook-Id": f"TEST-ef-{job}-{SUF}"})
        assert r.status_code == 200, f"{job} {r.text}"
    dup = requests.post(f"{BASE}/cron/efactura/tokens", headers={**hdr, "X-Webhook-Id": f"TEST-ef-tokens-{SUF}"})
    assert dup.json().get("duplicate") is True
    time.sleep(4)
    db = rdb()
    got = {n["branch_id"] for n in run(db.notifications.find({"tenant_id": T2, "kind": "appointment_reminder"}).to_list(10))}
    assert got == {B2A, B2B}, got
    with open(logf) as fh:
        fh.seek(log_pos)
        new_log = fh.read()
    assert "Context tenant lips" not in new_log and "Traceback" not in new_log, new_log[-1500:]


# ---- Suspended tenant ----
def test_suspended_tenant_blocked(owner, env):
    s = login(U1, PW)
    r = owner.put(f"{BASE}/platform/tenants/{T1}", json={"subscription_plan": "BASIC", "max_branches_allowed": 1, "status": "SUSPENDED"})
    assert r.status_code == 200
    try:
        code_existing = s.get(f"{BASE}/clients").status_code
        code_login = requests.post(f"{BASE}/auth/login", json={"email": U1, "password": PW}).status_code
    finally:
        owner.put(f"{BASE}/platform/tenants/{T1}", json={"subscription_plan": "BASIC", "max_branches_allowed": 1, "status": "ACTIVE"})
    assert code_existing in (401, 403) and code_login in (401, 403), f"suspended tenant still has access: token={code_existing} login={code_login}"


# ---- OAuth callback (unauthenticated ANAF redirect) ----
def test_efactura_oauth_callback_has_scope():
    r = requests.get(f"{BASE}/efactura/oauth/callback?code=x&state=invalid", allow_redirects=False)
    assert r.status_code in (302, 307), f"callback -> {r.status_code} {r.text[:120]}"
