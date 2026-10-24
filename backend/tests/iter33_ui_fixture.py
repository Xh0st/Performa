# Iter33 UI fixture: PF client + 2 fiscal invoices (setup) / remove everything created (teardown).
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
STATE = "/tmp/iter33_ui_state.json"
COUNTERS = ["pay_chitanta", "cash_expense_settlement", "cash_payment_order"]


def login():
    line = [ln for ln in open("/app/memory/test_credentials.md").read().splitlines() if "andrei.melek" in ln][0]
    em, pw = [x.strip() for x in line.lstrip("- ").split("/")[:2]]
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": em, "password": pw.split()[0]})
    r.raise_for_status()
    return s, r.json()["user"]


db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
if sys.argv[1] == "setup":
    s, user = login()
    tid, bid = user["tenant_id"], user["active_branch_id"]
    c = s.post(f"{BASE}/clients", json={"type": "pf", "name": "TEST_UI33 Bon", "phone": "0700000034"}).json()
    invs = []
    for i, gross in enumerate([120.0, 80.0, 300.0]):
        invs.append(str(db.invoices.insert_one({
            "type": "fiscal", "series": "TSTU", "number": f"33{i}", "issue_date": "2026-01-01", "due_date": "2026-01-02",
            "client_id": c["id"], "buyer": {"name": "TEST"}, "lines": [],
            "totals": {"net": gross, "vat": 0, "gross": gross}, "paid_amount": 0.0, "status": "unpaid",
            "efactura": {"status": "not_sent", "history": []}, "created_at": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tid, "branch_id": bid}).inserted_id))
    state = {"client": c["id"], "invoices": invs, "tid": tid, "bid": bid,
             "moves": [str(m["_id"]) for m in db.cash_movements.find({}, {"_id": 1})],
             "counters": {k: (db.counters.find_one({"_id": f"{tid}:{bid}:{k}"}) or {}).get("seq") for k in COUNTERS}}
    json.dump(state, open(STATE, "w"))
    print(json.dumps({"client": c["id"], "invoices": invs}))
else:
    st = json.load(open(STATE))
    pay_ids = [str(p["_id"]) for p in db.payments.find({"client_id": st["client"]}, {"_id": 1})]
    new_moves = [m["_id"] for m in db.cash_movements.find({}, {"_id": 1}) if str(m["_id"]) not in st["moves"]]
    print("payments", db.payments.delete_many({"client_id": st["client"]}).deleted_count)
    print("invoices", db.invoices.delete_many({"_id": {"$in": [ObjectId(i) for i in st["invoices"]]}}).deleted_count)
    print("moves", db.cash_movements.delete_many({"_id": {"$in": new_moves}}).deleted_count)
    db.clients.delete_one({"_id": ObjectId(st["client"])})
    db.audit_logs.delete_many({"entity_id": {"$in": [st["client"], *pay_ids, *st["invoices"], *[str(m) for m in new_moves]]}})
    for k, v in st["counters"].items():
        key = f"{st['tid']}:{st['bid']}:{k}"
        db.counters.delete_one({"_id": key}) if v is None else db.counters.update_one({"_id": key}, {"$set": {"seq": v}})
    print("done")
