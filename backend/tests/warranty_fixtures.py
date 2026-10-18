# TEST data builder/cleaner for warranty certificates + claims. CLI: python warranty_fixtures.py setup|teardown (state in /tmp/warranty_state.json)
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
STATE = "/tmp/warranty_state.json"
COUNTERS = ("invoice", "nir", "work_order", "proforma", "warranty_certificate", "warranty_claim")


def creds(key="andrei.melek"):
    txt = open("/app/memory/test_credentials.md").read()
    line = [ln for ln in txt.splitlines() if key in ln][0]
    parts = [x.strip() for x in line.lstrip("- ").split("—")[0].split("/")]
    if len(parts) >= 2 and parts[1]:
        return parts[0], parts[1]
    import re
    demo = re.search(r"password for all:\s*([^)\s]+)\)", txt).group(1)
    return parts[0], demo


def mdb():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def session(key="andrei.melek"):
    s = requests.Session()
    em, pw = creds(key)
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
    sup = s.post(f"{BASE}/suppliers", json={"name": f"TEST_FurnizorG {tag}"}).json()
    p1 = s.post(f"{BASE}/products", json={"code": f"TEST_G1_{tag}", "name": f"TEST Plăcuțe frână {tag}", "sale_price": 200, "vat_rate": 21,
                                          "warranty_months": 12}).json()
    p2 = s.post(f"{BASE}/products", json={"code": f"TEST_G2_{tag}", "name": f"TEST Disc {tag}", "sale_price": 300, "vat_rate": 21}).json()
    n1 = s.post(f"{BASE}/nirs", json={"supplier_id": sup["id"], "invoice_no": f"TEST-G-{tag}", "date": "2026-01-01T08:00:00+00:00",
                                      "lines": [{"product_id": p1["id"], "qty": 10, "unit_cost": 80}, {"product_id": p2["id"], "qty": 10, "unit_cost": 120}]}).json()
    cid = db.clients.insert_one({"name": f"TEST_Client Garanție {tag}", "type": "pf", "phone": "0700000000", "created_at": iso()}).inserted_id
    vid = db.vehicles.insert_one({"client_id": str(cid), "vin": f"TESTGAR{tag}0000"[:17].ljust(17, "0"), "plate": f"TSG{tag}", "make": "Test",
                                  "model": "Car", "mileage": 5000, "created_at": iso()}).inserted_id
    lines = [
        {"id": "g_p1", "type": "part", "description": "TEST Plăcuțe frână față", "qty": 2, "unit_price": 200, "discount": 0, "vat_rate": 21,
         "product_id": p1["id"], "code": p1["code"], "unit": "buc"},
        {"id": "g_p2", "type": "part", "description": "TEST Disc frână", "qty": 1, "unit_price": 300, "discount": 0, "vat_rate": 21,
         "product_id": p2["id"], "code": p2["code"], "unit": "buc"},
        {"id": "g_lab", "type": "labor", "description": "TEST Manoperă înlocuire frâne", "qty": 1.5, "unit_price": 150, "discount": 0, "vat_rate": 21,
         "product_id": "", "code": "", "unit": "ore"},
    ]
    wid = db.work_orders.insert_one({"number": f"TEST-WOG-{tag}", "client_id": str(cid), "vehicle_id": str(vid), "status": "finalizata",
                                     "mileage_in": 5000, "lines": lines, "quotes": [],
                                     "qc": {"passed": True, "at": iso(), "inspector_name": "TEST Inspector"},
                                     "status_history": [], "created_at": iso(), "reception": {}, "mechanic_ids": []}).inserted_id
    prof = s.post(f"{BASE}/invoices/from-work-order/{wid}", json={"type": "proforma"}).json()
    inv = s.post(f"{BASE}/invoices/from-work-order/{wid}", json={"type": "fiscal"}).json()
    st.update(supplier=sup["id"], p1=p1["id"], p2=p2["id"], nir=n1["id"], client=str(cid), vehicle=str(vid), wo=str(wid),
              proforma=prof["id"], invoice=inv["id"], invoice_ref=f"{inv['series']}{inv['number']}", issue_date=inv["issue_date"])
    return st


def teardown(st):
    db = mdb()
    pids = [x for x in (st.get("p1"), st.get("p2")) if x]
    claim_wos = [c["work_order_id"] for c in db.warranty_claims.find({"client_name": {"$regex": st["tag"]}}, {"work_order_id": 1})]
    wo_ids = [w for w in [st.get("wo")] + claim_wos if w]
    inv_ids = [str(i["_id"]) for i in db.invoices.find({"$or": [{"work_order_id": {"$in": wo_ids}}, {"original_invoice_id": st.get("invoice")}]}, {"_id": 1})]
    res = {
        "warranty_claims": db.warranty_claims.delete_many({"$or": [{"invoice_id": {"$in": inv_ids}}, {"client_name": {"$regex": st["tag"]}}]}).deleted_count,
        "warranty_certificates": db.warranty_certificates.delete_many({"$or": [{"invoice_id": {"$in": inv_ids}}, {"client_name": {"$regex": st["tag"]}}]}).deleted_count,
        "invoices": db.invoices.delete_many({"_id": {"$in": [ObjectId(i) for i in inv_ids]}}).deleted_count,
        "payments": db.payments.delete_many({"invoice_id": {"$in": inv_ids}}).deleted_count,
        "efactura_logs": db.efactura_logs.delete_many({"invoice_id": {"$in": inv_ids}}).deleted_count,
        "stock_moves": db.stock_moves.delete_many({"product_id": {"$in": pids}}).deleted_count,
        "stock_lots": db.stock_lots.delete_many({"product_id": {"$in": pids}}).deleted_count,
        "nirs": db.nirs.delete_many({"supplier_id": st.get("supplier")}).deleted_count,
        "products": db.products.delete_many({"_id": {"$in": [ObjectId(p) for p in pids]}}).deleted_count,
        "suppliers": db.suppliers.delete_many({"_id": ObjectId(st["supplier"])}).deleted_count if st.get("supplier") else 0,
        "rar_outbox": db.rar_autopass_outbox.delete_many({"work_order_id": {"$in": wo_ids}}).deleted_count,
        "time_entries": db.time_entries.delete_many({"work_order_id": {"$in": wo_ids}}).deleted_count,
        "work_orders": db.work_orders.delete_many({"$or": [{"_id": {"$in": [ObjectId(w) for w in wo_ids]}}, {"vehicle_id": st.get("vehicle")}]}).deleted_count,
        "vehicles": db.vehicles.delete_many({"_id": ObjectId(st["vehicle"])}).deleted_count if st.get("vehicle") else 0,
        "clients": db.clients.delete_many({"_id": ObjectId(st["client"])}).deleted_count if st.get("client") else 0,
    }
    ent = inv_ids + pids + wo_ids + [st.get("supplier"), st.get("nir")]
    res["audit_logs"] = db.audit_logs.delete_many({"$or": [{"entity_id": {"$in": [e for e in ent if e]}}, {"details": {"$regex": st["tag"]}}]}).deleted_count

    def max_used(c):
        if c == "invoice":
            nums = [int(i["number"]) for i in db.invoices.find({"type": "fiscal"}, {"number": 1}) if str(i.get("number", "")).isdigit()]
        elif c == "proforma":
            nums = [int(i["number"]) for i in db.invoices.find({"type": "proforma"}, {"number": 1}) if str(i.get("number", "")).isdigit()]
        elif c == "nir":
            nums = [int(n["number"].split("-")[-1]) for n in db.nirs.find({}, {"number": 1})]
        elif c == "work_order":
            nums = [int(n["number"].split("-")[-1]) for n in db.work_orders.find({"number": {"$regex": "^(CL|GAR)-"}}, {"number": 1})]
        elif c == "warranty_certificate":
            nums = [int(n["number"].split("-")[-1]) for n in db.warranty_certificates.find({}, {"number": 1})]
        else:
            nums = [int(n["number"].split("-")[-1]) for n in db.warranty_claims.find({}, {"number": 1})]
        return max(nums or [0])
    restored = {}
    for c, v in st["counters"].items():
        if v is not None and max_used(c) <= v:
            db.counters.update_one({"_id": c}, {"$set": {"seq": v}})
            restored[c] = v
    res["counters_restored"] = restored
    db.efactura_config.update_one({"_id": "main"}, {"$set": {"auto_send": st.get("auto_send", False)}})
    return res


def residue(tag):
    db = mdb()
    rx = {"$regex": tag}
    return {"products": db.products.count_documents({"code": rx}), "suppliers": db.suppliers.count_documents({"name": rx}),
            "clients": db.clients.count_documents({"name": rx}), "work_orders": db.work_orders.count_documents({"number": rx}),
            "invoices": db.invoices.count_documents({"buyer.name": rx}), "certs": db.warranty_certificates.count_documents({"client_name": rx}),
            "claims": db.warranty_claims.count_documents({"client_name": rx}), "vehicles": db.vehicles.count_documents({"plate": rx})}


if __name__ == "__main__":
    if sys.argv[1] == "setup":
        st = setup(session())
        json.dump(st, open(STATE, "w"))
        print(json.dumps(st, indent=1))
    else:
        st = json.load(open(STATE))
        print(teardown(st), residue(st["tag"]))
