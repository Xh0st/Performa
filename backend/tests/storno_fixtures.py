# Shared TEST data builder/cleaner for storno (CreditNote) + supplier return tests.
# CLI: python storno_fixtures.py setup|teardown  (state saved in /tmp/storno_state.json) - used for UI tests.
import os
import sys
import json
import secrets
import requests
from datetime import datetime, timezone
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
STATE = "/tmp/storno_state.json"
COUNTERS = ("invoice", "nir", "supplier_return", "work_order")


def creds():
    txt = open("/app/memory/test_credentials.md").read()
    line = [ln for ln in txt.splitlines() if "andrei.melek" in ln][0]
    em, pw = [x.strip() for x in line.lstrip("- ").split("/")[:2]]
    return em, pw


def mdb():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def session():
    s = requests.Session()
    em, pw = creds()
    r = s.post(f"{BASE}/auth/login", json={"email": em, "password": pw})
    r.raise_for_status()
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


def iso():
    return datetime.now(timezone.utc).isoformat()


def setup(s, tag=None):
    db = mdb()
    tag = tag or secrets.token_hex(3).upper()
    st = {"tag": tag, "counters": {c: (db.counters.find_one({"_id": c}) or {}).get("seq") for c in COUNTERS}}
    cfg = db.efactura_config.find_one({"_id": "main"}) or {}
    st["auto_send"] = cfg.get("auto_send", False)
    db.efactura_config.update_one({"_id": "main"}, {"$set": {"auto_send": False}})
    sup = s.post(f"{BASE}/suppliers", json={"name": f"TEST_Furnizor {tag}", "cui": "RO99999999"}).json()
    other = s.post(f"{BASE}/suppliers", json={"name": f"TEST_Furnizor2 {tag}"}).json()
    p1 = s.post(f"{BASE}/products", json={"code": f"TEST_P1_{tag}", "name": f"TEST Filtru {tag}", "sale_price": 100, "vat_rate": 21}).json()
    p2 = s.post(f"{BASE}/products", json={"code": f"TEST_P2_{tag}", "name": f"TEST Carte {tag}", "sale_price": 40, "vat_rate": 11}).json()
    n1 = s.post(f"{BASE}/nirs", json={"supplier_id": sup["id"], "invoice_no": f"TEST-F1-{tag}", "date": "2026-01-01T08:00:00+00:00",
                                      "lines": [{"product_id": p1["id"], "qty": 10, "unit_cost": 50}, {"product_id": p2["id"], "qty": 5, "unit_cost": 20}]}).json()
    n2 = s.post(f"{BASE}/nirs", json={"supplier_id": sup["id"], "invoice_no": f"TEST-F2-{tag}", "date": "2026-01-02T08:00:00+00:00",
                                      "lines": [{"product_id": p1["id"], "qty": 4, "unit_cost": 60}]}).json()
    cid = db.clients.insert_one({"name": f"TEST_Client {tag}", "type": "pf", "phone": "0700000000", "created_at": iso()}).inserted_id
    vid = db.vehicles.insert_one({"client_id": str(cid), "vin": f"TESTVIN{tag}0000"[:17].ljust(17, "0"), "plate": f"TST{tag}", "make": "Test", "model": "Car",
                                  "mileage": 1000, "created_at": iso()}).inserted_id
    lines = [
        {"id": "l_p1", "type": "part", "description": "TEST Filtru", "qty": 3, "unit_price": 100, "discount": 0, "vat_rate": 21,
         "product_id": p1["id"], "code": p1["code"], "unit": "buc"},
        {"id": "l_p2", "type": "part", "description": "TEST Carte", "qty": 2, "unit_price": 40, "discount": 0, "vat_rate": 11,
         "product_id": p2["id"], "code": p2["code"], "unit": "buc"},
        {"id": "l_lab", "type": "labor", "description": "TEST Manopera", "qty": 1.5, "unit_price": 150, "discount": 0, "vat_rate": 21,
         "product_id": "", "code": "", "unit": "ore"},
    ]
    wid = db.work_orders.insert_one({"number": f"TEST-WO-{tag}", "client_id": str(cid), "vehicle_id": str(vid), "status": "finalizata",
                                         "mileage_in": 1000, "lines": lines, "quotes": [],
                                         "qc": {"passed": True, "at": iso(), "inspector_name": "TEST Inspector"},
                                         "status_history": [], "created_at": iso(),
                                     "reception": {}, "mechanic_ids": []}).inserted_id
    inv = s.post(f"{BASE}/invoices/from-work-order/{wid}", json={"type": "fiscal"}).json()
    st.update(supplier=sup["id"], supplier2=other["id"], p1=p1["id"], p2=p2["id"], p1_code=p1["code"], p2_code=p2["code"], nir1=n1["id"],
              nir1_number=n1["number"], nir2=n2["id"], nir2_number=n2["number"], client=str(cid), vehicle=str(vid), wo=str(wid), invoice=inv["id"],
              invoice_ref=f"{inv['series']}{inv['number']}")
    return st


def teardown(st):
    db = mdb()
    pids = [x for x in (st.get("p1"), st.get("p2")) if x]
    sups = [x for x in (st.get("supplier"), st.get("supplier2")) if x]
    inv_ids = [str(i["_id"]) for i in db.invoices.find({"$or": [{"work_order_id": st.get("wo")}, {"original_invoice_id": st.get("invoice")}]}, {"_id": 1})]
    ret_ids = [str(r["_id"]) for r in db.supplier_returns.find({"supplier_id": {"$in": sups}}, {"_id": 1})]
    res = {
        "invoices": db.invoices.delete_many({"_id": {"$in": [ObjectId(i) for i in inv_ids]}}).deleted_count,
        "payments": db.payments.delete_many({"invoice_id": {"$in": inv_ids}}).deleted_count,
        "efactura_logs": db.efactura_logs.delete_many({"invoice_id": {"$in": inv_ids}}).deleted_count,
        "stock_moves": db.stock_moves.delete_many({"product_id": {"$in": pids}}).deleted_count,
        "stock_lots": db.stock_lots.delete_many({"product_id": {"$in": pids}}).deleted_count,
        "supplier_returns": db.supplier_returns.delete_many({"supplier_id": {"$in": sups}}).deleted_count,
        "nirs": db.nirs.delete_many({"supplier_id": {"$in": sups}}).deleted_count,
        "products": db.products.delete_many({"_id": {"$in": [ObjectId(p) for p in pids]}}).deleted_count,
        "suppliers": db.suppliers.delete_many({"_id": {"$in": [ObjectId(p) for p in sups]}}).deleted_count,
        "rar_outbox": db.rar_autopass_outbox.delete_many({"work_order_id": st.get("wo")}).deleted_count if st.get("wo") else 0,
        "work_orders": db.work_orders.delete_many({"_id": ObjectId(st["wo"])}).deleted_count if st.get("wo") else 0,
        "vehicles": db.vehicles.delete_many({"_id": ObjectId(st["vehicle"])}).deleted_count if st.get("vehicle") else 0,
        "clients": db.clients.delete_many({"_id": ObjectId(st["client"])}).deleted_count if st.get("client") else 0,
    }
    ent = inv_ids + pids + sups + ret_ids + [st.get("nir1"), st.get("nir2"), st.get("wo")]
    res["audit_logs"] = db.audit_logs.delete_many({"$or": [{"entity_id": {"$in": [e for e in ent if e]}},
                                                          {"details": {"$regex": st["tag"]}}]}).deleted_count
    # restore sequence counters (only if nobody else consumed numbers meanwhile)
    def max_used(c):
        if c == "invoice":
            nums = [int(i["number"]) for i in db.invoices.find({"type": "fiscal"}, {"number": 1}) if str(i.get("number", "")).isdigit()]
        elif c == "nir":
            nums = [int(n["number"].split("-")[-1]) for n in db.nirs.find({}, {"number": 1})]
        elif c == "supplier_return":
            nums = [int(n["number"].split("-")[-1]) for n in db.supplier_returns.find({}, {"number": 1})]
        else:
            nums = [int(n["number"].split("-")[-1]) for n in db.work_orders.find({"number": {"$regex": "^CL-"}}, {"number": 1})]
        return max(nums or [0])
    st["counters_restored"] = {}
    for c, v in st["counters"].items():
        if v is not None and max_used(c) <= v:
            db.counters.update_one({"_id": c}, {"$set": {"seq": v}})
            st["counters_restored"][c] = v
    res["counters_restored"] = st["counters_restored"]
    db.efactura_config.update_one({"_id": "main"}, {"$set": {"auto_send": st.get("auto_send", False)}})
    return res


def residue(tag):
    db = mdb()
    rx = {"$regex": tag}
    return {"products": db.products.count_documents({"code": rx}), "suppliers": db.suppliers.count_documents({"name": rx}),
            "nirs": db.nirs.count_documents({"invoice_no": rx}), "clients": db.clients.count_documents({"name": rx}),
            "work_orders": db.work_orders.count_documents({"number": rx}), "invoices": db.invoices.count_documents({"buyer.name": rx}),
            "returns": db.supplier_returns.count_documents({"supplier_name": rx})}


if __name__ == "__main__":
    if sys.argv[1] == "setup":
        st = setup(session())
        json.dump(st, open(STATE, "w"))
        print(json.dumps(st, indent=1))
    else:
        st = json.load(open(STATE))
        print(teardown(st), residue(st["tag"]))
