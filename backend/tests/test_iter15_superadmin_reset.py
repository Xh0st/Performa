# Iteration 15: SUPERADMIN migration, tenant list admin_email, primary tenant admin password reset (temp password, forced change)
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
ADMIN_PW = re.search(r"admin@serviceauto\.ro / (\S+)", _txt).group(1)
SUF = uuid.uuid4().hex[:6]
PW = "TempInit2026!"
NEW_PW = "TempNew2026!x"
SA_TENANT = "tenant-e93a5f22c8ba4a11"
SA_BRANCH = "branch-e93a5f22c8ba4a11"
PROTECTED = ["tenant-92e564e6004a450d", "tenant-8541282f554641b8"]
LOOP = asyncio.new_event_loop()
_cli = None
CREATED = []
STATE = {}


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
def temp_tenant(owner):
    body = {"company_name": f"TEMP-rst-{SUF} SRL", "cui": f"RO-TEMPRST{SUF}".upper(),
            "admin_email": f"temp_rst_{SUF}@example.com", "initial_password": PW, "subscription_plan": "BASIC"}
    r = owner.post(f"{BASE}/platform/tenants", json=body)
    assert r.status_code == 200, r.text
    t = r.json()
    CREATED.append(t["id"])
    # complete initial change so the admin is fully active
    s = login(body["admin_email"], PW)
    r = s.post(f"{BASE}/auth/change-initial-password", json={"current_password": PW, "new_password": NEW_PW})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    assert s.get(f"{BASE}/clients").status_code == 200
    return body, t, s


# --- Migration ---
class TestMigration:
    def test_legacy_ids_gone(self):
        async def _c():
            d = rdb()
            assert await d.tenants.find_one({"_id": "demo-tenant-001"}) is None
            assert await d.branches.find_one({"_id": "demo-branch-001"}) is None
            for c in await d.list_collection_names():
                n = await d[c].count_documents({"$or": [{"tenant_id": "demo-tenant-001"}, {"branch_id": "demo-branch-001"},
                                                         {"active_branch_id": "demo-branch-001"},
                                                         {"assigned_branch_ids": "demo-branch-001"}]})
                assert n == 0, c
            assert await d.counters.count_documents({"_id": {"$regex": "demo-tenant-001"}}) == 0
        run(_c())

    def test_new_superadmin_tenant(self, owner):
        me = owner.get(f"{BASE}/auth/me").json()
        assert me["tenant_id"] == SA_TENANT and me["active_branch_id"] == SA_BRANCH
        assert me["platform_role"] == "SUPERADMIN"
        lst = owner.get(f"{BASE}/platform/tenants").json()
        t = next(x for x in lst if x["id"] == SA_TENANT)
        assert t["company_name"] == "SUPERADMIN" and t["status"] == "ACTIVE"
        assert t["admin_email"] == "andrei.melek@gmail.com" and t["admin_user_id"] == me["id"]
        br = owner.get(f"{BASE}/platform/tenants/{SA_TENANT}/branches").json()
        assert any(b["id"] == SA_BRANCH and b["is_main_branch"] for b in br)

    def test_operational_data_accessible(self, owner):
        for ep in ("clients", "vehicles", "work-orders", "invoices"):
            r = owner.get(f"{BASE}/{ep}")
            assert r.status_code == 200, (ep, r.text)
            assert len(r.json()) > 0, ep
        assert owner.get(f"{BASE}/settings").status_code == 200
        assert len(owner.get(f"{BASE}/audit").json()) > 0

    def test_demo_admin_in_new_context(self):
        s = login("admin@serviceauto.ro", ADMIN_PW)
        me = s.get(f"{BASE}/auth/me").json()
        assert me["tenant_id"] == SA_TENANT and me["active_branch_id"] == SA_BRANCH


# --- Tenant list admin_email ---
class TestTenantList:
    def test_list_has_admin_email_no_secrets(self, owner, temp_tenant):
        body, t, _ = temp_tenant
        r = owner.get(f"{BASE}/platform/tenants")
        assert r.status_code == 200
        lst = r.json()
        assert "password_hash" not in r.text and "temporary_password" not in r.text
        for item in lst:
            assert "admin_email" in item and "admin_user_id" in item
        me = next(x for x in lst if x["id"] == t["id"])
        assert me["admin_email"] == body["admin_email"]
        assert ObjectId.is_valid(me["admin_user_id"])
        for pid in PROTECTED:
            p = next((x for x in lst if x["id"] == pid), None)
            assert p is not None and p["admin_email"], pid

    def test_list_forbidden_non_superadmin(self):
        s = login("admin@serviceauto.ro", ADMIN_PW)
        assert s.get(f"{BASE}/platform/tenants").status_code == 403


# --- Reset password ---
class TestResetPassword:
    def test_non_superadmin_forbidden(self, temp_tenant):
        _, t, tsess = temp_tenant
        s = login("admin@serviceauto.ro", ADMIN_PW)
        assert s.post(f"{BASE}/platform/tenants/{t['id']}/admin/reset-password").status_code == 403
        # tenant admin itself can't reset either
        assert tsess.post(f"{BASE}/platform/tenants/{t['id']}/admin/reset-password").status_code == 403
        assert requests.post(f"{BASE}/platform/tenants/{t['id']}/admin/reset-password").status_code == 401

    def test_reject_own_and_unknown(self, owner):
        r = owner.post(f"{BASE}/platform/tenants/{SA_TENANT}/admin/reset-password")
        assert r.status_code == 400
        r = owner.post(f"{BASE}/platform/tenants/tenant-doesnotexist{SUF}/admin/reset-password")
        assert r.status_code == 404
        # owner password untouched
        login("andrei.melek@gmail.com", OWNER_PW)

    def test_reset_flow(self, owner, temp_tenant):
        body, t, old_sess = temp_tenant
        before = run(rdb().users.find_one({"email": body["admin_email"]}))
        r = owner.post(f"{BASE}/platform/tenants/{t['id']}/admin/reset-password")
        assert r.status_code == 200, r.text
        data = r.json()
        assert set(data.keys()) == {"admin_email", "temporary_password"}
        assert data["admin_email"] == body["admin_email"]
        tmp = data["temporary_password"]
        assert isinstance(tmp, str) and len(tmp) >= 12
        after = run(rdb().users.find_one({"email": body["admin_email"]}))
        assert after["password_hash"].startswith("$2b$") and tmp not in str(after)
        assert after["password_hash"] != before["password_hash"]
        assert after["must_change_password"] is True
        aud = run(rdb().audit_logs.find_one({"action": "reset_tenant_admin_password", "entity_id": t["id"]}))
        assert aud and aud["details"] == body["admin_email"] and tmp not in str(aud)
        # second reset generates different password (one-time display)
        # old session blocked
        assert old_sess.get(f"{BASE}/clients").status_code == 403
        assert old_sess.get(f"{BASE}/auth/me").status_code == 200
        # old password no longer works
        login(body["admin_email"], NEW_PW, expect=401)
        s = login(body["admin_email"], tmp)
        me = s.get(f"{BASE}/auth/me").json()
        assert me["must_change_password"] is True and "password_hash" not in me
        for ep in ("clients", "vehicles", "work-orders", "dashboard", "users", "platform/tenants"):
            assert s.get(f"{BASE}/{ep}").status_code == 403, ep
        r = s.post(f"{BASE}/auth/change-initial-password", json={"current_password": "wrongpass123", "new_password": "Another2026!"})
        assert r.status_code == 401
        r = s.post(f"{BASE}/auth/change-initial-password", json={"current_password": tmp, "new_password": tmp})
        assert r.status_code == 400
        final_pw = "Final2026!" + SUF
        r = s.post(f"{BASE}/auth/change-initial-password", json={"current_password": tmp, "new_password": final_pw})
        assert r.status_code == 200, r.text
        assert "password_hash" not in r.text
        s.headers["Authorization"] = f"Bearer {r.json()['token']}"
        assert s.get(f"{BASE}/clients").status_code == 200
        login(body["admin_email"], tmp, expect=401)
        login(body["admin_email"], final_pw)
        STATE["final_pw"] = final_pw

    def test_reset_twice_different_password(self, owner, temp_tenant):
        _, t, _ = temp_tenant
        a = owner.post(f"{BASE}/platform/tenants/{t['id']}/admin/reset-password").json()["temporary_password"]
        b = owner.post(f"{BASE}/platform/tenants/{t['id']}/admin/reset-password").json()["temporary_password"]
        assert a != b

    def test_tenant_without_admin_404(self, owner, temp_tenant):
        _, t, _ = temp_tenant
        async def _strip():
            d = rdb()
            await d.users.update_many({"tenant_id": t["id"]}, {"$set": {"tenant_id": t["id"] + "-detached"}})
        run(_strip())
        try:
            r = owner.post(f"{BASE}/platform/tenants/{t['id']}/admin/reset-password")
            assert r.status_code == 404
            lst = owner.get(f"{BASE}/platform/tenants").json()
            item = next(x for x in lst if x["id"] == t["id"])
            assert item["admin_email"] == ""
        finally:
            run(rdb().users.update_many({"tenant_id": t["id"] + "-detached"}, {"$set": {"tenant_id": t["id"]}}))

    def test_cleanup_delete_tenant(self, owner, temp_tenant):
        body, t, _ = temp_tenant
        r = owner.request("DELETE", f"{BASE}/platform/tenants/{t['id']}", json={"confirmation": body["company_name"]})
        assert r.status_code == 200
        assert run(rdb().users.count_documents({"tenant_id": t["id"]})) == 0
