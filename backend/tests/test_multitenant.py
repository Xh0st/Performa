# Multi-tenant Pool Model regression: migration, auth scope, isolation, quotas, branch switching, public quote, cleanup
import asyncio
import os
import re
import uuid
import sys

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


def _creds():
    txt = open("/app/memory/test_credentials.md").read()
    owner = re.search(r"andrei\.melek@gmail\.com / (\S+)", txt).group(1)
    admin = re.search(r"admin@serviceauto\.ro / (\S+)", txt).group(1)
    return owner, admin


OWNER_PW, ADMIN_PW = _creds()
SUF = uuid.uuid4().hex[:6]
T_A, B_A = f"TEST-tenant-a-{SUF}", f"TEST-branch-a-{SUF}"
T_B, B_B1, B_B2 = f"TEST-tenant-b-{SUF}", f"TEST-branch-b1-{SUF}", f"TEST-branch-b2-{SUF}"
USER_A = f"test_admin_a_{SUF}@example.com"
USER_B = f"test_multi_b_{SUF}@example.com"
USER_SA_VICTIM = f"test_sa_victim_{SUF}@example.com"
TEST_PW = "TestPass2026!"
TENANTS = [T_A, T_B]
TEST_IDS = []


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def rdb():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    s.login_response = r
    return s


@pytest.fixture(scope="module")
def owner():
    return login("andrei.melek@gmail.com", OWNER_PW)


@pytest.fixture(scope="module")
def demo_admin():
    return login("admin@serviceauto.ro", ADMIN_PW)


@pytest.fixture(scope="module")
def setup(owner):
    db = rdb()
    counters_before = {c["_id"]: c["seq"] for c in run(db.counters.find().to_list(100))}
    r = owner.post(f"{BASE}/platform/tenants", json={"tenant_id": T_A, "company_name": f"TEST Tenant A {SUF}", "max_branches_allowed": 1})
    assert r.status_code == 200, r.text
    r = owner.post(f"{BASE}/platform/tenants/{T_A}/branches", json={"branch_id": B_A, "branch_name": "TEST Branch A", "is_main_branch": True})
    assert r.status_code == 200, r.text
    r = owner.post(f"{BASE}/platform/tenants", json={"tenant_id": T_B, "company_name": f"TEST Tenant B {SUF}", "max_branches_allowed": 2})
    assert r.status_code == 200, r.text
    for b in (B_B1, B_B2):
        r = owner.post(f"{BASE}/platform/tenants/{T_B}/branches", json={"branch_id": b, "branch_name": f"TEST {b}"})
        assert r.status_code == 200, r.text
    # No API exists to create a tenant admin for a new tenant / assign multi-branch -> seed via DB
    h = hash_password(TEST_PW)
    run(db.users.insert_many([
        {"email": USER_A, "name": "TEST Admin A", "role": "admin", "active": True, "password_hash": h,
         "tenant_id": T_A, "assigned_branch_ids": [B_A], "active_branch_id": B_A},
        {"email": USER_SA_VICTIM, "name": "TEST SA victim", "role": "admin", "active": True, "password_hash": h,
         "platform_role": "SUPERADMIN", "tenant_id": T_A, "assigned_branch_ids": [B_A], "active_branch_id": B_A},
        {"email": USER_B, "name": "TEST Multi B", "role": "admin", "active": True, "password_hash": h,
         "tenant_id": T_B, "assigned_branch_ids": [B_B1, B_B2], "active_branch_id": B_B1},
    ]))
    yield {"counters_before": counters_before}
    # ---- cleanup everything TEST ----
    names = run(db.list_collection_names())
    for c in names:
        if c in OPERATIONAL_COLLECTIONS:
            run(db[c].delete_many({"tenant_id": {"$in": TENANTS}}))
    run(db.users.delete_many({"email": {"$regex": f"_{SUF}@example.com$"}}))
    run(db.branches.delete_many({"tenant_id": {"$in": TENANTS}}))
    run(db.tenants.delete_many({"_id": {"$in": TENANTS}}))
    run(db.login_attempts.delete_many({"identifier": {"$regex": SUF}}))
    run(db.audit_logs.delete_many({"user_email": {"$regex": f"_{SUF}@example.com$"}}))
    run(db.audit_logs.delete_many({"entity_id": {"$in": TEST_IDS}}))
    for k, v in counters_before.items():
        run(db.counters.update_one({"_id": k}, {"$set": {"seq": v}}))
    run(db.counters.delete_many({"_id": {"$nin": list(counters_before)}}))


@pytest.fixture(scope="module")
def ua(setup):
    return login(USER_A, TEST_PW)


@pytest.fixture(scope="module")
def ub(setup):
    return login(USER_B, TEST_PW)


# ---------- 1. Migration ----------
def test_migration_all_operational_scoped():
    db = rdb()
    for c in OPERATIONAL_COLLECTIONS:
        n = run(db[c].count_documents({"$or": [{"tenant_id": {"$exists": False}}, {"branch_id": {"$exists": False}}]}))
        assert n == 0, f"{c} has {n} unscoped docs"


# ---------- 2. Auth ----------
def test_owner_login_me(owner):
    r = owner.login_response
    assert "access_token" in r.cookies and "refresh_token" in r.cookies
    sc = r.headers.get("set-cookie", "").lower()
    assert "httponly" in sc and "samesite=none" in sc
    me = owner.get(f"{BASE}/auth/me").json()
    assert me["platform_role"] == "SUPERADMIN"
    assert me["tenant_id"] == "demo-tenant-001" and me["active_branch_id"] == "demo-branch-001"
    assert any(b["id"] == "demo-branch-001" for b in me["branches"])
    assert "password_hash" not in me


def test_cookie_scope_works(owner):
    s = requests.Session()
    s.cookies.update(owner.login_response.cookies)
    for ep in ["/clients", "/work-orders", "/invoices", "/products", "/rar-autopass/config"]:
        r = s.get(f"{BASE}{ep}")
        assert r.status_code == 200, f"{ep} {r.status_code} {r.text[:200]}"


def test_bcrypt_format():
    u = run(rdb().users.find_one({"email": "andrei.melek@gmail.com"}))
    assert u["password_hash"].startswith("$2b$")


def test_bruteforce_lockout():
    email = f"nobody_{SUF}@example.com"
    codes = [requests.post(f"{BASE}/auth/login", json={"email": email, "password": "x"}).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429, codes
    run(rdb().login_attempts.delete_many({"identifier": {"$regex": SUF}}))


# ---------- 3. Isolation ----------
def test_isolation_clients(owner, ua):
    me = ua.get(f"{BASE}/auth/me").json()
    assert me["tenant_id"] == T_A and me["active_branch_id"] == B_A
    r = ua.post(f"{BASE}/clients", json={"type": "pf", "name": f"TEST Client A {SUF}", "phone": "0700000000", "email": "a@example.com"})
    assert r.status_code == 200, r.text
    cid_a = r.json()["id"]
    TEST_IDS.append(cid_a)
    demo_clients = owner.get(f"{BASE}/clients").json()
    assert cid_a not in [c["id"] for c in demo_clients]
    assert owner.get(f"{BASE}/clients/{cid_a}").status_code == 404
    assert owner.put(f"{BASE}/clients/{cid_a}", json={"type": "pf", "name": "HACKED"}).status_code == 404
    owner.delete(f"{BASE}/clients/{cid_a}")
    assert ua.get(f"{BASE}/clients/{cid_a}").json()["name"] == f"TEST Client A {SUF}"
    a_clients = ua.get(f"{BASE}/clients").json()
    assert [c["id"] for c in a_clients] == [cid_a]
    demo_id = demo_clients[0]["id"]
    assert ua.get(f"{BASE}/clients/{demo_id}").status_code == 404
    assert ua.put(f"{BASE}/clients/{demo_id}", json={"type": "pf", "name": "HACKED"}).status_code == 404
    ua.delete(f"{BASE}/clients/{demo_id}")
    assert owner.get(f"{BASE}/clients/{demo_id}").json()["name"] != "HACKED"
    assert owner.get(f"{BASE}/clients/{demo_id}").status_code == 200


def test_isolation_lists_and_aggregates(owner, ua):
    for ep in ["/work-orders", "/invoices", "/products", "/payments", "/appointments?start=2020-01-01T00:00:00%2B00:00&end=2030-01-01T00:00:00%2B00:00", "/warranties", "/vehicles", "/mechanics", "/suppliers", "/audit"]:
        r = ua.get(f"{BASE}{ep}")
        assert r.status_code == 200, f"{ep}: {r.status_code} {r.text[:200]}"
        data = r.json()
        items = data if isinstance(data, list) else data.get("items", [])
        if ep != "/audit":
            assert len(items) == 0, f"{ep} leaked {len(items)} items to tenant A"
        else:
            assert all(a.get("user_email", "").endswith(f"_{SUF}@example.com") for a in items), "audit leak"
    d = ua.get(f"{BASE}/dashboard")
    assert d.status_code == 200, d.text
    demo_wo = owner.get(f"{BASE}/work-orders").json()[0]["id"]
    demo_inv = owner.get(f"{BASE}/invoices").json()
    demo_inv = (demo_inv if isinstance(demo_inv, list) else demo_inv["items"])[0]["id"]
    assert ua.get(f"{BASE}/work-orders/{demo_wo}").status_code == 404
    assert ua.get(f"{BASE}/invoices/{demo_inv}").status_code == 404


def test_cross_tenant_vehicle_with_demo_client(owner, ua):
    demo_cid = owner.get(f"{BASE}/clients").json()[0]["id"]
    r = ua.post(f"{BASE}/vehicles", json={"client_id": demo_cid, "vin": f"TSTXA{SUF.upper()}000001"[:17].ljust(17, "0"),
                                          "plate": "TST01AAA", "make": "Dacia", "model": "Logan"})
    assert r.status_code == 404, r.text


def test_vin_namespace_shared_across_tenants(ua):
    """Global unique index on vehicles.vin -> tenant A cannot register VIN existing in demo (and learns it exists)."""
    demo_vin = run(rdb().vehicles.find_one({"tenant_id": "demo-tenant-001"}))["vin"]
    cid = ua.get(f"{BASE}/clients").json()[0]["id"]
    r = ua.post(f"{BASE}/vehicles", json={"client_id": cid, "vin": demo_vin, "plate": "TST02AAA", "make": "Dacia", "model": "Logan"})
    assert r.status_code == 200, f"VIN collision across tenants: {r.status_code} {r.text[:200]}"


def test_settings_per_tenant(ua):
    r = ua.get(f"{BASE}/settings")
    assert r.status_code == 200
    assert r.json().get("name") in (None, ""), "demo settings leaked"
    r = ua.put(f"{BASE}/settings", json={"name": f"TEST Company A {SUF}"})
    assert r.status_code == 200, f"tenant settings write failed: {r.status_code} {r.text[:200]}"


def test_tenant_admin_user_mgmt_scoped(ua, demo_admin):
    emails = [u["email"] for u in ua.get(f"{BASE}/users").json()]
    assert "andrei.melek@gmail.com" not in emails and USER_A in emails
    demo_emails = [u["email"] for u in demo_admin.get(f"{BASE}/users").json()]
    assert USER_A not in demo_emails


def test_create_user_existing_email_other_tenant(ua):
    r = ua.post(f"{BASE}/users", json={"email": "receptie@serviceauto.ro", "name": "TEST dup", "role": "receptioner", "password": TEST_PW})
    assert r.status_code == 400, f"expected 400 business error, got {r.status_code} {r.text[:200]}"


def test_tenant_admin_can_escalate_via_superadmin_password_reset(ua):
    """TENANT_ADMIN can reset password of a SUPERADMIN user in same tenant -> privilege escalation."""
    victim = run(rdb().users.find_one({"email": USER_SA_VICTIM}))
    r = ua.put(f"{BASE}/users/{victim['_id']}", json={"email": USER_SA_VICTIM, "name": "x", "role": "admin", "password": "Escalated2026!"})
    escalated = False
    if r.status_code == 200:
        s = requests.Session()
        lr = s.post(f"{BASE}/auth/login", json={"email": USER_SA_VICTIM, "password": "Escalated2026!"})
        if lr.status_code == 200:
            s.headers["Authorization"] = f"Bearer {lr.json()['token']}"
            escalated = s.get(f"{BASE}/platform/tenants").status_code == 200
    assert not escalated, "tenant admin took over a SUPERADMIN account"


def test_shared_counter_numbering(ua):
    db = rdb()
    before = (run(db.counters.find_one({"_id": "demo-tenant-001:demo-branch-001:work_order"})) or {}).get("seq")
    cid = ua.get(f"{BASE}/clients").json()[0]["id"]
    vr = ua.post(f"{BASE}/vehicles", json={"client_id": cid, "vin": f"TSTB{SUF.upper()}".ljust(17, "1"), "plate": "TST03AAA", "make": "Dacia", "model": "Logan"})
    assert vr.status_code == 200, vr.text
    pytest.wo_vehicle = vr.json()["id"]
    w = ua.post(f"{BASE}/work-orders", json={"client_id": cid, "vehicle_id": vr.json()["id"], "mileage_in": 1000, "complaint": "TEST",
                                             "photos": {}, "signature": "data:image/png;base64,TEST"})
    assert w.status_code == 200, w.text
    pytest.wo_a = w.json()["id"]
    assert w.json()["number"].endswith(f"{1:05d}"), f"tenant A WO number continues demo sequence: {w.json()['number']} (demo seq was {before})"


# ---------- 6. Public quote ----------
def test_public_quote_token_scope(ua):
    wid = getattr(pytest, "wo_a", None)
    if not wid:
        pytest.skip("no WO")
    r = ua.post(f"{BASE}/work-orders/{wid}/lines", json={"type": "labor", "description": "TEST labor", "qty": 1, "unit_price": 100})
    assert r.status_code == 200, r.text
    q = ua.post(f"{BASE}/work-orders/{wid}/quotes", json={"valid_days": 7})
    assert q.status_code == 200, q.text
    token = q.json()[-1]["token"]
    p = requests.get(f"{BASE}/public/quotes/{token}")
    assert p.status_code == 200, p.text
    assert "token" not in p.json()["quote"] and p.json()["client"] == f"TEST Client A {SUF}"
    assert requests.get(f"{BASE}/public/quotes/invalid-token-xyz").status_code == 404
    d = requests.post(f"{BASE}/public/quotes/{token}/decision", json={"approved": True, "paper_approved": True, "name": "x"})
    assert d.status_code == 403, d.text
    q2 = ua.get(f"{BASE}/work-orders/{wid}/quotes").json()[-1]
    assert q2["status"] == "draft"


# ---------- 4. Quota & RBAC ----------
def test_quota_second_branch_403(owner, setup):
    r = owner.post(f"{BASE}/platform/tenants/{T_A}/branches", json={"branch_id": f"TEST-branch-a2-{SUF}", "branch_name": "TEST A2"})
    assert r.status_code == 403 and "limita" in r.json()["detail"].lower()
    r = owner.post(f"{BASE}/platform/tenants/demo-tenant-001/branches", json={"branch_id": f"TEST-demo-b2-{SUF}", "branch_name": "TEST D2"})
    assert r.status_code == 403


def test_non_superadmin_forbidden(demo_admin, ua):
    for s in (demo_admin, ua):
        assert s.get(f"{BASE}/platform/tenants").status_code == 403
        assert s.post(f"{BASE}/platform/tenants", json={"tenant_id": f"TEST-x-{SUF}", "company_name": "X"}).status_code == 403
        assert s.post(f"{BASE}/platform/tenants/{T_A}/branches", json={"branch_id": f"TEST-y-{SUF}", "branch_name": "Y"}).status_code == 403
        assert s.put(f"{BASE}/platform/tenants/{T_A}", json={"subscription_plan": "PRO", "max_branches_allowed": 99, "status": "ACTIVE"}).status_code == 403


def test_unauthenticated_401():
    assert requests.get(f"{BASE}/platform/tenants").status_code == 401
    assert requests.get(f"{BASE}/clients").status_code == 401


# ---------- 5. Branch switching ----------
def test_branch_switch(ub):
    me = ub.get(f"{BASE}/auth/me").json()
    assert {b["id"] for b in me["branches"]} == {B_B1, B_B2} and me["active_branch_id"] == B_B1
    c1 = ub.post(f"{BASE}/clients", json={"type": "pf", "name": f"TEST B1 {SUF}"}).json()["id"]
    r = ub.post(f"{BASE}/auth/active-branch", json={"branch_id": B_B2})
    assert r.status_code == 200, r.text
    tok1 = ub.headers["Authorization"]
    ub.headers["Authorization"] = f"Bearer {r.json()['token']}"
    assert ub.get(f"{BASE}/auth/me").json()["active_branch_id"] == B_B2
    assert c1 not in [c["id"] for c in ub.get(f"{BASE}/clients").json()]
    assert ub.get(f"{BASE}/clients/{c1}").status_code == 404
    c2 = ub.post(f"{BASE}/clients", json={"type": "pf", "name": f"TEST B2 {SUF}"}).json()["id"]
    assert [c["id"] for c in ub.get(f"{BASE}/clients").json()] == [c2]
    # old token still scoped to B1
    s = requests.Session(); s.headers["Authorization"] = tok1
    assert [c["id"] for c in s.get(f"{BASE}/clients").json()] == [c1]
    # not assigned branch / other tenant
    assert ub.post(f"{BASE}/auth/active-branch", json={"branch_id": "demo-branch-001"}).status_code == 403
    assert ub.post(f"{BASE}/auth/active-branch", json={"branch_id": B_A}).status_code == 403
    doc = run(rdb().clients.find_one({"name": f"TEST B2 {SUF}"}))
    assert doc["tenant_id"] == T_B and doc["branch_id"] == B_B2


def test_rar_config_singleton_per_tenant(ua, ub):
    """rar_autopass_config uses fixed _id='primary' -> only first tenant can save config."""
    body = {"branch_name": "TEST", "authorization_code": "TEST-AUTH", "service_cui": "RO123", "environment": "test"}
    ra = ua.put(f"{BASE}/rar-autopass/config", json=body)
    rb = ub.put(f"{BASE}/rar-autopass/config", json=body)
    assert ra.status_code == 200 and rb.status_code == 200, f"A={ra.status_code} B={rb.status_code} {rb.text[:150]}"


# ---------- 8. Demo regression ----------
def test_demo_regression(owner):
    for ep in ["/clients", "/work-orders", "/invoices", "/rar-autopass/config", "/warranties", "/appointments?start=2020-01-01T00:00:00%2B00:00&end=2030-01-01T00:00:00%2B00:00",
               "/reports/final-inspections?start=2026-01-01&end=2026-12-31", "/dashboard", "/products", "/payments", "/vehicles", "/settings"]:
        r = owner.get(f"{BASE}{ep}")
        assert r.status_code == 200, f"{ep}: {r.status_code} {r.text[:200]}"
    assert len(owner.get(f"{BASE}/clients").json()) >= 10
    assert owner.get(f"{BASE}/settings").json().get("name")
