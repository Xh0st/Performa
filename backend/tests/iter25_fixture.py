# Iteration 25 fixture: TEMP BASIC/FULL/ENTERPRISE tenants + copied print docs (invoice/proforma/storno/NIR/WO quote,
# warranty certificate, e-Factura inbox message). Usage: python iter25_fixture.py setup|teardown. State: /tmp/iter25.json
import asyncio
import json
import os
import re
import sys
import uuid

import requests
from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
sys.path.insert(0, "/app/backend")
from tenant_context import OPERATIONAL_COLLECTIONS  # noqa: E402

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
STATE = "/tmp/iter25.json"
_txt = open("/app/memory/test_credentials.md").read()
OWNER_PW = re.search(r"andrei\.melek@gmail\.com / (\S+)", _txt).group(1)
PW = "TempInit2026!"
NEW_PW = "TempNew2026!x"


def db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def login(email, pw):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    return r.json()["token"]


async def copy_docs(d, tid, bid):
    ids = {}
    queries = {
        "fiscal": ("invoices", {"type": "fiscal", "kind": {"$ne": "credit_note"}}),
        "proforma": ("invoices", {"type": "proforma"}),
        "storno": ("invoices", {"kind": "credit_note"}),
        "nir": ("nirs", {}),
        "quote_wo": ("work_orders", {"quotes.0": {"$exists": True}}),
        "warranty": ("warranty_certificates", {}),
        "efactura": ("efactura_inbox", {"xml": {"$exists": True}}),
    }
    for key, (col, q) in queries.items():
        src = await d[col].find_one(q)
        if not src:
            continue
        doc = dict(src)
        doc["_id"] = ObjectId()
        doc["tenant_id"], doc["branch_id"] = tid, bid
        doc["temp_iter25"] = True
        if key == "warranty":
            doc["invoice_id"] = f"temp25-{uuid.uuid4().hex[:8]}"
        if col == "work_orders":
            doc["created_at"] = "2000-01-01T00:00:00+00:00"  # do not count towards monthly quota
        await d[col].insert_one(doc)
        ids[key] = doc["invoice_id"] if key == "warranty" else str(doc["_id"])
    return ids


def setup():
    suf = uuid.uuid4().hex[:6]
    owner = login("andrei.melek@gmail.com", OWNER_PW)
    h = {"Authorization": f"Bearer {owner}"}
    state = {"suf": suf, "tenants": {}}
    d = db()
    for plan in ("BASIC", "FULL", "ENTERPRISE"):
        email = f"temp25_{plan.lower()}_{suf}@example.com"
        body = {"company_name": f"TEMP25-{plan}-{suf} SRL", "cui": f"RO-TEMP25{plan}{suf}".upper(),
                "admin_email": email, "initial_password": PW, "subscription_plan": plan}
        r = requests.post(f"{BASE}/platform/tenants", json=body, headers=h)
        r.raise_for_status()
        t = r.json()
        tok = login(email, PW)
        r = requests.post(f"{BASE}/auth/change-initial-password", json={"current_password": PW, "new_password": NEW_PW},
                          headers={"Authorization": f"Bearer {tok}"})
        r.raise_for_status()
        tok = r.json()["token"]
        requests.put(f"{BASE}/settings", json={"name": body["company_name"], "cui": body["cui"]},
                     headers={"Authorization": f"Bearer {tok}"}).raise_for_status()
        br = asyncio.get_event_loop().run_until_complete(d.branches.find_one({"tenant_id": t["id"]}))
        ids = asyncio.get_event_loop().run_until_complete(copy_docs(d, t["id"], br["_id"]))
        state["tenants"][plan] = {"id": t["id"], "email": email, "token": tok, "branch_id": br["_id"],
                                  "company": body["company_name"], "docs": ids}
    json.dump(state, open(STATE, "w"))
    print(json.dumps({p: {"id": v["id"], "docs": v["docs"]} for p, v in state["tenants"].items()}, indent=1))


async def _teardown():
    d = db()
    tids = [t["_id"] async for t in d.tenants.find({"company_name": {"$regex": "^TEMP25-"}})]
    for tid in tids:
        for col in OPERATIONAL_COLLECTIONS | {"cron_errors"}:
            await d[col].delete_many({"tenant_id": tid})
        await d.users.delete_many({"tenant_id": tid})
        await d.branches.delete_many({"tenant_id": tid})
        await d.counters.delete_many({"_id": {"$regex": f"^{re.escape(tid)}:"}})
        await d.tenants.delete_one({"_id": tid})
    await d.users.delete_many({"email": {"$regex": "^temp25_"}})
    await d.login_attempts.delete_many({"identifier": {"$regex": "temp25_"}})
    left = await d.tenants.count_documents({"company_name": {"$regex": "^TEMP25-"}})
    print(f"teardown: removed {len(tids)} tenants, left={left}")


if __name__ == "__main__":
    if sys.argv[1] == "setup":
        setup()
    else:
        asyncio.get_event_loop().run_until_complete(_teardown())
