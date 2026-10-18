# Iteration 10 extras: warranty lock, receptionist paper approval, field-scope, decision persistence, re-decision guard.
import secrets
from datetime import datetime, timezone

import pytest
import requests
from bson import ObjectId

from warranty_fixtures import BASE, mdb, session

TAG = "X10" + secrets.token_hex(3).upper()
REAL = ("CL-2026-00086", "CL-2026-00083")
REAL_ID = "6ad30affff3439dd9e54f0c1"


def iso():
    return datetime.now(timezone.utc).isoformat()


def base_lines(price=100):
    return [
        {"id": "x_part", "type": "part", "description": "TEST piesa", "qty": 1, "unit_price": price, "discount": 0, "vat_rate": 21,
         "product_id": "", "code": "P-X", "unit": "buc", "source_warehouse": "Depozit Central"},
        {"id": "x_lab", "type": "labor", "description": "TEST man", "qty": 1, "unit_price": price, "discount": 0, "vat_rate": 21,
         "product_id": "", "code": "", "unit": "ore", "labor_category": "mecanic_senior", "mechanic_id": ""},
    ]


@pytest.fixture(scope="module")
def ctx():
    db = mdb()
    real = {n: db.work_orders.find_one({"number": n}) for n in REAL}
    real_doc = db.work_orders.find_one({"_id": ObjectId(REAL_ID)})
    cid = db.clients.insert_one({"name": f"TEST_Client {TAG}", "type": "pf", "phone": "0700000000", "email": "t@example.com",
                                 "created_at": iso()}).inserted_id
    vid = db.vehicles.insert_one({"client_id": str(cid), "vin": f"TEST{TAG}".ljust(17, "0")[:17], "plate": f"TS{TAG}",
                                  "make": "Test", "model": "Car", "mileage": 1000, "created_at": iso()}).inserted_id
    made = []

    def mk(suffix, status="diagnosticare", **extra):
        doc = {"number": f"TEST-{TAG}-{suffix}", "client_id": str(cid), "vehicle_id": str(vid), "status": status, "mileage_in": 1000,
               "complaint": "TEST", "lines": base_lines(extra.pop("price", 100)), "quotes": [], "qc": {}, "status_history": [],
               "created_at": iso(), "reception": {}, "mechanic_ids": []} | extra
        wid = str(db.work_orders.insert_one(doc).inserted_id)
        made.append(wid)
        return wid

    yield {"admin": session(), "rec": session("sef.service"), "db": db, "mk": mk}
    db.notifications.delete_many({"work_order_id": {"$in": made}})
    db.time_entries.delete_many({"work_order_id": {"$in": made}})
    db.audit_logs.delete_many({"entity_id": {"$in": made}})
    db.work_orders.delete_many({"vehicle_id": str(vid)})
    db.vehicles.delete_one({"_id": vid})
    db.clients.delete_one({"_id": cid})
    for n, doc in real.items():
        assert db.work_orders.find_one({"number": n}) == doc
    assert db.work_orders.find_one({"_id": ObjectId(REAL_ID)}) == real_doc


# --- Warranty WOs: lines immutable and zero-cost
def test_warranty_lines_blocked(ctx):
    wid = ctx["mk"]("WAR", status="in_lucru", is_warranty=True, price=0)
    s = ctx["admin"]
    assert s.put(f"{BASE}/work-orders/{wid}/lines/x_part", json={"unit_price": 50}).status_code == 400
    assert s.post(f"{BASE}/work-orders/{wid}/lines", json={"type": "labor", "description": "TEST", "qty": 1}).status_code == 400
    assert s.delete(f"{BASE}/work-orders/{wid}/lines/x_part").status_code == 400
    w = s.get(f"{BASE}/work-orders/{wid}").json()
    assert w["totals"]["gross"] == 0 and len(w["lines"]) == 2


# --- Receptionist role can paper-approve; decision persisted
def test_receptionist_paper_approval(ctx):
    wid = ctx["mk"]("REC", status="asteapta_oferta")
    rec = ctx["rec"]
    q = rec.post(f"{BASE}/work-orders/{wid}/quotes", json={"valid_days": 7})
    assert q.status_code == 200, q.text
    assert rec.post(f"{BASE}/work-orders/{wid}/quotes/1/decision", json={"approved": True, "paper_approved": False}).status_code == 400
    r = rec.post(f"{BASE}/work-orders/{wid}/quotes/1/decision", json={"approved": True, "paper_approved": True, "name": "TEST client"})
    assert r.status_code == 200, r.text
    q1 = r.json()[0]
    assert q1["status"] == "approved" and q1["decision"]["paper_approved"] is True and q1["decision"]["name"] == "TEST client"
    w = ctx["db"].work_orders.find_one({"_id": ObjectId(wid)})
    assert w["status"] == "aprobata" and w["approved_quote"] == 1
    # re-decision on approved quote rejected
    assert rec.post(f"{BASE}/work-orders/{wid}/quotes/1/decision", json={"approved": False}).status_code == 400


# --- Signed approval: signature stored, paper false
def test_signature_approval_persisted(ctx):
    wid = ctx["mk"]("SIG", status="diagnosticare")
    s = ctx["admin"]
    s.post(f"{BASE}/work-orders/{wid}/quotes", json={"valid_days": 7})
    r = s.post(f"{BASE}/work-orders/{wid}/quotes/1/decision", json={"approved": True, "signature": "data:image/png;base64,TEST"})
    assert r.status_code == 200
    d = r.json()[0]["decision"]
    assert d["signature"].startswith("data:image") and d["paper_approved"] is False


# --- Public token: paper flag rejected even with approved False
def test_public_paper_on_reject(ctx):
    wid = ctx["mk"]("PUBR", status="diagnosticare")
    s = ctx["admin"]
    token = s.post(f"{BASE}/work-orders/{wid}/quotes", json={"valid_days": 7}).json()[0]["token"]
    r = requests.post(f"{BASE}/public/quotes/{token}/decision", json={"approved": False, "paper_approved": True})
    assert r.status_code == 403
    assert ctx["db"].work_orders.find_one({"_id": ObjectId(wid)})["quotes"][0]["status"] == "draft"


# --- Status gate with rejected quote only -> 400
@pytest.mark.parametrize("target", ["aprobata", "finalizata"])
def test_gate_rejected_quote(ctx, target):
    wid = ctx["mk"](f"REJ{target}", status="in_lucru", quotes=[{"version": 1, "status": "rejected", "token": secrets.token_hex(4)}])
    assert ctx["admin"].post(f"{BASE}/work-orders/{wid}/status", json={"status": target}).status_code == 400


# --- Totals precision with discount on both line types
def test_combined_totals(ctx):
    wid = ctx["mk"]("TOT", status="aprobata")
    s = ctx["admin"]
    s.put(f"{BASE}/work-orders/{wid}/lines/x_part", json={"qty": 1.5, "unit_price": 33.33, "discount": 12.5})
    r = s.put(f"{BASE}/work-orders/{wid}/lines/x_lab", json={"qty": 0.7, "unit_price": 180, "discount": 7})
    t = r.json()["totals"]
    exp_net = round(1.5 * 33.33 * 0.875 + 0.7 * 180 * 0.93, 2)
    assert abs(t["net"] - exp_net) < 0.02, t
    assert abs(t["gross"] - round(t["net"] * 1.21, 2)) < 0.02, t


# --- Out-of-scope keys ignored (type / vat / product_id / source not editable)
def test_extra_fields_ignored(ctx):
    wid = ctx["mk"]("EXT", status="aprobata")
    r = ctx["admin"].put(f"{BASE}/work-orders/{wid}/lines/x_part", json={"type": "labor", "vat_rate": 0, "source_warehouse": "X", "qty": 2})
    assert r.status_code == 200
    ln = next(x for x in r.json()["lines"] if x["id"] == "x_part")
    assert ln["type"] == "part" and ln["vat_rate"] == 21 and ln["source_warehouse"] == "Depozit Central" and ln["qty"] == 2


# --- PUT /work-orders on locked order (diagnosis/allocation) - informational
def test_wo_header_update_on_locked(ctx):
    wid = ctx["mk"]("HDR", status="inchisa")
    r = ctx["admin"].put(f"{BASE}/work-orders/{wid}", json={"diagnosis": "TEST changed"})
    print("PUT /work-orders on inchisa ->", r.status_code)
