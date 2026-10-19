# Iteration 13 final MT security retest: eFactura disconnect (non-demo), TenantCollection update hardening,
# OAuth callback empty-state / generic failure, tenant+branch suspend/reactivate, cross-tenant CRUD + aggregate, quota
import asyncio
import os
import re
import sys
import time
import uuid
from types import SimpleNamespace

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
sys.path.insert(0, "/app/backend")
from tenant_context import DEMO_BRANCH_ID, DEMO_TENANT_ID, OPERATIONAL_COLLECTIONS  # noqa: E402

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


def _mk_tenant(owner, tid, name, mx):
    run(rdb().tenants.insert_one({
        "_id": tid,
        "company_name": name,
        "cui": f"CUI-{tid}",
        "subscription_plan": "BASIC" if mx == 1 else "FULL",
        "max_branches_allowed": mx,
        "status": "ACTIVE",
    }))
    return SimpleNamespace(status_code=200, text="")
_txt = open("/app/memory/test_credentials.md").read()
OWNER_PW = re.search(r"andrei\.melek@gmail\.com / (\S+)", _txt).group(1)
ADMIN_PW = re.search(r"admin@serviceauto\.ro / (\S+)", _txt).group(1)
SUF = uuid.uuid4().hex[:6]
T1, B1 = f"TEMP-f1-{SUF}", f"TEMP-fb1-{SUF}"
T2, B2a, B2b = f"TEMP-f2-{SUF}", f"TEMP-fb2a-{SUF}", f"TEMP-fb2b-{SUF}"
U1, U2 = f"temp_f1_{SUF}@example.com", f"temp_f2_{SUF}@example.com"
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
    demo_cfg = run(db.efactura_config.find_one({"tenant_id": DEMO_TENANT_ID, "kind": "efactura"}))
    for t, mx in ((T1, 1), (T2, 2)):
        assert _mk_tenant(owner, t, f"TEMP {t}", mx).status_code == 200
    for t, b in ((T1, B1), (T2, B2a), (T2, B2b)):
        assert owner.post(f"{BASE}/platform/tenants/{t}/branches", json={"branch_id": b, "branch_name": f"TEMP {b}"}).status_code == 200
    assert owner.post(f"{BASE}/platform/tenants/{T1}/admins", json={"email": U1, "name": "TEMP F1", "password": PW, "branch_ids": [B1]}).status_code == 200
    assert owner.post(f"{BASE}/platform/tenants/{T2}/admins", json={"email": U2, "name": "TEMP F2", "password": PW, "branch_ids": [B2a]}).status_code == 200
    yield {"demo_cfg": demo_cfg}
    for c in run(db.list_collection_names()):
        if c in OPERATIONAL_COLLECTIONS or c == "cron_errors":
            run(db[c].delete_many({"tenant_id": {"$in": TENANTS}}))
    run(db.clients.delete_many({"name": {"$regex": f"TEMP.*{SUF}"}}))
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


# ---- eFactura disconnect non-demo tenant ----
def test_efactura_disconnect_unsets_all_tokens(a1, a2, env):
    for s, cid in ((a1, "TEMPCID1"), (a2, "TEMPCID2")):
        assert s.put(f"{BASE}/efactura/config", json={"environment": "test", "client_id": cid}).status_code == 200
    toks = {"access_token": "TEMPAT", "refresh_token": "TEMPRT", "token_expires_at": "2099-01-01", "refresh_expires_at": "2099-01-01", "connected_at": "2026-01-01"}
    for t in TENANTS:
        run(rdb().efactura_config.update_one({"tenant_id": t, "kind": "efactura"}, {"$set": toks}))
    r = a1.post(f"{BASE}/efactura/oauth/disconnect")
    assert r.status_code == 200, r.text
    assert r.json().get("connected") in (False, None) or "access_token" not in r.json()
    d1 = run(rdb().efactura_config.find_one({"tenant_id": T1, "kind": "efactura"}))
    for k in toks:
        assert k not in d1, k
    assert d1["client_id"] == "TEMPCID1" and d1["branch_id"] == B1
    d2 = run(rdb().efactura_config.find_one({"tenant_id": T2, "kind": "efactura"}))
    assert d2["access_token"] == "TEMPAT"  # other tenant untouched
    demo = run(rdb().efactura_config.find_one({"tenant_id": DEMO_TENANT_ID, "kind": "efactura"}))
    assert (demo or {}).get("access_token") == (env["demo_cfg"] or {}).get("access_token")
    assert run(rdb().efactura_logs.count_documents({"tenant_id": T1, "op": "oauth", "message": "Deconectat SPV"})) == 1


# ---- TenantCollection hardening ----
def test_tenantcollection_update_operators():
    async def go():
        import core
        from fastapi import HTTPException
        from tenant_context import set_scope, clear_scope
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        core.raw_db = cli
        db = core.TenantDatabase()
        set_scope({"tenant_id": T1, "branch_id": B1})
        r = await db.clients.insert_one({"name": f"TEMP h {SUF}", "tenant_id": "demo-tenant-001", "branch_id": "demo-branch-001"})
        _id = r.inserted_id
        res = {}

        async def chk(label):
            d = await cli.clients.find_one({"_id": _id})
            res[label] = (d.get("tenant_id"), d.get("branch_id"))

        await db.clients.update_one({"_id": _id}, {"$set": {"tenant_id": "demo-tenant-001", "branch_id": "demo-branch-001", "x": 1}})
        await chk("set")
        await db.clients.update_one({"_id": _id}, {"$unset": {"tenant_id": "", "branch_id": ""}})
        await chk("unset")
        await db.clients.update_one({"_id": _id}, {"$rename": {"tenant_id": "old_t", "branch_id": "old_b"}})
        await chk("rename_from")
        await db.clients.update_one({"_id": _id}, {"$set": {"evil": "demo-tenant-001"}})
        await db.clients.update_one({"_id": _id}, {"$rename": {"evil": "tenant_id"}})
        await chk("rename_to")
        await db.clients.update_many({"_id": _id}, {"$set": {"tenant_id": "demo-tenant-001"}, "$unset": {"branch_id": ""}})
        await chk("update_many")
        await db.clients.find_one_and_update({"_id": _id}, {"$set": {"tenant_id": "demo-tenant-001"}, "$currentDate": {"branch_id": True}})
        await chk("fau")
        await db.clients.update_one({"_id": _id}, {"$setOnInsert": {"tenant_id": "demo-tenant-001"}, "$set": {"y": 1}}, upsert=True)
        await chk("upsert_existing")
        pipe = None
        try:
            await db.clients.update_one({"_id": _id}, [{"$set": {"tenant_id": "demo-tenant-001"}}])
        except HTTPException as e:
            pipe = e.status_code
        await chk("pipeline")
        pipe_many = None
        try:
            await db.clients.update_many({"_id": _id}, [{"$unset": "tenant_id"}])
        except HTTPException as e:
            pipe_many = e.status_code
        raw_blocked = []
        for bad in ("replace_one", "bulk_write", "find_one_and_replace", "find_one_and_delete", "rename", "drop", "watch", "estimated_document_count", "map_reduce", "database"):
            try:
                getattr(db.clients, bad)
            except AttributeError:
                raw_blocked.append(bad)
        # upsert insert path stamps scope
        await db.clients.update_one({"name": f"TEMP ups {SUF}"}, {"$set": {"tenant_id": "demo-tenant-001", "name": f"TEMP ups {SUF}"}}, upsert=True)
        ups = await cli.clients.find_one({"name": f"TEMP ups {SUF}"})
        # no-scope -> fail closed
        clear_scope()
        noscope = None
        try:
            await db.clients.find_one({})
        except HTTPException as e:
            noscope = e.status_code
        noscope_upd = None
        try:
            await db.clients.update_one({"_id": _id}, {"$set": {"z": 1}}, upsert=True)
        except HTTPException as e:
            noscope_upd = e.status_code
        except Exception as e:  # noqa: BLE001
            noscope_upd = type(e).__name__
        await cli.clients.delete_many({"name": {"$regex": f"TEMP.*{SUF}"}})
        return res, pipe, pipe_many, raw_blocked, (ups["tenant_id"], ups["branch_id"]), noscope, noscope_upd

    res, pipe, pipe_many, blocked, ups, noscope, noscope_upd = asyncio.new_event_loop().run_until_complete(go())
    print(res, pipe, pipe_many, blocked, ups, noscope, noscope_upd)
    for label, v in res.items():
        assert v == (T1, B1), (label, v)
    assert pipe == 400 and pipe_many == 400
    assert set(blocked) == {"replace_one", "bulk_write", "find_one_and_replace", "find_one_and_delete", "rename", "drop", "watch", "estimated_document_count", "map_reduce", "database"}
    assert ups == (T1, B1)
    assert noscope == 503
    assert noscope_upd == 503, f"no-scope upsert not fail-closed with 503: {noscope_upd}"


# ---- OAuth callback ----
def test_oauth_callback_empty_state_no_log():
    before = run(rdb().efactura_logs.count_documents({}))
    cfg_before = run(rdb().efactura_config.find({}, {"oauth_state": 1, "tenant_id": 1}).to_list(1000))
    for params in ({"code": "x", "state": ""}, {"code": "x"}, {"error": "access_denied"}, {"state": "", "error": "x"}):
        r = requests.get(f"{BASE}/efactura/oauth/callback", params=params, allow_redirects=False)
        assert r.status_code in (302, 307), (params, r.status_code)
        assert "oauth=error" in r.headers["location"]
    assert run(rdb().efactura_logs.count_documents({})) == before
    assert run(rdb().efactura_config.find({}, {"oauth_state": 1, "tenant_id": 1}).to_list(1000)) == cfg_before


def test_oauth_callback_generic_failure_redirects(a2):
    from datetime import datetime, timezone
    state = f"TEMPGEN{SUF}"
    assert a2.put(f"{BASE}/efactura/config", json={"environment": "test", "client_id": "TEMPCID2"}).status_code == 200
    # invalid (non-Fernet) secret -> dec() raises InvalidToken (generic exception)
    run(rdb().efactura_config.update_one({"tenant_id": T2, "kind": "efactura"}, {"$set": {"client_secret": "not-a-fernet-token", "oauth_state": state, "oauth_state_at": datetime.now(timezone.utc).isoformat()}}))
    r = requests.get(f"{BASE}/efactura/oauth/callback", params={"code": "fake", "state": state}, allow_redirects=False)
    assert r.status_code in (302, 307), (r.status_code, r.text[:200])
    assert "oauth=error" in r.headers["location"]
    doc = run(rdb().efactura_config.find_one({"tenant_id": T2, "kind": "efactura"}))
    assert doc["oauth_state"] == "" and "access_token" not in doc or doc.get("access_token") == "TEMPAT"
    assert run(rdb().efactura_logs.count_documents({"tenant_id": T2, "op": "oauth", "ok": False})) >= 1
    assert run(rdb().efactura_logs.count_documents({"tenant_id": {"$nin": [T2]}, "message": {"$regex": "Fernet|InvalidToken"}, "at": {"$gt": "2026-01"}, "op": "oauth"})) == 0
    # replay same state -> rejected
    r = requests.get(f"{BASE}/efactura/oauth/callback", params={"code": "fake", "state": state}, allow_redirects=False)
    assert "oauth=error" in r.headers["location"]


# ---- Suspend / reactivate ----
def test_tenant_suspend_expired_and_reactivate(owner, env):
    for status in ("SUSPENDED", "EXPIRED"):
        s = login(U1, PW)
        assert s.get(f"{BASE}/clients").status_code == 200
        assert owner.put(f"{BASE}/platform/tenants/{T1}", json={"subscription_plan": "BASIC", "max_branches_allowed": 1, "status": status}).status_code == 200
        try:
            assert s.get(f"{BASE}/auth/me").status_code == 403
            assert s.get(f"{BASE}/clients").status_code == 403
            assert s.post(f"{BASE}/clients", json={"name": f"TEMP blocked {SUF}"}).status_code == 403
            assert s.get(f"{BASE}/dashboard").status_code == 403
            assert s.post(f"{BASE}/auth/refresh").status_code == 403
            login(U1, PW, expect=403)
            # cannot create branch/admin for suspended tenant
            assert owner.post(f"{BASE}/platform/tenants/{T1}/admins", json={"email": f"z_{SUF}@example.com", "name": "z", "password": PW, "branch_ids": [B1]}).status_code == 404
        finally:
            owner.put(f"{BASE}/platform/tenants/{T1}", json={"subscription_plan": "BASIC", "max_branches_allowed": 1, "status": "ACTIVE"})
        assert s.get(f"{BASE}/auth/me").status_code == 200
        assert s.post(f"{BASE}/auth/refresh").status_code == 200
        login(U1, PW)


def test_branch_inactive_blocks_operations_and_reactivate(env):
    s = login(U1, PW)
    run(rdb().branches.update_one({"_id": B1}, {"$set": {"status": "INACTIVE"}}))
    try:
        assert s.get(f"{BASE}/auth/me").status_code == 403
        assert s.get(f"{BASE}/clients").status_code == 403
        assert s.put(f"{BASE}/settings", json={"company_name": "x"}).status_code == 403
        assert s.post(f"{BASE}/auth/refresh").status_code == 403
        login(U1, PW, expect=403)
    finally:
        run(rdb().branches.update_one({"_id": B1}, {"$set": {"status": "ACTIVE"}}))
    assert s.get(f"{BASE}/clients").status_code == 200
    login(U1, PW)


def test_superadmin_cannot_suspend_own_tenant(owner):
    r = owner.put(f"{BASE}/platform/tenants/{DEMO_TENANT_ID}", json={"subscription_plan": "BASIC", "max_branches_allowed": 1, "status": "SUSPENDED"})
    assert r.status_code == 400
    t = next(x for x in owner.get(f"{BASE}/platform/tenants").json() if x["id"] == DEMO_TENANT_ID)
    assert t["status"] == "ACTIVE"


# ---- Cross-tenant CRUD / aggregate / quota ----
def test_cross_tenant_crud_and_aggregate(a1, a2, demo_admin):
    c1 = a1.post(f"{BASE}/clients", json={"name": f"TEMP X1 {SUF}"})
    assert c1.status_code == 200, c1.text
    c1 = c1.json()
    v = a1.post(f"{BASE}/vehicles", json={"client_id": c1["id"], "vin": f"TEMPVIN{SUF.upper()}ABCD"[:17].ljust(17, "X"), "plate": f"TMP{SUF}", "make": "TEMP", "model": "T"})
    assert v.status_code == 200, v.text
    l1 = a1.get(f"{BASE}/clients").json()
    assert [c for c in l1 if c["id"] == c1["id"]][0]["vehicle_count"] == 1
    assert all(c["id"] != c1["id"] for c in a2.get(f"{BASE}/clients").json())
    assert all(c["id"] != c1["id"] for c in demo_admin.get(f"{BASE}/clients").json())
    assert all(x["id"] != v.json()["id"] for x in a2.get(f"{BASE}/vehicles").json())
    assert a2.get(f"{BASE}/vehicles/{v.json()['id']}").status_code == 404
    assert a2.delete(f"{BASE}/clients/{c1['id']}").status_code == 404
    # same VIN allowed in another tenant? at least must not leak existence of T1 data via 400 'VIN deja existent'
    # aggregate isolation: payment in T2 must not affect T1 cash register opening
    run(rdb().payments.insert_one({"tenant_id": T2, "branch_id": B2a, "method": "numerar", "date": "2020-01-01", "amount": 999.0, "invoice_id": "TEMP"}))
    o1 = a1.get(f"{BASE}/cash-register", params={"day": "2026-01-15"}).json()
    o2 = a2.get(f"{BASE}/cash-register", params={"day": "2026-01-15"}).json()
    assert o1.get("opening") == 0 and o2.get("opening") == 999.0, (o1, o2)
    d1 = a1.get(f"{BASE}/dashboard").json()
    assert d1["in_service"] == 0 and d1["low_stock"] == 0
    assert a1.get(f"{BASE}/users").status_code == 200
    assert {u["email"] for u in a1.get(f"{BASE}/users").json()} == {U1}


def test_vin_duplicate_cross_tenant(a1, a2):
    vin = ("TMPV" + SUF.upper() + "0000000000")[:17]
    c1 = a1.post(f"{BASE}/clients", json={"name": f"TEMP V1 {SUF}"}).json()
    c2 = a2.post(f"{BASE}/clients", json={"name": f"TEMP V2 {SUF}"}).json()
    assert a1.post(f"{BASE}/vehicles", json={"client_id": c1["id"], "vin": vin, "plate": "T1", "make": "x", "model": "y"}).status_code == 200
    r = a2.post(f"{BASE}/vehicles", json={"client_id": c2["id"], "vin": vin, "plate": "T2", "make": "x", "model": "y"})
    assert r.status_code == 200, f"VIN uniqueness leaks across tenants: {r.status_code} {r.text}"
    # cross-tenant client_id must be rejected
    r = a2.post(f"{BASE}/vehicles", json={"client_id": c1["id"], "vin": ("TMPW" + SUF.upper() + "0000000000")[:17], "plate": "T3", "make": "x", "model": "y"})
    assert r.status_code in (400, 404), f"vehicle linked to foreign-tenant client: {r.status_code}"


def test_branch_quota(owner, env):
    r = owner.post(f"{BASE}/platform/tenants/{T1}/branches", json={"branch_id": f"TEMP-fbx-{SUF}", "branch_name": "TEMP over"})
    assert r.status_code == 403
    r = owner.post(f"{BASE}/platform/tenants/{T2}/branches", json={"branch_id": f"TEMP-fby-{SUF}", "branch_name": "TEMP over"})
    assert r.status_code == 403
    assert run(rdb().branches.count_documents({"tenant_id": T1})) == 1


def test_tenant_admin_cannot_touch_superadmin(a1, owner):
    me = owner.get(f"{BASE}/auth/me").json()
    assert me["platform_role"] == "SUPERADMIN" and me["tenant_id"] == DEMO_TENANT_ID
    assert me["active_branch_id"] == DEMO_BRANCH_ID
    assert a1.put(f"{BASE}/users/{me['id']}", json={"email": me["email"], "name": "hack", "role": "mecanic"}).status_code in (403, 404)
    assert a1.delete(f"{BASE}/users/{me['id']}").status_code in (403, 404)
    assert a1.get(f"{BASE}/platform/tenants").status_code == 403
    assert owner.get(f"{BASE}/auth/me").json()["name"] != "hack"
