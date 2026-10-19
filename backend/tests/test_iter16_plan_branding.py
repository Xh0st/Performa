# Iteration 16: BASIC/FULL plan enforcement (permissions, FULL-only API gating, 3 active users,
# 1000 WO/month quota without cross-tenant leakage, custom_subdomain rules) + Performa PDF branding/footer.
import asyncio
import os
import re
import sys
import uuid
from datetime import datetime, timezone

import fitz  # pymupdf
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
PW = "TempInit2026!"
NEW_PW = "TempNew2026!x"
FOOTER = "Generat cu Performa - performa.net"
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
        s.login_json = r.json()
    return s


def pdf_text(content: bytes) -> str:
    doc = fitz.open(stream=content, filetype="pdf")
    return "\n".join(p.get_text() for p in doc)


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
    s = login(body["admin_email"], PW)
    r = s.post(f"{BASE}/auth/change-initial-password", json={"current_password": PW, "new_password": NEW_PW})
    assert r.status_code == 200, r.text
    s.change_json = r.json()
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    s.tenant = t
    s.email = body["admin_email"]
    return s


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
def basic(owner):
    return make_tenant(owner, "BASIC", "basic")


@pytest.fixture(scope="module")
def basic2(owner):
    return make_tenant(owner, "BASIC", "basicb")


@pytest.fixture(scope="module")
def full(owner):
    return make_tenant(owner, "FULL", "full")


FULL_ONLY_GET = ["/appointments", "/products", "/suppliers", "/nirs", "/supplier-returns",
                 "/efactura/config", "/efactura/inbox", "/efactura/logs", "/rar-autopass/config",
                 "/rar-autopass/outbox", "/rar-autopass/logs"]


# --- 1. permissions + gating ---
def test_basic_me_plan_and_permissions(basic):
    me = basic.get(f"{BASE}/auth/me").json()
    assert me["subscription_plan"] == "BASIC"
    assert "planning" not in me["permissions"] and "stock" not in me["permissions"]
    assert "workorders" in me["permissions"] and "settings" in me["permissions"]
    assert basic.get(f"{BASE}/settings").json()["subscription_plan"] == "BASIC"


def test_basic_full_only_apis_403(basic):
    for p in FULL_ONLY_GET:
        r = basic.get(f"{BASE}{p}")
        assert r.status_code == 403, f"{p} -> {r.status_code}"
    assert basic.post(f"{BASE}/appointments", json={}).status_code == 403
    assert basic.post(f"{BASE}/invoices/000000000000000000000000/efactura/validate").status_code == 403
    assert basic.put(f"{BASE}/rar-autopass/config", json={}).status_code == 403


def test_full_me_and_apis_allowed(full):
    me = full.get(f"{BASE}/auth/me").json()
    assert me["subscription_plan"] == "FULL"
    assert "planning" in me["permissions"] and "stock" in me["permissions"]
    for p in ["/appointments?start=2026-01-01T00:00:00%2B00:00&end=2026-01-31T00:00:00%2B00:00", "/products", "/suppliers", "/nirs", "/efactura/config", "/rar-autopass/config"]:
        r = full.get(f"{BASE}{p}")
        assert r.status_code == 200, f"{p} -> {r.status_code} {r.text[:120]}"


def test_full_login_and_change_password_response_permissions(owner, full):
    # frontend changeInitialPassword uses data.user directly -> must reflect FULL plan
    assert "planning" in full.change_json["user"]["permissions"], "change-initial-password user.permissions ignores FULL plan"


def test_full_login_response_permissions(full):
    s = login(full.email, NEW_PW)
    assert "planning" in s.login_json["user"]["permissions"], "login user.permissions ignores FULL plan"


# --- 2. user limit ---
def _user(s, tag, active=True):
    return s.post(f"{BASE}/users", json={"email": f"temp_u{tag}_{SUF}@example.com", "name": f"TEMP u{tag}",
                                          "role": "receptioner", "password": "TempUser2026!", "active": active})


def test_basic_user_limit_create_and_reactivate(basic):
    assert _user(basic, "b1").status_code == 200
    assert _user(basic, "b2").status_code == 200
    r = _user(basic, "b3")
    assert r.status_code == 403 and "3" in r.json()["detail"]
    inactive = _user(basic, "b4", active=False)
    assert inactive.status_code == 200, inactive.text
    iid = inactive.json()["id"]
    body = {"email": f"temp_ub4_{SUF}@example.com", "name": "TEMP ub4", "role": "receptioner", "active": True}
    assert basic.put(f"{BASE}/users/{iid}", json=body).status_code == 403
    d = rdb()
    assert run(d.users.count_documents({"tenant_id": basic.tenant["id"], "active": True})) == 3
    # editing an already-active user at the limit is allowed
    users = basic.get(f"{BASE}/users").json()
    b1 = next(u for u in users if u["email"].startswith("temp_ub1_"))
    assert basic.put(f"{BASE}/users/{b1['id']}", json={"email": b1["email"], "name": "TEMP ub1 edit",
                                                      "role": "receptioner", "active": True}).status_code == 200
    # deactivate one, then reactivation of another works
    assert basic.put(f"{BASE}/users/{b1['id']}", json={"email": b1["email"], "name": "x", "role": "receptioner",
                                                      "active": False}).status_code == 200
    assert basic.put(f"{BASE}/users/{iid}", json=body).status_code == 200


def test_full_no_user_limit(full):
    for i in range(4):
        assert _user(full, f"f{i}").status_code == 200


# --- 3. WO quota ---
def _client_vehicle(s, tag):
    c = s.post(f"{BASE}/clients", json={"name": f"TEMP client {tag} {SUF}", "type": "pf", "phone": "0700000000"})
    assert c.status_code in (200, 201), c.text
    vin = ("TMPVIN" + uuid.uuid4().hex.upper())[:17]
    v = s.post(f"{BASE}/vehicles", json={"client_id": c.json()["id"], "vin": vin, "plate": f"B{SUF[:3]}TMP",
                                          "make": "Dacia", "model": "Logan"})
    assert v.status_code in (200, 201), v.text
    return c.json()["id"], v.json()["id"]


def _wo(s, cid, vid):
    return s.post(f"{BASE}/work-orders", json={"client_id": cid, "vehicle_id": vid, "mileage_in": 1000,
                                                "complaint": "TEMP", "photos": {}, "signature": "data:image/png;base64,AA"})


def _fill(tenant_id, n):
    d = rdb()
    br = run(d.branches.find_one({"tenant_id": tenant_id}))
    month = datetime.now(timezone.utc).isoformat()
    run(d.work_orders.insert_many([{"number": f"TEMP-Q-{i}", "tenant_id": tenant_id, "branch_id": br["_id"],
                                    "status": "noua", "created_at": month, "lines": []} for i in range(n)]))


def test_basic_wo_quota_and_isolation(basic, basic2, full):
    cid, vid = _client_vehicle(basic, "q")
    assert _wo(basic, cid, vid).status_code == 200
    _fill(basic.tenant["id"], 999)
    r = _wo(basic, cid, vid)
    assert r.status_code == 403 and "1.000" in r.json()["detail"]
    # another BASIC tenant unaffected
    cid2, vid2 = _client_vehicle(basic2, "q2")
    assert _wo(basic2, cid2, vid2).status_code == 200
    # FULL with >1000 unaffected
    _fill(full.tenant["id"], 1000)
    cid3, vid3 = _client_vehicle(full, "q3")
    assert _wo(full, cid3, vid3).status_code == 200


def test_quota_ignores_previous_month(basic2):
    d = rdb()
    br = run(d.branches.find_one({"tenant_id": basic2.tenant["id"]}))
    run(d.work_orders.insert_many([{"number": f"TEMP-OLD-{i}", "tenant_id": basic2.tenant["id"], "branch_id": br["_id"],
                                    "created_at": "2020-01-15T10:00:00+00:00"} for i in range(1000)]))
    cid, vid = _client_vehicle(basic2, "old")
    assert _wo(basic2, cid, vid).status_code == 200


# --- 4. settings subdomain ---
def test_basic_cannot_set_subdomain_or_upgrade(basic):
    r = basic.put(f"{BASE}/settings", json={"name": "TEMP basic", "custom_subdomain": "abc"})
    assert r.status_code == 403
    r = basic.put(f"{BASE}/settings", json={"name": "TEMP basic", "subscription_plan": "FULL", "custom_subdomain": ""})
    assert r.status_code == 200 and r.json()["subscription_plan"] == "BASIC"
    assert run(rdb().tenants.find_one({"_id": basic.tenant["id"]}))["subscription_plan"] == "BASIC"
    assert not basic.get(f"{BASE}/settings").json().get("custom_subdomain")


@pytest.mark.parametrize("bad", ["Bad_Sub", "-abc", "abc-", "a.b", "x" * 64, "ab c", "ăbc"])
def test_full_invalid_subdomain(full, bad):
    assert full.put(f"{BASE}/settings", json={"custom_subdomain": bad}).status_code == 400


def test_full_valid_subdomain(full):
    r = full.put(f"{BASE}/settings", json={"custom_subdomain": "  Temp-Sub1 "})
    assert r.status_code == 200, r.text
    assert full.get(f"{BASE}/settings").json()["custom_subdomain"] == "temp-sub1"


def test_subdomain_uniqueness_across_tenants(owner, full):
    other = make_tenant(owner, "FULL", "fullb")
    r = other.put(f"{BASE}/settings", json={"custom_subdomain": "temp-sub1"})
    assert r.status_code in (400, 409), f"duplicate subdomain accepted ({r.status_code})"


def test_downgraded_tenant_can_still_save_settings(owner, full):
    # UI sends full settings object (incl. stored custom_subdomain) on every save
    t = full.tenant
    settings_now = full.get(f"{BASE}/settings").json()
    assert settings_now.get("custom_subdomain") == "temp-sub1"
    r = owner.put(f"{BASE}/platform/tenants/{t['id']}", json={"subscription_plan": "BASIC", "max_branches_allowed": 5, "status": "ACTIVE"})
    assert r.status_code == 200
    try:
        body = full.get(f"{BASE}/settings").json() | {"name": "TEMP after downgrade"}
        r = full.put(f"{BASE}/settings", json=body)
        assert r.status_code == 200, f"downgraded tenant blocked from saving settings: {r.status_code} {r.text}"
    finally:
        owner.put(f"{BASE}/platform/tenants/{t['id']}", json={"subscription_plan": "FULL", "max_branches_allowed": 5, "status": "ACTIVE"})


# --- 5. PDFs ---
def test_anexa5_pdf_basic_footer(basic):
    r = basic.get(f"{BASE}/reports/final-inspections/pdf", params={"start": "2026-01-01", "end": "2026-01-31"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/pdf")
    t = pdf_text(r.content)
    assert "Performa" in t and FOOTER in t


def test_anexa5_pdf_full_no_footer(full):
    r = full.get(f"{BASE}/reports/final-inspections/pdf", params={"start": "2026-01-01", "end": "2026-01-31"})
    assert r.status_code == 200
    t = pdf_text(r.content)
    assert "Performa" in t and FOOTER not in t and "performa.net" not in t


def test_warranty_certificate_basic_endpoint():
    demo = login("admin@serviceauto.ro", ADMIN_PW)
    cert = run(rdb().warranty_certificates.find_one({}))
    if not cert:
        pytest.skip("no warranty certificate in demo data")
    r = demo.get(f"{BASE}/warranties/invoices/{cert['invoice_id']}/certificate")
    assert r.status_code == 200, r.text
    t = pdf_text(r.content)
    assert "Performa" in t and FOOTER in t


def test_warranty_and_efactura_pdf_builders_full_vs_basic():
    from warranty_pdf import build_certificate
    from efactura_pdf import render_pdf
    cert = run(rdb().warranty_certificates.find_one({}))
    if cert:
        tb = pdf_text(build_certificate(cert, include_footer=True))
        tf = pdf_text(build_certificate(cert, include_footer=False))
        assert FOOTER in tb and "Performa" in tf and FOOTER not in tf
    m = run(rdb().efactura_inbox.find_one({"xml": {"$exists": True}}))
    if not m:
        pytest.skip("no efactura inbox xml")
    tb = pdf_text(render_pdf(m["xml"], m, include_footer=True))
    tf = pdf_text(render_pdf(m["xml"], m, include_footer=False))
    assert "Performa" in tb and FOOTER in tb
    assert "Performa" in tf and FOOTER not in tf


def test_efactura_inbox_pdf_endpoint_blocked_for_basic():
    demo = login("admin@serviceauto.ro", ADMIN_PW)
    m = run(rdb().efactura_inbox.find_one({}))
    if not m:
        pytest.skip("no inbox")
    assert demo.get(f"{BASE}/efactura/inbox/{m['_id']}/pdf").status_code == 403
