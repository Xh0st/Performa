# Iteration 18: settings save with missing labor_rates/elevators + custom logo upload (FULL vs BASIC gating)
import asyncio
import base64
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
SUF = uuid.uuid4().hex[:6]
PW = "TempInit2026!"
NEW_PW = "TempNew2026!x"
LOOP = asyncio.new_event_loop()
_cli = None
CREATED = []
# 1x1 PNG
PNG = base64.b64encode(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")).decode()
PNG_URL = f"data:image/png;base64,{PNG}"


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


def make_tenant(owner, plan, tag):
    body = {"company_name": f"TEST-{tag}-{SUF} SRL", "cui": f"RO-TEST{tag}{SUF}".upper(),
            "admin_email": f"test_{tag}_{SUF}@example.com", "initial_password": PW, "subscription_plan": plan}
    r = owner.post(f"{BASE}/platform/tenants", json=body)
    assert r.status_code == 200, r.text
    t = r.json()
    CREATED.append(t["id"])
    s = login(body["admin_email"], PW)
    r = s.post(f"{BASE}/auth/change-initial-password", json={"current_password": PW, "new_password": NEW_PW})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    s.tenant = t
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
            for col in OPERATIONAL_COLLECTIONS | {"cron_errors", "settings", "audit_logs"}:
                await d[col].delete_many({"tenant_id": tid})
            await d.users.delete_many({"tenant_id": tid})
            await d.branches.delete_many({"tenant_id": tid})
            await d.counters.delete_many({"_id": {"$regex": f"^{re.escape(tid)}:"}})
            await d.tenants.delete_one({"_id": tid})
        await d.users.delete_many({"email": {"$regex": f"_{SUF}@example.com$"}})
        await d.login_attempts.delete_many({"identifier": {"$regex": SUF}})
    run(_c())


@pytest.fixture(scope="module")
def full(owner):
    return make_tenant(owner, "FULL", "full")


@pytest.fixture(scope="module")
def basic(owner):
    return make_tenant(owner, "BASIC", "basic")


def _settings_doc(tid):
    return run(rdb().settings.find_one({"tenant_id": tid, "kind": "company"}))


# --- settings save with sparse doc ---
def test_full_settings_get_sparse(full):
    r = full.get(f"{BASE}/settings")
    assert r.status_code == 200
    d = r.json()
    assert d["subscription_plan"] == "FULL"
    print("sparse settings keys:", sorted(d.keys()))


def test_full_save_without_labor_rates_elevators(full):
    body = {"name": "TEST Firma", "elevators": [], "labor_rates": {}, "vat_rate": 21, "payment_terms_days": 30}
    r = full.put(f"{BASE}/settings", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "TEST Firma"
    doc = _settings_doc(full.tenant["id"])
    assert doc["name"] == "TEST Firma" and doc["elevators"] == [] and doc["labor_rates"] == {}


def test_full_save_strips_scope_and_plan(full):
    body = {"name": "TEST Firma2", "tenant_id": "tenant-evil", "branch_id": "branch-evil", "_id": "x",
            "subscription_plan": "ENTERPRISE"}
    r = full.put(f"{BASE}/settings", json=body)
    assert r.status_code == 200, r.text
    doc = _settings_doc(full.tenant["id"])
    assert doc["tenant_id"] == full.tenant["id"]
    assert doc.get("branch_id") != "branch-evil"
    assert "subscription_plan" not in doc
    assert run(rdb().tenants.find_one({"_id": full.tenant["id"]}))["subscription_plan"] == "FULL"


def test_full_save_with_plan_limits_echo_not_persisted(full):
    # frontend sends the whole GET payload back, including plan_limits
    s = full.get(f"{BASE}/settings").json()
    r = full.put(f"{BASE}/settings", json=s)
    assert r.status_code == 200, r.text
    doc = _settings_doc(full.tenant["id"])
    assert "plan_limits" not in doc, "plan_limits (derived field) persisted into settings doc"


def test_full_null_custom_subdomain(full):
    r = full.put(f"{BASE}/settings", json={"custom_subdomain": None})
    assert r.status_code == 200, r.text
    doc = _settings_doc(full.tenant["id"])
    assert doc.get("custom_subdomain") in (None, ""), f"null subdomain stored as {doc.get('custom_subdomain')!r}"


# --- logo upload ---
def test_full_logo_upload_png(full):
    r = full.put(f"{BASE}/settings/logo", json={"data_url": PNG_URL})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["custom_logo_data_url"] == PNG_URL and d["custom_logo_mime"] == "image/png"
    assert full.get(f"{BASE}/settings").json()["custom_logo_data_url"] == PNG_URL


@pytest.mark.parametrize("mime", ["jpeg", "webp"])
def test_full_logo_upload_other_mimes(full, mime):
    r = full.put(f"{BASE}/settings/logo", json={"data_url": f"data:image/{mime};base64,{PNG}"})
    assert r.status_code == 200, r.text
    assert r.json()["custom_logo_mime"] == f"image/{mime}"


@pytest.mark.parametrize("url", ["data:image/gif;base64,R0lGOD", "data:image/png;base64,@@@", "notadataurl",
                                 "data:image/png;base64,"])
def test_full_logo_invalid(full, url):
    r = full.put(f"{BASE}/settings/logo", json={"data_url": url})
    assert r.status_code in (400, 422), r.text


def test_full_logo_too_big(full):
    big = base64.b64encode(b"\0" * (1024 * 1024 + 10)).decode()
    r = full.put(f"{BASE}/settings/logo", json={"data_url": f"data:image/png;base64,{big}"})
    assert r.status_code in (400, 413, 422), r.status_code


def test_full_save_after_logo_keeps_logo(full):
    s = full.get(f"{BASE}/settings").json()
    s["name"] = "TEST after logo"
    r = full.put(f"{BASE}/settings", json=s)
    assert r.status_code == 200
    assert r.json().get("custom_logo_data_url")


# --- BASIC ---
def test_basic_logo_403(basic):
    r = basic.put(f"{BASE}/settings/logo", json={"data_url": PNG_URL})
    assert r.status_code == 403, r.text
    doc = _settings_doc(basic.tenant["id"]) or {}
    assert "custom_logo_data_url" not in doc


def test_basic_settings_save_ok(basic):
    r = basic.put(f"{BASE}/settings", json={"name": "TEST basic", "elevators": [], "labor_rates": {}})
    assert r.status_code == 200, r.text
    assert r.json()["subscription_plan"] == "BASIC"


def test_basic_can_inject_logo_via_settings_put(basic):
    # PUT /settings accepts arbitrary dict -> could BASIC bypass logo gating?
    r = basic.put(f"{BASE}/settings", json={"custom_logo_data_url": PNG_URL})
    doc = _settings_doc(basic.tenant["id"]) or {}
    assert "custom_logo_data_url" not in doc, "BASIC can set custom_logo_data_url via PUT /settings (gating bypass)"
