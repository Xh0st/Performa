# Iteration 26: P1 fixes - unique sparse subdomain index + clear, logo storage accounting, invoice read overrides
# historical plan/logo snapshot. Needs iter25_fixture.py setup (run in a separate pytest process after iter25/iter25b).
import asyncio
import base64
import json
import os

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
STATE = json.load(open("/tmp/iter25.json"))
T, SUF = STATE["tenants"], STATE["suf"]
LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)
DB = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def run(c):
    return LOOP.run_until_complete(c)


def sess(plan):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {T[plan]['token']}"
    return s


def used(plan):
    return run(DB.tenants.find_one({"_id": T[plan]["id"]})).get("document_storage_used_bytes", 0)


# --- subdomain index ---
def test_subdomain_index_unique_sparse():
    info = run(DB.settings.index_information())
    idx = [v for v in info.values() if v["key"] == [("custom_subdomain", 1)]]
    assert idx and idx[0].get("unique") and idx[0].get("sparse")
    assert run(DB.settings.count_documents({"custom_subdomain": ""})) == 0


def test_subdomain_set_clear_and_reuse():
    full, ent = sess("FULL"), sess("ENTERPRISE")
    sd = f"temp26-{SUF}"
    r = full.put(f"{BASE}/settings", json={"custom_subdomain": sd.upper()})
    assert r.status_code == 200 and r.json().get("custom_subdomain") == sd
    assert ent.put(f"{BASE}/settings", json={"custom_subdomain": sd}).status_code == 400
    # clear -> field unset (not "") so sparse index lets many tenants be empty
    r = full.put(f"{BASE}/settings", json={"custom_subdomain": ""})
    assert r.status_code == 200 and not r.json().get("custom_subdomain")
    doc = run(DB.settings.find_one({"tenant_id": T["FULL"]["id"], "kind": "company"}))
    assert "custom_subdomain" not in doc
    r = ent.put(f"{BASE}/settings", json={"custom_subdomain": ""})
    assert r.status_code == 200
    # now ENTERPRISE can take freed subdomain
    r = ent.put(f"{BASE}/settings", json={"custom_subdomain": sd})
    assert r.status_code == 200 and r.json()["custom_subdomain"] == sd
    # direct DB insert of duplicate violates the index
    with pytest.raises(DuplicateKeyError):
        run(DB.settings.insert_one({"_id": ObjectId(), "tenant_id": "temp26-x", "kind": "x", "custom_subdomain": sd}))
    assert ent.put(f"{BASE}/settings", json={"custom_subdomain": None}).status_code == 200
    assert run(DB.settings.count_documents({"custom_subdomain": sd})) == 0


def test_basic_cannot_set_subdomain_but_can_clear():
    b = sess("BASIC")
    assert b.put(f"{BASE}/settings", json={"custom_subdomain": f"temp26b-{SUF}"}).status_code == 403
    assert b.put(f"{BASE}/settings", json={"custom_subdomain": ""}).status_code == 200


# --- logo storage accounting ---
def test_logo_storage_accounting_no_negative():
    s = sess("FULL")
    s.delete(f"{BASE}/settings/logo")
    run(DB.tenants.update_one({"_id": T["FULL"]["id"]}, {"$set": {"document_storage_used_bytes": 1000}}))
    data = "data:image/png;base64," + base64.b64encode(PNG).decode()
    assert s.put(f"{BASE}/settings/logo", json={"data_url": data}).status_code == 200
    assert used("FULL") == 1000 + len(PNG)
    # replace with same logo -> no double counting
    assert s.put(f"{BASE}/settings/logo", json={"data_url": data}).status_code == 200
    assert used("FULL") == 1000 + len(PNG)
    assert s.delete(f"{BASE}/settings/logo").status_code == 200
    assert used("FULL") == 1000
    # counter lower than logo size -> clamps to 0
    s.put(f"{BASE}/settings/logo", json={"data_url": data})
    run(DB.tenants.update_one({"_id": T["FULL"]["id"]}, {"$set": {"document_storage_used_bytes": 10}}))
    assert s.delete(f"{BASE}/settings/logo").status_code == 200
    assert used("FULL") == 0
    # double delete stays 0
    assert s.delete(f"{BASE}/settings/logo").status_code == 200
    assert used("FULL") == 0


def test_logo_storage_limit_enforced():
    s = sess("FULL")
    run(DB.tenants.update_one({"_id": T["FULL"]["id"]}, {"$set": {"document_storage_used_bytes": 10 * 1024 ** 3}}))
    data = "data:image/png;base64," + base64.b64encode(PNG).decode()
    r = s.put(f"{BASE}/settings/logo", json={"data_url": data})
    assert r.status_code == 403
    run(DB.tenants.update_one({"_id": T["FULL"]["id"]}, {"$set": {"document_storage_used_bytes": 0}}))


# --- invoice read overrides historical snapshot ---
def test_invoice_get_overrides_historical_plan_and_logo():
    full, basic = sess("FULL"), sess("BASIC")
    fid, bid = T["FULL"]["docs"]["fiscal"], T["BASIC"]["docs"]["fiscal"]
    run(DB.invoices.update_one({"_id": ObjectId(fid)}, {"$set": {
        "seller.subscription_plan": "BASIC", "seller.custom_logo_data_url": "data:image/png;base64,OLD"}}))
    run(DB.invoices.update_one({"_id": ObjectId(bid)}, {"$set": {
        "seller.subscription_plan": "ENTERPRISE", "seller.custom_logo_data_url": "data:image/png;base64,OLD"}}))
    data = "data:image/png;base64," + base64.b64encode(PNG).decode()
    assert full.put(f"{BASE}/settings/logo", json={"data_url": data}).status_code == 200
    inv = full.get(f"{BASE}/invoices/{fid}").json()
    assert inv["seller"]["subscription_plan"] == "FULL"
    assert inv["seller"]["custom_logo_data_url"] == data
    inv = basic.get(f"{BASE}/invoices/{bid}").json()
    assert inv["seller"]["subscription_plan"] == "BASIC"
    assert "custom_logo_data_url" not in inv["seller"]
    # FULL without logo -> empty string, not stale
    full.delete(f"{BASE}/settings/logo")
    inv = full.get(f"{BASE}/invoices/{fid}").json()
    assert inv["seller"]["custom_logo_data_url"] == ""


def test_basic_nir_forbidden():
    r = sess("BASIC").get(f"{BASE}/nirs/{T['BASIC']['docs']['nir']}")
    assert r.status_code == 403
    assert r.json().get("detail")
