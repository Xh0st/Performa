# Fiscal invoice gate: requires finalizata + QC passed + an approved quote (iteration 7). Labor-only TEST lines (no stock).
import secrets
from datetime import datetime, timezone

import pytest
from bson import ObjectId

from warranty_fixtures import BASE, mdb, session, COUNTERS

TAG = "FQG" + secrets.token_hex(3).upper()
REAL = ("CL-2026-00086", "CL-2026-00083")
QC_OK = {"passed": True, "at": "2026-01-01T00:00:00+00:00", "inspector_name": "TEST"}
LINE = [{"id": "fq_lab", "type": "labor", "description": "TEST manopera", "qty": 1, "unit_price": 100, "discount": 0, "vat_rate": 21,
         "product_id": "", "code": "", "unit": "ore"}]


def iso():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture(scope="module")
def ctx():
    db, s = mdb(), session()
    real = {n: db.work_orders.find_one({"number": n}) for n in REAL}
    counters = {c: (db.counters.find_one({"_id": c}) or {}).get("seq") for c in COUNTERS}
    cfg = db.efactura_config.find_one({"_id": "main"}) or {}
    db.efactura_config.update_one({"_id": "main"}, {"$set": {"auto_send": False}})
    cid = db.clients.insert_one({"name": f"TEST_Client {TAG}", "type": "pf", "phone": "0700000000", "created_at": iso()}).inserted_id
    vid = db.vehicles.insert_one({"client_id": str(cid), "vin": f"TEST{TAG}".ljust(17, "0")[:17], "plate": f"TS{TAG}",
                                  "make": "Test", "model": "Car", "mileage": 1000, "created_at": iso()}).inserted_id
    made = []

    def mk(suffix, status="finalizata", quotes=None, qc=None, lines=None):
        doc = {"number": f"TEST-{TAG}-{suffix}", "client_id": str(cid), "vehicle_id": str(vid), "status": status, "mileage_in": 1000,
               "complaint": "TEST", "lines": lines if lines is not None else [dict(x) for x in LINE], "quotes": quotes or [],
               "qc": qc if qc is not None else dict(QC_OK), "status_history": [], "created_at": iso(), "reception": {}, "mechanic_ids": []}
        wid = str(db.work_orders.insert_one(doc).inserted_id)
        made.append(wid)
        return wid

    yield {"s": s, "db": db, "mk": mk}
    inv_ids = [str(i["_id"]) for i in db.invoices.find({"work_order_id": {"$in": made}}, {"_id": 1})]
    db.warranty_certificates.delete_many({"invoice_id": {"$in": inv_ids}})
    db.efactura_logs.delete_many({"invoice_id": {"$in": inv_ids}})
    db.invoices.delete_many({"_id": {"$in": [ObjectId(i) for i in inv_ids]}})
    db.rar_autopass_outbox.delete_many({"work_order_id": {"$in": made}})
    db.rar_autopass_logs.delete_many({"work_order_id": {"$in": made}})
    db.notifications.delete_many({"work_order_id": {"$in": made}})
    db.audit_logs.delete_many({"entity_id": {"$in": made + inv_ids}})
    db.work_orders.delete_many({"$or": [{"_id": {"$in": [ObjectId(w) for w in made]}}, {"vehicle_id": str(vid)}]})
    db.vehicles.delete_one({"_id": vid})
    db.clients.delete_one({"_id": cid})
    for c in ("invoice", "warranty_certificate"):
        if counters.get(c) is not None:
            db.counters.update_one({"_id": c}, {"$set": {"seq": counters[c]}})
    db.efactura_config.update_one({"_id": "main"}, {"$set": {"auto_send": cfg.get("auto_send", False)}})
    for n, doc in real.items():
        assert db.work_orders.find_one({"number": n}) == doc, f"Real {n} was modified!"
    assert db.work_orders.count_documents({"number": {"$regex": TAG}}) == 0


def _post(ctx, wid):
    return ctx["s"].post(f"{BASE}/invoices/from-work-order/{wid}", json={"type": "fiscal"})


@pytest.mark.parametrize("label,quotes", [("NOQ", []), ("REJ", [{"version": 1, "status": "rejected"}]),
                                          ("DRAFT", [{"version": 1, "status": "draft"}]), ("SENT", [{"version": 1, "status": "sent"}]),
                                          ("SUPER", [{"version": 1, "status": "superseded"}])])
def test_fiscal_rejected_without_approved_quote(ctx, label, quotes):
    wid = ctx["mk"](label, quotes=quotes)
    r = _post(ctx, wid)
    assert r.status_code == 400, r.text
    assert "deviz" in r.json()["detail"].lower()
    w = ctx["db"].work_orders.find_one({"_id": ObjectId(wid)})
    assert w["status"] == "finalizata" and not w.get("invoice_id")
    assert ctx["db"].invoices.count_documents({"work_order_id": wid}) == 0


def test_fiscal_rejected_without_qc(ctx):
    wid = ctx["mk"]("NOQC", quotes=[{"version": 1, "status": "approved"}], qc={"passed": False})
    r = _post(ctx, wid)
    assert r.status_code == 400 and "calit" in r.json()["detail"].lower()


def test_fiscal_rejected_not_finalised(ctx):
    wid = ctx["mk"]("INL", status="in_lucru", quotes=[{"version": 1, "status": "approved"}])
    assert _post(ctx, wid).status_code == 400


def test_fiscal_accepts_generated_approved_quote(ctx):
    s, db = ctx["s"], ctx["db"]
    wid = ctx["mk"]("OK", status="diagnosticare", qc={})
    assert s.post(f"{BASE}/work-orders/{wid}/quotes", json={"valid_days": 7}).status_code == 200
    r = s.post(f"{BASE}/work-orders/{wid}/quotes/1/decision", json={"approved": True, "signature": "data:image/png;base64,TEST", "name": "TEST"})
    assert r.status_code == 200 and r.json()[0]["status"] == "approved"
    db.work_orders.update_one({"_id": ObjectId(wid)}, {"$set": {"qc": dict(QC_OK)}})
    r = s.post(f"{BASE}/work-orders/{wid}/status", json={"status": "finalizata"})
    assert r.status_code == 200, r.text
    r = _post(ctx, wid)
    assert r.status_code == 200, r.text
    inv = r.json()
    assert inv["type"] == "fiscal" and inv["work_order_id"] == wid and inv["totals"]["gross"] == 121
    w = s.get(f"{BASE}/work-orders/{wid}").json()
    assert w["status"] == "facturata" and w["invoice_id"] == inv["id"]
    # invoiced: cannot close, reopen, review, or re-invoice
    assert s.post(f"{BASE}/work-orders/{wid}/status", json={"status": "inchisa"}).status_code == 400
    assert s.post(f"{BASE}/work-orders/{wid}/reopen", json={}).status_code == 400
    assert s.post(f"{BASE}/work-orders/{wid}/closure-review", json={}).status_code == 400
    assert _post(ctx, wid).status_code == 400
    assert s.get(f"{BASE}/work-orders/{wid}").json()["status"] == "facturata"
    ids = {x["id"] for x in s.get(f"{BASE}/closure-exceptions/work-orders").json()}
    assert wid not in ids


def test_real_cl_00086_readonly(ctx):
    w = ctx["db"].work_orders.find_one({"number": "CL-2026-00086"})
    assert w and str(w["_id"]) == "6ad3d505afe314ce5bd6df92"
    assert w["status"] == "inchisa" and not w.get("invoice_id") and not w.get("closure_review")
    ids = {x["id"] for x in ctx["s"].get(f"{BASE}/closure-exceptions/work-orders").json()}
    assert str(w["_id"]) in ids
