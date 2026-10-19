# Iteration 25b supplement: WO monthly quota counted per TENANT (across branches), custom_subdomain uniqueness,
# historical invoice read enrichment. Needs iter25_fixture.py setup + test_iter25_plan_matrix_branding.py run first.
import asyncio
import json
import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
STATE = json.load(open("/tmp/iter25.json"))
T, SUF = STATE["tenants"], STATE["suf"]
LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)
DB = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def run(c):
    return LOOP.run_until_complete(c)


def sess(plan):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {T[plan]['token']}"
    return s


def _cv(s, tag):
    c = s.post(f"{BASE}/clients", json={"name": f"TEMP25 client {tag}", "type": "pf", "phone": "0700000001"}).json()
    vin = (f"TMP25X{tag}{SUF}" + "0" * 17)[:17].upper()
    v = s.post(f"{BASE}/vehicles", json={"client_id": c["id"], "vin": vin, "plate": f"B25X{tag[:2]}",
                                          "make": "Dacia", "model": "Logan"}).json()
    return c["id"], v["id"]


def _wo(s, cid, vid):
    return s.post(f"{BASE}/work-orders", json={"client_id": cid, "vehicle_id": vid, "mileage_in": 1000,
                                                "complaint": "TEMP25", "photos": {}, "signature": "data:image/png;base64,AA"})


# --- WO quota is tenant-scoped: 4999 WOs on ANOTHER branch of FULL tenant + new WO on main branch
def test_wo_quota_counts_all_branches():
    t = T["FULL"]
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    run(DB.work_orders.delete_many({"tenant_id": t["id"], "created_at": {"$regex": f"^{month}"}}))
    other = f"temp25-br-full-2-{SUF}"
    assert run(DB.branches.find_one({"_id": other, "tenant_id": t["id"]})), "second FULL branch missing"
    now = datetime.now(timezone.utc).isoformat()
    run(DB.work_orders.insert_many([{"number": f"TEMP25-XB-{i}", "tenant_id": t["id"], "branch_id": other,
                                     "status": "noua", "created_at": now, "lines": [], "temp_iter25": True}
                                    for i in range(4999)]))
    s = sess("FULL")
    cid, vid = _cv(s, "FX")
    r = _wo(s, cid, vid)
    assert r.status_code in (200, 201), r.text
    assert r.json().get("branch_id") != other
    r = _wo(s, cid, vid)
    assert r.status_code == 403 and "5000" in r.json()["detail"], r.text


# --- custom_subdomain unique across tenants (case-insensitive)
def test_subdomain_unique_across_tenants():
    sub = f"temp25-full-{SUF}"
    assert sess("FULL").put(f"{BASE}/settings", json={"custom_subdomain": sub}).status_code == 200
    r = sess("ENTERPRISE").put(f"{BASE}/settings", json={"custom_subdomain": sub.upper()})
    assert r.status_code in (400, 409), r.text
    r = sess("ENTERPRISE").put(f"{BASE}/settings", json={"custom_subdomain": "Bad_Sub!"})
    assert r.status_code == 400
    # same tenant can re-save own subdomain
    assert sess("FULL").put(f"{BASE}/settings", json={"custom_subdomain": sub}).status_code == 200


# --- historical invoice (no plan/logo in seller snapshot) enriched on read
def test_historical_invoice_enriched_on_read():
    for plan in ("BASIC", "FULL"):
        iid = T[plan]["docs"]["fiscal"]
        from bson import ObjectId
        run(DB.invoices.update_one({"_id": ObjectId(iid)},
                                   {"$unset": {"seller.subscription_plan": "", "seller.custom_logo_data_url": ""}}))
        seller = sess(plan).get(f"{BASE}/invoices/{iid}").json()["seller"]
        assert seller["subscription_plan"] == plan
        if plan == "BASIC":
            assert not seller.get("custom_logo_data_url")
        else:
            assert seller["custom_logo_data_url"].startswith("data:image/")
