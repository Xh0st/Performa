# Status guard (iteration 9): aprobata/finalizata require an approved quote; finalizata also needs QC; auto-aprobata on signed approval.
import secrets
from datetime import datetime, timezone

import pytest
from bson import ObjectId

from warranty_fixtures import BASE, mdb, session, COUNTERS

QC_KEYS = ["noxe", "frane", "geometrie", "faruri_geamuri_parbrize", "parametri_reglaje", "etanșeitate", "proba_drum"]

TAG = "SQG" + secrets.token_hex(3).upper()
REAL = ("CL-2026-00086", "CL-2026-00083")
LINE = [{"id": "sq_lab", "type": "labor", "description": "TEST manopera", "qty": 1, "unit_price": 100, "discount": 0, "vat_rate": 21,
         "product_id": "", "code": "", "unit": "ore"}]
SIG = "data:image/png;base64,TEST"


def iso():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture(scope="module")
def ctx():
    db, s = mdb(), session()
    real = {n: db.work_orders.find_one({"number": n}) for n in REAL}
    counters = {c: (db.counters.find_one({"_id": c}) or {}).get("seq") for c in COUNTERS}
    cfg = db.efactura_config.find_one({"_id": "main"}) or {}
    db.efactura_config.update_one({"_id": "main"}, {"$set": {"auto_send": False}})
    cid = db.clients.insert_one({"name": f"TEST_Client {TAG}", "type": "pf", "phone": "0700000000", "email": "test@example.com",
                                 "created_at": iso()}).inserted_id
    vid = db.vehicles.insert_one({"client_id": str(cid), "vin": f"TEST{TAG}".ljust(17, "0")[:17], "plate": f"TS{TAG}",
                                  "make": "Test", "model": "Car", "mileage": 1000, "created_at": iso()}).inserted_id
    made = []

    def mk(suffix, status="in_lucru", quotes=None, qc=None):
        doc = {"number": f"TEST-{TAG}-{suffix}", "client_id": str(cid), "vehicle_id": str(vid), "status": status, "mileage_in": 1000,
               "complaint": "TEST", "lines": [dict(x) for x in LINE], "quotes": quotes or [], "qc": qc or {},
               "status_history": [], "created_at": iso(), "reception": {}, "mechanic_ids": []}
        wid = str(db.work_orders.insert_one(doc).inserted_id)
        made.append(wid)
        return wid

    yield {"s": s, "db": db, "mk": mk}
    inv_ids = [str(i["_id"]) for i in db.invoices.find({"work_order_id": {"$in": made}}, {"_id": 1})]
    db.warranty_certificates.delete_many({"invoice_id": {"$in": inv_ids}})
    db.efactura_logs.delete_many({"invoice_id": {"$in": inv_ids}})
    db.invoices.delete_many({"_id": {"$in": [ObjectId(i) for i in inv_ids]}})
    for coll in ("rar_autopass_outbox", "rar_autopass_logs", "notifications", "time_entries"):
        db[coll].delete_many({"work_order_id": {"$in": made}})
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


def _status(ctx, wid, st):
    return ctx["s"].post(f"{BASE}/work-orders/{wid}/status", json={"status": st, "note": "TEST"})


def _qc_pass(ctx, wid):
    r = ctx["s"].put(f"{BASE}/work-orders/{wid}/qc", json={"items": {k: "C" for k in QC_KEYS}, "mechanic_signature": SIG, "chief_signature": SIG})
    assert r.status_code == 200 and r.json()["qc"]["passed"] is True, r.text


QUOTE_VARIANTS = [("NOQ", []), ("DRAFT", [{"version": 1, "status": "draft"}]), ("SENT", [{"version": 1, "status": "sent"}]),
                  ("REJ", [{"version": 1, "status": "rejected"}]), ("SUPER", [{"version": 1, "status": "superseded"}]),
                  ("MIX", [{"version": 1, "status": "superseded"}, {"version": 2, "status": "rejected"}, {"version": 3, "status": "sent"}])]


# 1) Manual aprobata/finalizata blocked without approved quote (also with QC passed)
@pytest.mark.parametrize("target", ["aprobata", "finalizata"])
@pytest.mark.parametrize("label,quotes", QUOTE_VARIANTS)
def test_manual_status_blocked_without_approved_quote(ctx, target, label, quotes):
    wid = ctx["mk"](f"{label}-{target}", quotes=quotes, qc={"passed": True})
    r = _status(ctx, wid, target)
    assert r.status_code == 400, r.text
    assert "deviz" in r.json()["detail"].lower()
    w = ctx["db"].work_orders.find_one({"_id": ObjectId(wid)})
    assert w["status"] == "in_lucru" and not w.get("finished_at") and w["status_history"] == []


# 2) Real signed approval auto-switches to aprobata from noua/diagnosticare/asteapta_oferta
@pytest.mark.parametrize("start", ["noua", "diagnosticare", "asteapta_oferta"])
def test_signed_approval_sets_aprobata(ctx, start):
    s, db = ctx["s"], ctx["db"]
    wid = ctx["mk"](f"AUTO-{start}", status="diagnosticare" if start != "noua" else "noua")
    assert s.post(f"{BASE}/work-orders/{wid}/quotes", json={"valid_days": 7}).status_code == 200
    # create_quote moves noua/diagnosticare -> asteapta_oferta; force the start status to test each branch
    db.work_orders.update_one({"_id": ObjectId(wid)}, {"$set": {"status": start}})
    assert s.post(f"{BASE}/work-orders/{wid}/quotes/1/send", json={"channel": "sms", "link": "TEST"}).status_code == 200
    # no signature -> 400, status unchanged
    r = s.post(f"{BASE}/work-orders/{wid}/quotes/1/decision", json={"approved": True, "signature": ""})
    assert r.status_code == 400
    assert s.get(f"{BASE}/work-orders/{wid}").json()["status"] == start
    r = s.post(f"{BASE}/work-orders/{wid}/quotes/1/decision", json={"approved": True, "signature": SIG, "name": "TEST"})
    assert r.status_code == 200 and r.json()[0]["status"] == "approved"
    w = s.get(f"{BASE}/work-orders/{wid}").json()
    assert w["status"] == "aprobata" and w["approved_quote"] == 1
    assert w["status_history"][-1]["status"] == "aprobata"


def test_public_portal_approval_sets_aprobata(ctx):
    s = ctx["s"]
    wid = ctx["mk"]("PUB", status="diagnosticare")
    q = s.post(f"{BASE}/work-orders/{wid}/quotes", json={"valid_days": 7}).json()[0]
    import requests
    r = requests.post(f"{BASE}/public/quotes/{q['token']}/decision", json={"approved": True, "signature": SIG, "name": "TEST Client"})
    assert r.status_code == 200, r.text
    assert s.get(f"{BASE}/work-orders/{wid}").json()["status"] == "aprobata"


def test_rejection_does_not_set_aprobata(ctx):
    s = ctx["s"]
    wid = ctx["mk"]("REJFLOW", status="diagnosticare")
    s.post(f"{BASE}/work-orders/{wid}/quotes", json={"valid_days": 7})
    r = s.post(f"{BASE}/work-orders/{wid}/quotes/1/decision", json={"approved": False, "reason": "TEST"})
    assert r.status_code == 200 and r.json()[0]["status"] == "rejected"
    assert s.get(f"{BASE}/work-orders/{wid}").json()["status"] == "asteapta_oferta"
    assert _status(ctx, wid, "aprobata").status_code == 400


def test_approval_on_in_lucru_keeps_status(ctx):
    s = ctx["s"]
    wid = ctx["mk"]("INL", status="in_lucru", quotes=[{"version": 1, "status": "sent", "token": f"tok{TAG}"}])
    r = s.post(f"{BASE}/work-orders/{wid}/quotes/1/decision", json={"approved": True, "signature": SIG})
    assert r.status_code == 200
    assert s.get(f"{BASE}/work-orders/{wid}").json()["status"] == "in_lucru"


# 3) Approved quote: finalizata 400 without QC, 200 with QC; aprobata allowed manually; then 4) fiscal invoice
def test_approved_quote_finalize_requires_qc_then_invoice(ctx):
    s, db = ctx["s"], ctx["db"]
    wid = ctx["mk"]("FULL", status="diagnosticare")
    s.post(f"{BASE}/work-orders/{wid}/quotes", json={"valid_days": 7})
    s.post(f"{BASE}/work-orders/{wid}/quotes/1/decision", json={"approved": True, "signature": SIG, "name": "TEST"})
    assert _status(ctx, wid, "in_lucru").status_code == 200
    assert _status(ctx, wid, "aprobata").status_code == 200
    r = _status(ctx, wid, "finalizata")
    assert r.status_code == 400 and "calit" in r.json()["detail"].lower()
    assert s.get(f"{BASE}/work-orders/{wid}").json()["status"] == "aprobata"
    # fiscal invoice not allowed before finalizata
    assert s.post(f"{BASE}/invoices/from-work-order/{wid}", json={"type": "fiscal"}).status_code == 400
    _qc_pass(ctx, wid)
    r = _status(ctx, wid, "finalizata")
    assert r.status_code == 200, r.text
    w = r.json()
    assert w["status"] == "finalizata" and w.get("finished_at")
    r = s.post(f"{BASE}/invoices/from-work-order/{wid}", json={"type": "fiscal"})
    assert r.status_code == 200, r.text
    assert s.get(f"{BASE}/work-orders/{wid}").json()["status"] == "facturata"


# 4) Fiscal: finalizata+QC but quote not approved -> 400 (direct DB state, simulates legacy records)
@pytest.mark.parametrize("label,quotes", QUOTE_VARIANTS)
def test_fiscal_blocked_without_approved_quote(ctx, label, quotes):
    wid = ctx["mk"](f"FIS-{label}", status="finalizata", quotes=quotes, qc={"passed": True})
    r = ctx["s"].post(f"{BASE}/invoices/from-work-order/{wid}", json={"type": "fiscal"})
    assert r.status_code == 400 and "deviz" in r.json()["detail"].lower()
    assert ctx["db"].invoices.count_documents({"work_order_id": wid}) == 0


# 6) Uninvoiced close without quote still works
def test_close_without_quote_allowed(ctx):
    wid = ctx["mk"]("CLOSE", status="noua")
    r = _status(ctx, wid, "inchisa")
    assert r.status_code == 200, r.text
    w = r.json()
    assert w["status"] == "inchisa" and w["closure_quote_rule"]["reason"] == "inchidere_nefacturata"
    assert w["pre_closure_status"] == "noua"
