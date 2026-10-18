# Iteration 12 P0 retest: suspended tenant/inactive branch, OAuth scope, cron isolation, singletons, counters,
# malicious tenant_id updates, SUPERADMIN protection, cross-tenant by-id, superadmin tenant-admin/branch APIs
import asyncio
import os
import re
import sys
import uuid

import pytest
import requests
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
T1, B1 = f"TEMP-t1-{SUF}", f"TEMP-b1-{SUF}"
T2, B2a, B2b = f"TEMP-t2-{SUF}", f"TEMP-b2a-{SUF}", f"TEMP-b2b-{SUF}"
U1, U2 = f"temp_a1_{SUF}@example.com", f"temp_a2_{SUF}@example.com"
PW = "TempPass2026!"
TENANTS = [T1, T2]
LOOP = asyncio.new_event_loop()


def run(c):
    return LOOP.run_until_complete(c)


_cli = None


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


@pytest.fixture(scope="module")
def demo_admin():
    return login("admin@serviceauto.ro", ADMIN_PW)


@pytest.fixture(scope="module")
def env(owner):
    db = rdb()
    counters_before = {c["_id"]: c["seq"] for c in run(db.counters.find().to_list(1000))}
    demo_cfg_before = run(db.efactura_config.find_one({"_id": "main"}))
    for t, mx in ((T1, 1), (T2, 2)):
        r = owner.post(f"{BASE}/platform/tenants", json={"tenant_id": t, "company_name": f"TEMP {t}", "max_branches_allowed": mx})
        assert r.status_code == 200, r.text
    for t, b in ((T1, B1), (T2, B2a), (T2, B2b)):
        r = owner.post(f"{BASE}/platform/tenants/{t}/branches", json={"branch_id": b, "branch_name": f"TEMP {b}"})
        assert r.status_code == 200, r.text
    r = owner.post(f"{BASE}/platform/tenants/{T1}/admins", json={"email": U1, "name": "TEMP A1", "password": PW, "branch_ids": [B1]})
    assert r.status_code == 200, r.text
    r = owner.post(f"{BASE}/platform/tenants/{T2}/admins", json={"email": U2, "name": "TEMP A2", "password": PW, "branch_ids": [B2a]})
    assert r.status_code == 200, r.text
    u2id = r.json()["id"]
    yield {"u2id": u2id, "demo_cfg_before": demo_cfg_before}
    for c in run(db.list_collection_names()):
        if c in OPERATIONAL_COLLECTIONS or c == "cron_errors":
            run(db[c].delete_many({"tenant_id": {"$in": TENANTS}}))
    run(db.users.delete_many({"email": {"$regex": f"_{SUF}@example.com$"}}))
    run(db.branches.delete_many({"tenant_id": {"$in": TENANTS}}))
    run(db.tenants.delete_many({"_id": {"$in": TENANTS}}))
    run(db.login_attempts.delete_many({"identifier": {"$regex": SUF}}))
    run(db.audit_logs.delete_many({"user_email": {"$regex": f"_{SUF}@example.com$"}}))
    run(db.counters.delete_many({"_id": {"$regex": "^TEMP-"}}))
    for k, v in counters_before.items():
        run(db.counters.update_one({"_id": k}, {"$set": {"seq": v}}))


@pytest.fixture(scope="module")
def a1(env):
    return login(U1, PW)


@pytest.fixture(scope="module")
def a2(env):
    return login(U2, PW)


# ---- Superadmin APIs: tenant admin + branch assignment ----
def test_superadmin_branch_assignment(owner, env):
    r = owner.put(f"{BASE}/platform/users/{env['u2id']}/branches", json={"branch_ids": [B1]})
    assert r.status_code == 400, r.text  # foreign tenant branch rejected
    r = owner.put(f"{BASE}/platform/users/{env['u2id']}/branches", json={"branch_ids": [B2a, B2b]})
    assert r.status_code == 200 and r.json()["assigned_branch_ids"] == [B2a, B2b]
    r = owner.post(f"{BASE}/platform/tenants/{T1}/admins", json={"email": f"x_{SUF}@example.com", "name": "x", "password": PW, "branch_ids": [B2a]})
    assert r.status_code == 400


def test_platform_403_non_superadmin(demo_admin, a1):
    for s in (demo_admin, a1):
        assert s.get(f"{BASE}/platform/tenants").status_code == 403
        assert s.post(f"{BASE}/platform/tenants", json={"tenant_id": f"TEMP-x-{SUF}", "company_name": "x"}).status_code == 403
        assert s.put(f"{BASE}/platform/tenants/{T1}", json={"subscription_plan": "PRO", "max_branches_allowed": 9, "status": "ACTIVE"}).status_code == 403
        assert s.post(f"{BASE}/platform/tenants/{T1}/admins", json={"email": f"y_{SUF}@example.com", "name": "y", "password": PW, "branch_ids": [B1]}).status_code == 403


def test_superadmin_protected(demo_admin, owner):
    me = owner.get(f"{BASE}/auth/me").json()
    r = demo_admin.put(f"{BASE}/users/{me['id']}", json={"email": me["email"], "name": "hack", "role": "mecanic", "password": "Hacked12345"})
    assert r.status_code == 403, r.text
    assert demo_admin.delete(f"{BASE}/users/{me['id']}").status_code == 403
    assert owner.get(f"{BASE}/auth/me").json()["role"] == "admin"


# ---- Suspended tenant / inactive branch ----
def test_suspended_tenant_blocks_me_login_refresh(owner, env):
    s = login(U1, PW)
    assert s.get(f"{BASE}/auth/me").status_code == 200
    r = owner.put(f"{BASE}/platform/tenants/{T1}", json={"subscription_plan": "BASIC", "max_branches_allowed": 1, "status": "SUSPENDED"})
    assert r.status_code == 200
    try:
        assert s.get(f"{BASE}/auth/me").status_code == 403
        assert s.get(f"{BASE}/clients").status_code == 403
        assert s.post(f"{BASE}/auth/refresh").status_code == 403  # refresh cookie in session
        login(U1, PW, expect=403)
    finally:
        owner.put(f"{BASE}/platform/tenants/{T1}", json={"subscription_plan": "BASIC", "max_branches_allowed": 1, "status": "ACTIVE"})
    assert s.get(f"{BASE}/auth/me").status_code == 200


def test_inactive_branch_blocks(env):
    s = login(U1, PW)
    run(rdb().branches.update_one({"_id": B1}, {"$set": {"status": "INACTIVE"}}))
    try:
        assert s.get(f"{BASE}/auth/me").status_code == 403
        assert s.post(f"{BASE}/auth/refresh").status_code == 403
        login(U1, PW, expect=403)
    finally:
        run(rdb().branches.update_one({"_id": B1}, {"$set": {"status": "ACTIVE"}}))
    assert s.get(f"{BASE}/auth/me").status_code == 200


# ---- Singletons per tenant ----
def test_settings_rar_efactura_distinct(a1, a2, demo_admin):
    demo_settings = demo_admin.get(f"{BASE}/settings").json()
    assert a1.put(f"{BASE}/settings", json={"company_name": f"TEMP C1 {SUF}"}).status_code == 200
    assert a2.put(f"{BASE}/settings", json={"company_name": f"TEMP C2 {SUF}"}).status_code == 200
    assert a1.get(f"{BASE}/settings").json()["company_name"] == f"TEMP C1 {SUF}"
    assert a2.get(f"{BASE}/settings").json()["company_name"] == f"TEMP C2 {SUF}"
    assert demo_admin.get(f"{BASE}/settings").json().get("company_name") == demo_settings.get("company_name")
    for s, code in ((a1, "TEMPRAR1"), (a2, "TEMPRAR2")):
        r = s.put(f"{BASE}/rar-autopass/config", json={"authorization_code": code, "service_cui": "RO123", "environment": "test"})
        assert r.status_code == 200, r.text
    assert a1.get(f"{BASE}/rar-autopass/config").json()["authorization_code"] == "TEMPRAR1"
    assert a2.get(f"{BASE}/rar-autopass/config").json()["authorization_code"] == "TEMPRAR2"
    for s, cid in ((a1, "TEMPCID1"), (a2, "TEMPCID2")):
        r = s.put(f"{BASE}/efactura/config", json={"environment": "simulare", "client_id": cid})
        assert r.status_code == 200, r.text
    assert a1.get(f"{BASE}/efactura/config").json()["client_id"] == "TEMPCID1"
    assert a2.get(f"{BASE}/efactura/config").json()["client_id"] == "TEMPCID2"
    db = rdb()
    for coll, kind in (("settings", "company"), ("rar_autopass_config", "rar_autopass"), ("efactura_config", "efactura")):
        for t in TENANTS:
            assert run(db[coll].count_documents({"tenant_id": t, "kind": kind})) == 1, (coll, t)


def test_malicious_settings_body_does_not_move(a1, demo_admin):
    before = run(rdb().settings.count_documents({"tenant_id": "demo-tenant-001"}))
    r = a1.put(f"{BASE}/settings", json={"tenant_id": "demo-tenant-001", "branch_id": "demo-branch-001", "company_name": f"TEMP M {SUF}"})
    assert r.status_code == 200
    doc = run(rdb().settings.find_one({"tenant_id": T1, "kind": "company"}))
    assert doc and doc["branch_id"] == B1 and doc["company_name"] == f"TEMP M {SUF}"
    assert run(rdb().settings.count_documents({"tenant_id": "demo-tenant-001"})) == before
    assert demo_admin.get(f"{BASE}/settings").json().get("company_name") != f"TEMP M {SUF}"


def test_tenantcollection_sanitizes_and_forbids_unscoped():
    async def go():
        import core
        from tenant_context import set_scope
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        core.raw_db = cli
        db = core.TenantDatabase()
        set_scope({"tenant_id": T1, "branch_id": B1})
        r = await db.clients.insert_one({"name": f"TEMP sanit {SUF}", "tenant_id": "demo-tenant-001"})
        doc = await cli.clients.find_one({"_id": r.inserted_id})
        assert doc["tenant_id"] == T1
        await db.clients.update_one({"_id": r.inserted_id}, {"$set": {"tenant_id": "demo-tenant-001", "branch_id": "demo-branch-001"}})
        doc = await cli.clients.find_one({"_id": r.inserted_id})
        assert doc["tenant_id"] == T1 and doc["branch_id"] == B1
        for bad in ("replace_one", "bulk_write", "find_one_and_replace", "find_one_and_delete", "rename", "drop"):
            with pytest.raises(AttributeError):
                getattr(db.clients, bad)
        await db.clients.update_one({"_id": r.inserted_id}, {"$unset": {"tenant_id": ""}})
        doc = await cli.clients.find_one({"_id": r.inserted_id})
        if "tenant_id" not in doc:
            await cli.clients.delete_one({"_id": r.inserted_id})
        return doc
    doc = asyncio.new_event_loop().run_until_complete(go())
    assert "tenant_id" in doc, "$unset tenant_id not sanitized -> document orphaned (minor hardening)"


def test_counters_independent():
    async def go():
        import core
        from tenant_context import set_scope
        core.raw_db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        set_scope({"tenant_id": T1, "branch_id": B1})
        a = [await core.next_seq("work_order"), await core.next_seq("work_order")]
        set_scope({"tenant_id": T2, "branch_id": B2a})
        b = await core.next_seq("work_order")
        set_scope({"tenant_id": T2, "branch_id": B2b})
        c = await core.next_seq("work_order")
        return a, b, c
    demo_before = run(rdb().counters.find_one({"_id": "demo-tenant-001:demo-branch-001:work_order"}))
    a, b, c = asyncio.new_event_loop().run_until_complete(go())
    assert a == [1, 2] and b == 1 and c == 1
    demo_after = run(rdb().counters.find_one({"_id": "demo-tenant-001:demo-branch-001:work_order"}))
    assert demo_before == demo_after


# ---- Cross-tenant by id ----
def test_cross_tenant_by_id(a1, a2):
    cl = a1.post(f"{BASE}/clients", json={"name": f"TEMP Client {SUF}"}).json()
    pr = a1.post(f"{BASE}/products", json={"code": f"TEMP-P-{SUF}", "name": "TEMP P", "sale_price": 10}).json()
    assert a2.delete(f"{BASE}/clients/{cl['id']}").status_code == 404
    assert a2.get(f"{BASE}/clients/{cl['id']}").status_code == 404
    assert a2.put(f"{BASE}/clients/{cl['id']}", json={"name": "PWNED"}).status_code == 404
    assert a2.get(f"{BASE}/products/{pr['id']}/moves").status_code == 404
    assert a2.put(f"{BASE}/products/{pr['id']}", json={"code": "PWN", "name": "PWNED"}).status_code == 404
    assert a1.get(f"{BASE}/clients/{cl['id']}").json()["name"] == f"TEMP Client {SUF}"
    assert a1.get(f"{BASE}/products/{pr['id']}/moves").status_code == 200
    assert not run(rdb().audit_logs.find_one({"entity_id": cl["id"], "action": "delete"}))


# ---- OAuth callback scope ----
def test_oauth_callback_scoped(a1, env):
    from datetime import datetime, timezone
    state = f"TEMPSTATE{SUF}"
    assert a1.put(f"{BASE}/efactura/config", json={"environment": "simulare", "client_id": "TEMPCID1", "client_secret": "TEMPSECRET"}).status_code == 200
    run(rdb().efactura_config.update_one({"tenant_id": T1, "kind": "efactura"}, {"$set": {"oauth_state": state, "oauth_state_at": datetime.now(timezone.utc).isoformat()}}))
    r = requests.get(f"{BASE}/efactura/oauth/callback", params={"code": "fake", "state": state}, allow_redirects=False)
    assert r.status_code in (302, 307), (r.status_code, r.text)
    doc = run(rdb().efactura_config.find_one({"tenant_id": T1, "kind": "efactura"}))
    assert doc.get("oauth_state") == ""
    assert run(rdb().efactura_logs.count_documents({"tenant_id": T1, "op": "oauth"})) >= 1
    r = requests.get(f"{BASE}/efactura/oauth/callback", params={"code": "x", "state": "nonexistent"}, allow_redirects=False)
    assert r.status_code in (302, 307) and "oauth=error" in r.headers["location"]
    demo = run(rdb().efactura_config.find_one({"_id": "main"}))
    assert demo.get("oauth_state") == (env["demo_cfg_before"] or {}).get("oauth_state")


def test_oauth_disconnect_non_demo_tenant(a1):
    run(rdb().efactura_config.update_one({"tenant_id": T1, "kind": "efactura"}, {"$set": {"access_token": "TEMPTOKEN"}}))
    assert a1.post(f"{BASE}/efactura/oauth/disconnect").status_code == 200
    doc = run(rdb().efactura_config.find_one({"tenant_id": T1, "kind": "efactura"}))
    assert "access_token" not in doc, "disconnect filters _id='main' -> tokens not removed for non-demo tenants"


# ---- Cron per-branch isolation ----
def test_cron_isolation_inprocess(env):
    import routes_efactura as rf
    import core
    from tenant_context import current_scope
    seen = []

    async def fake_job(job):
        sc = current_scope()
        seen.append(sc["branch_id"])
        if sc["branch_id"] == B2a:
            raise RuntimeError("TEMP boom")
        from core import db
        await db.efactura_config.find_one({"kind": "efactura"})  # must not 503

    async def go():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        core.raw_db, rf.raw_db = cli, cli
        core.db = core.TenantDatabase()
        orig = rf._run_job
        rf._run_job = fake_job
        try:
            await rf._run_job_all_tenants("status")
        finally:
            rf._run_job = orig
    asyncio.new_event_loop().run_until_complete(go())
    assert B1 in seen and B2a in seen and B2b in seen and "demo-branch-001" in seen
    assert seen.index(B2b) > seen.index(B2a) or B2b in seen
    assert run(rdb().cron_errors.count_documents({"branch_id": B2a})) == 1
    assert run(rdb().cron_errors.count_documents({"branch_id": {"$in": [B1, B2b]}})) == 0


def test_cron_http_endpoints():
    sec = os.environ["WEBHOOK_CRON_SECRET"]
    assert requests.post(f"{BASE}/cron/efactura/status").status_code == 401
    before = run(rdb().cron_errors.count_documents({"tenant_id": {"$in": TENANTS}}))
    r = requests.post(f"{BASE}/cron/efactura/status", headers={"Authorization": f"Bearer {sec}"})
    assert r.status_code == 200 and r.json()["ok"]
    import time
    time.sleep(3)
    assert run(rdb().cron_errors.count_documents({"tenant_id": {"$in": TENANTS}})) == before


def test_branch_switch_multi(env):
    s = login(U2, PW)
    me = s.get(f"{BASE}/auth/me").json()
    assert {b["id"] for b in me["branches"]} == {B2a, B2b}
    r = s.post(f"{BASE}/auth/active-branch", json={"branch_id": B2b})
    assert r.status_code == 200
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    assert s.get(f"{BASE}/auth/me").json()["active_branch_id"] == B2b
    assert s.post(f"{BASE}/auth/active-branch", json={"branch_id": B1}).status_code == 403
    assert s.post(f"{BASE}/auth/active-branch", json={"branch_id": "demo-branch-001"}).status_code == 403
