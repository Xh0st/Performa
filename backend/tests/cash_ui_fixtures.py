# TEST fixture builder/cleaner for Cash page UI tests. CLI: python cash_ui_fixtures.py setup|teardown (state in /tmp/cash_ui_state.json)
import json
import os
import sys
from datetime import datetime, timezone

import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
STATE = "/tmp/cash_ui_state.json"
COUNTERS = ["pay_chitanta", "pay_bon_fiscal", "pay_bon_pos", "pay_ordin_plata", "pay_confirmare_online", "cash_deposit"]


def creds():
    line = [ln for ln in open("/app/memory/test_credentials.md").read().splitlines() if "andrei.melek" in ln][0]
    em, pw = [x.strip() for x in line.lstrip("- ").split("/")[:2]]
    return em, pw.split()[0]


def setup():
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    s = requests.Session()
    em, pw = creds()
    user = s.post(f"{BASE}/auth/login", json={"email": em, "password": pw}).json()["user"]
    tid, bid = user["tenant_id"], user["active_branch_id"]
    st = {"tid": tid, "bid": bid, "counters": {c: (db.counters.find_one({"_id": f"{tid}:{bid}:{c}"}) or {}).get("seq") for c in COUNTERS},
          "deposits_before": [str(d["_id"]) for d in db.cash_movements.find({}, {"_id": 1})]}
    pf = s.post(f"{BASE}/clients", json={"type": "pf", "name": "TEST_UI PF Casa"}).json()
    pj = s.post(f"{BASE}/clients", json={"type": "pj", "name": "TEST_UI PJ Casa", "cui": "RO99887766"}).json()
    st["clients"] = [pf["id"], pj["id"]]
    st["pf"], st["pj"] = pf["id"], pj["id"]
    inv = []
    for cid, gross, due, num in [(pf["id"], 100.0, "2026-01-05", "U1"), (pf["id"], 200.0, "2026-02-05", "U2"), (pj["id"], 500.0, "2026-01-05", "U3")]:
        doc = {"type": "fiscal", "series": "TSTU", "number": num, "issue_date": "2026-01-01", "due_date": due, "client_id": cid,
               "buyer": {"name": "TEST"}, "lines": [], "totals": {"net": round(gross / 1.21, 2), "vat": round(gross - gross / 1.21, 2), "gross": gross},
               "paid_amount": 0.0, "status": "unpaid", "efactura": {"status": "not_sent", "history": []},
               "created_at": datetime.now(timezone.utc).isoformat(), "tenant_id": tid, "branch_id": bid}
        inv.append(str(db.invoices.insert_one(doc).inserted_id))
    st["invoices"] = inv
    json.dump(st, open(STATE, "w"))
    print(json.dumps({k: v for k, v in st.items() if k != "counters"}))


def teardown():
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    st = json.load(open(STATE))
    pays = [str(p["_id"]) for p in db.payments.find({"client_id": {"$in": st["clients"]}}, {"_id": 1})]
    new_deps = [d["_id"] for d in db.cash_movements.find({"reference": {"$regex": "^TEST_"}}, {"_id": 1})
                if str(d["_id"]) not in st["deposits_before"]]
    print("payments", db.payments.delete_many({"client_id": {"$in": st["clients"]}}).deleted_count)
    print("invoices", db.invoices.delete_many({"_id": {"$in": [ObjectId(i) for i in st["invoices"]]}}).deleted_count)
    print("deposits", db.cash_movements.delete_many({"_id": {"$in": new_deps}}).deleted_count)
    print("clients", db.clients.delete_many({"_id": {"$in": [ObjectId(i) for i in st["clients"]]}}).deleted_count)
    db.audit_logs.delete_many({"entity_id": {"$in": st["clients"] + pays + [str(d) for d in new_deps]}})
    for c, v in st["counters"].items():
        key = f"{st['tid']}:{st['bid']}:{c}"
        if v is None:
            db.counters.delete_one({"_id": key})
        else:
            db.counters.update_one({"_id": key}, {"$set": {"seq": v}})


if __name__ == "__main__":
    setup() if sys.argv[1] == "setup" else teardown()
