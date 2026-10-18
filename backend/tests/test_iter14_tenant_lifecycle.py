# Iteration 14: tenant create (auto ID, BASIC/FULL quota, main branch + admin), initial-password guard,
# change-initial-password validations, tenant delete (authz, confirmation, full cleanup)
import asyncio
import os
import re
import uuid

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
import sys
sys.path.insert(0, "/app/backend")
from tenant_context import OPERATIONAL_COLLECTIONS  # noqa: E402

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
_txt = open("/app/memory/test_credentials.md").read()
OWNER_PW = re.search(r"andrei\.melek@gmail\.com / (\S+)", _txt).group(1)
ADMIN_PW = re.search(r"admin@serviceauto\.ro / (\S+)", _txt).group(1)
SUF = uuid.uuid4().hex[:6]
PW = "TempInit2026!"
NEW_PW = "TempNew2026!x"
LOOP = asyncio.new_event_loop()
_cli = None
CREATED = []


def run(c):
    return LOOP.run_until_complete(c)


def rdb():
    global _cli
    if _cli is None:
        asyncio.set_event_loop(LOOP)
        _cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return _cli[os.environ["DB_NAME"]]


def login(email, pw, expect=200):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == expect, r.text
    if expect == 200:
        s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="module")
def owner():
    return login("andrei.melek@gmail.com", OWNER_PW)


def make_tenant(owner, plan, tag):
    body = {"company_name": f"TEMP-{tag}-{SUF} SRL", "cui": f"RO-TEMP{tag}{SUF}".upper(),
            "admin_email": f"temp_{tag}_{SUF}@example.com", "initial_password": PW, "subscription_plan": plan}
    r = owner.post(f"{BASE}/platform/tenants", json=body)
    assert r.status_code == 200, r.text
    t = r.json()
    CREATED.append(t["id"])
    return body, t


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    async def _c():
        d = rdb()
        for tid in CREATED:
            for col in OPERATIONAL_COLLECTIONS | {"cron_errors"}:
                await d[col].delete_many({"tenant_id": tid})
            await d.users.delete_many({"tenant_id": tid})
            await d.branches.delete_many({"tenant_id": tid})
            await d.counters.delete_many({"_id": {"$regex": f"^{re.escape(tid)}:"}})
            await d.tenants.delete_one({"_id": tid})
        await d.users.delete_many({"email": {"$regex": f"_{SUF}@example.com$"}})
        await d.login_attempts.delete_many({"identifier": {"$regex": SUF}})
    run(_c())


@pytest.fixture(scope="module")
def full_tenant(owner):
    return make_tenant(owner, "FULL", "full")


# --- create ---
def test_create_full_autogen_id_quota_branch_admin(full_tenant):
    body, t = full_tenant
    assert re.fullmatch(r"tenant-[0-9a-f]{16}", t["id"])
    assert t["max_branches_allowed"] == 5 and t["subscription_plan"] == "FULL" and t["status"] == "ACTIVE"
    assert t["cui"] == body["cui"]
    d = rdb()
    branches = run(d.branches.find({"tenant_id": t["id"]}).to_list(10))
    assert len(branches) == 1 and branches[0]["is_main_branch"] is True
    u = run(d.users.find_one({"email": body["admin_email"]}))
    assert u["tenant_id"] == t["id"] and u["tenant_role"] == "TENANT_ADMIN" and u["must_change_password"] is True
    assert u["password_hash"].startswith("$2b$")
    assert u["assigned_branch_ids"] == [branches[0]["_id"]]
    assert not u.get("platform_role")


def test_create_basic_quota(owner):
    _, t = make_tenant(owner, "BASIC", "basic")
    assert t["max_branches_allowed"] == 1
    r = owner.post(f"{BASE}/platform/tenants/{t['id']}/branches",
                   json={"branch_id": f"TEMP-bb-{SUF}", "branch_name": "x2"})
    assert r.status_code == 403


def test_create_validations(owner, full_tenant):
    body, _ = full_tenant
    base = {"company_name": f"TEMP-v-{SUF} SRL", "cui": f"RO-TEMPV{SUF}", "admin_email": f"temp_v_{SUF}@example.com",
            "initial_password": PW, "subscription_plan": "BASIC"}
    assert owner.post(f"{BASE}/platform/tenants", json=base | {"subscription_plan": "GOLD"}).status_code == 400
    assert owner.post(f"{BASE}/platform/tenants", json=base | {"cui": body["cui"].lower()}).status_code == 400
    assert owner.post(f"{BASE}/platform/tenants", json=base | {"admin_email": body["admin_email"].upper()}).status_code == 400
    assert owner.post(f"{BASE}/platform/tenants", json=base | {"initial_password": "short"}).status_code == 422
    assert owner.post(f"{BASE}/platform/tenants", json=base | {"admin_email": "invalid-email"}).status_code == 422
    assert owner.post(f"{BASE}/platform/tenants", json={k: v for k, v in base.items() if k != "initial_password"}).status_code == 422
    assert run(rdb().tenants.find_one({"cui": base["cui"].upper()})) is None


def test_non_superadmin_cannot_create_or_delete(full_tenant):
    _, t = full_tenant
    demo = login("admin@serviceauto.ro", ADMIN_PW)
    r = demo.post(f"{BASE}/platform/tenants", json={"company_name": "TEMP-x SRL", "cui": "TEMPX" + SUF,
                                                     "admin_email": f"temp_x_{SUF}@example.com", "initial_password": PW})
    assert r.status_code == 403
    r = demo.delete(f"{BASE}/platform/tenants/{t['id']}", json={"confirmation": t["company_name"]})
    assert r.status_code == 403
    assert run(rdb().tenants.find_one({"_id": t["id"]})) is not None


# --- initial password guard ---
def test_initial_login_and_guard(full_tenant):
    body, t = full_tenant
    s = login(body["admin_email"], PW)
    me = s.get(f"{BASE}/auth/me")
    assert me.status_code == 200 and me.json()["must_change_password"] is True
    assert me.json()["tenant_id"] == t["id"]
    for path in ["/clients", "/vehicles", "/work-orders", "/dashboard", "/users", "/platform/tenants"]:
        r = s.get(f"{BASE}{path}")
        assert r.status_code == 403, f"{path} -> {r.status_code}"
    # cookie-only path is guarded too
    c = requests.Session()
    c.post(f"{BASE}/auth/login", json={"email": body["admin_email"], "password": PW})
    assert c.get(f"{BASE}/clients").status_code == 403


def test_change_initial_password_validations_and_success(full_tenant):
    body, _ = full_tenant
    s = login(body["admin_email"], PW)
    url = f"{BASE}/auth/change-initial-password"
    assert s.post(url, json={"current_password": "WrongPass123", "new_password": NEW_PW}).status_code == 401
    assert s.post(url, json={"current_password": PW, "new_password": PW}).status_code == 400
    assert s.post(url, json={"current_password": PW, "new_password": "short"}).status_code == 400
    assert s.get(f"{BASE}/clients").status_code == 403
    r = s.post(url, json={"current_password": PW, "new_password": NEW_PW})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["user"]["must_change_password"] is False and "password_hash" not in data["user"]
    assert data["user"]["tenant_id"] == full_tenant[1]["id"]
    assert len(data["user"]["branches"]) == 1
    s.headers["Authorization"] = f"Bearer {data['token']}"
    assert s.get(f"{BASE}/clients").status_code == 200
    assert s.get(f"{BASE}/auth/me").json()["must_change_password"] is False
    # second change rejected; old password no longer works; new does
    assert s.post(url, json={"current_password": NEW_PW, "new_password": "Another2026!"}).status_code == 400
    login(body["admin_email"], PW, expect=401)
    s2 = login(body["admin_email"], NEW_PW)
    assert s2.get(f"{BASE}/clients").status_code == 200
    # isolation: new admin sees no demo data
    assert s2.get(f"{BASE}/clients").json() in ([], {"items": [], "total": 0}) or len(s2.get(f"{BASE}/clients").json()) == 0


def test_change_initial_password_unauth():
    r = requests.post(f"{BASE}/auth/change-initial-password", json={"current_password": "a", "new_password": "bbbbbbbbb"})
    assert r.status_code == 401


# --- delete ---
def test_delete_own_context_tenant_refused(owner):
    me = owner.get(f"{BASE}/auth/me").json()
    r = owner.delete(f"{BASE}/platform/tenants/{me['tenant_id']}", json={"confirmation": "whatever"})
    assert r.status_code == 400
    assert run(rdb().tenants.find_one({"_id": me["tenant_id"]})) is not None


def test_delete_404_and_wrong_confirmation(owner, full_tenant):
    _, t = full_tenant
    assert owner.delete(f"{BASE}/platform/tenants/tenant-doesnotexist{SUF}", json={"confirmation": "xx"}).status_code == 404
    r = owner.delete(f"{BASE}/platform/tenants/{t['id']}", json={"confirmation": t["company_name"].lower()})
    assert r.status_code == 400
    assert owner.delete(f"{BASE}/platform/tenants/{t['id']}").status_code == 422
    assert run(rdb().tenants.find_one({"_id": t["id"]})) is not None


def test_delete_full_cleanup(owner, full_tenant):
    body, t = full_tenant
    tid = t["id"]
    s = login(body["admin_email"], NEW_PW)
    r = s.post(f"{BASE}/clients", json={"name": f"TEMP client {SUF}", "type": "pf", "phone": "0700000000"})
    assert r.status_code in (200, 201), r.text
    d = rdb()
    assert run(d.clients.count_documents({"tenant_id": tid})) >= 1
    run(d.counters.insert_one({"_id": f"{tid}:fakebranch:test", "seq": 1}))
    r = owner.delete(f"{BASE}/platform/tenants/{tid}", json={"confirmation": "  " + t["company_name"] + " "})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert run(d.tenants.find_one({"_id": tid})) is None
    assert run(d.users.count_documents({"tenant_id": tid})) == 0
    assert run(d.branches.count_documents({"tenant_id": tid})) == 0
    assert run(d.counters.count_documents({"_id": {"$regex": f"^{tid}:"}})) == 0
    for col in OPERATIONAL_COLLECTIONS:
        assert run(d[col].count_documents({"tenant_id": tid})) == 0, col
    # old session of deleted admin is dead
    assert s.get(f"{BASE}/auth/me").status_code in (401, 403)
    login(body["admin_email"], NEW_PW, expect=401)
    assert owner.get(f"{BASE}/platform/tenants").status_code == 200
