# Iter32 UI fixture: PF client + 150 RON invoice + 150 RON cash chitanta. CLI: setup|teardown (state /tmp/iter32_ui.json)
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
STATE = "/tmp/iter32_ui.json"
COUNTERS = ["pay_chitanta", "pay_bon_fiscal", "cash_deposit", "cash_expense_settlement", "cash_payment_order", "cash_receipt_reversal"]
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def setup():
    line = [ln for ln in open("/app/memory/test_credentials.md").read().splitlines() if "andrei.melek" in ln][0]
    em, pw = [x.strip() for x in line.lstrip("- ").split("/")[:2]]
    s = requests.Session()
    user = s.post(f"{BASE}/auth/login", json={"email": em, "password": pw.split()[0]}).json()["user"]
    tid, bid = user["tenant_id"], user["active_branch_id"]
    st = {"tid": tid, "bid": bid, "counters": {c: (db.counters.find_one({"_id": f"{tid}:{bid}:{c}"}) or {}).get("seq") for c in COUNTERS},
          "moves_before": [str(d["_id"]) for d in db.cash_movements.find({}, {"_id": 1})]}
    pf = s.post(f"{BASE}/clients", json={"type": "pf", "name": "TEST_UI32 PF"}).json()
    doc = {"type": "fiscal", "series": "TSTU32", "number": "1", "issue_date": "2026-01-01", "due_date": "2026-01-05", "client_id": pf["id"],
           "buyer": {"name": "TEST"}, "lines": [], "totals": {"net": 123.97, "vat": 26.03, "gross": 150.0},
           "paid_amount": 0.0, "status": "unpaid", "efactura": {"status": "not_sent", "history": []},
           "created_at": datetime.now(timezone.utc).isoformat(), "tenant_id": tid, "branch_id": bid}
    inv = str(db.invoices.insert_one(doc).inserted_id)
    pay = s.post(f"{BASE}/payments", json={"client_id": pf["id"], "invoice_id": inv, "amount": 150, "method": "numerar",
                                           "cash_document": "receipt", "reference": "TEST_UI32"}).json()
    st.update({"client": pf["id"], "invoice": inv, "payment": pay["id"], "payment_doc": pay["doc_number"]})
    json.dump(st, open(STATE, "w"))
    print(json.dumps({k: v for k, v in st.items() if k not in ("counters", "moves_before")}))


def teardown():
    st = json.load(open(STATE))
    pays = [str(p["_id"]) for p in db.payments.find({"client_id": st["client"]}, {"_id": 1})]
    new = [d["_id"] for d in db.cash_movements.find({}, {"_id": 1}) if str(d["_id"]) not in st["moves_before"]]
    print("payments", db.payments.delete_many({"client_id": st["client"]}).deleted_count)
    print("invoices", db.invoices.delete_one({"_id": ObjectId(st["invoice"])}).deleted_count)
    print("moves", db.cash_movements.delete_many({"_id": {"$in": new}}).deleted_count)
    print("clients", db.clients.delete_one({"_id": ObjectId(st["client"])}).deleted_count)
    db.audit_logs.delete_many({"entity_id": {"$in": [st["client"], st["invoice"]] + pays + [str(d) for d in new]}})
    for c, v in st["counters"].items():
        key = f"{st['tid']}:{st['bid']}:{c}"
        if v is None:
            db.counters.delete_one({"_id": key})
        else:
            db.counters.update_one({"_id": key}, {"$set": {"seq": v}})


if __name__ == "__main__":
    setup() if sys.argv[1] == "setup" else teardown()
