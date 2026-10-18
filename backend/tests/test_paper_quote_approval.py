# Paper approval of quotes (iteration 9): internal service endpoint accepts paper_approved without signature; public endpoint rejects it.
import secrets
from datetime import datetime, timezone

import pytest
import requests
from bson import ObjectId

from warranty_fixtures import BASE, mdb, session

QC_KEYS = ["noxe", "frane", "geometrie", "faruri_geamuri_parbrize", "parametri_reglaje", "etanșeitate", "proba_drum"]
TAG = "PAP" + secrets.token_hex(3).upper()
REAL = ("CL-2026-00086", "CL-2026-00083")
LINE = [{"id": "pa_lab", "type": "labor", "description": "TEST manopera", "qty": 1, "unit_price": 100, "discount": 0, "vat_rate": 21,
         "product_id": "", "code": "", "unit": "ore"}]
SIG = "data:image/png;base64,TEST"


def iso():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture(scope="module")
def ctx():
    db, s = mdb(), session()
    real = {n: db.work_orders.find_one({"number": n}) for n in REAL}
    cid = db.clients.insert_one({"name": f"TEST_Client {TAG}", "type": "pf", "phone": "0700000000", "email": "test@example.com",
                                 "created_at": iso()}).inserted_id
    vid = db.vehicles.insert_one({"client_id": str(cid), "vin": f"TEST{TAG}".ljust(17, "0")[:17], "plate": f"TS{TAG}",
                                  "make": "Test", "model": "Car", "mileage": 1000, "created_at": iso()}).inserted_id
    made = []

    def mk(suffix, status="diagnosticare"):
        doc = {"number": f"TEST-{TAG}-{suffix}", "client_id": str(cid), "vehicle_id": str(vid), "status": status, "mileage_in": 1000,
               "complaint": "TEST", "lines": [dict(x) for x in LINE], "quotes": [], "qc": {},
               "status_history": [], "created_at": iso(), "reception": {}, "mechanic_ids": []}
        wid = str(db.work_orders.insert_one(doc).inserted_id)
        made.append(wid)
        q = s.post(f"{BASE}/work-orders/{wid}/quotes", json={"valid_days": 7})
        assert q.status_code == 200, q.text
        return wid, q.json()[0]

    yield {"s": s, "db": db, "mk": mk}
    for coll in ("notifications", "time_entries"):
        db[coll].delete_many({"work_order_id": {"$in": made}})
    db.audit_logs.delete_many({"entity_id": {"$in": made}})
    db.work_orders.delete_many({"$or": [{"_id": {"$in": [ObjectId(w) for w in made]}}, {"vehicle_id": str(vid)}]})
    db.vehicles.delete_one({"_id": vid})
    db.clients.delete_one({"_id": cid})
    for n, doc in real.items():
        assert db.work_orders.find_one({"number": n}) == doc, f"Real {n} was modified!"
    assert db.work_orders.count_documents({"number": {"$regex": TAG}}) == 0


def _dec(ctx, wid, body):
    return ctx["s"].post(f"{BASE}/work-orders/{wid}/quotes/1/decision", json=body)


def _wo(ctx, wid):
    return ctx["s"].get(f"{BASE}/work-orders/{wid}").json()


def test_approve_without_signature_or_paper_400(ctx):
    wid, _ = ctx["mk"]("NOSIG")
    for body in ({"approved": True}, {"approved": True, "signature": "", "paper_approved": False}):
        r = _dec(ctx, wid, body)
        assert r.status_code == 400, r.text
        assert "semn" in r.json()["detail"].lower()
    w = _wo(ctx, wid)
    assert w["status"] == "asteapta_oferta" and w["quotes"][0]["status"] == "draft"


def test_status_gate_before_approval(ctx):
    wid, _ = ctx["mk"]("GATE")
    for st in ("aprobata", "finalizata"):
        r = ctx["s"].post(f"{BASE}/work-orders/{wid}/status", json={"status": st})
        assert r.status_code == 400 and "deviz" in r.json()["detail"].lower()
    assert _wo(ctx, wid)["status"] == "asteapta_oferta"


def test_internal_paper_approval_sets_aprobata_then_qc_finalize(ctx):
    wid, _ = ctx["mk"]("PAPER")
    r = _dec(ctx, wid, {"approved": True, "signature": "", "paper_approved": True, "name": "TEST Client"})
    assert r.status_code == 200, r.text
    q = r.json()[0]
    assert q["status"] == "approved"
    assert q["decision"]["paper_approved"] is True and q["decision"]["signature"] == "" and q["decision"]["via"] == "service"
    w = _wo(ctx, wid)
    assert w["status"] == "aprobata" and w["approved_quote"] == 1
    assert w["status_history"][-1]["status"] == "aprobata"
    # persisted in DB
    dbq = ctx["db"].work_orders.find_one({"_id": ObjectId(wid)})["quotes"][0]
    assert dbq["decision"]["paper_approved"] is True
    # finalizata requires QC
    r = ctx["s"].post(f"{BASE}/work-orders/{wid}/status", json={"status": "finalizata"})
    assert r.status_code == 400 and "calit" in r.json()["detail"].lower()
    r = ctx["s"].put(f"{BASE}/work-orders/{wid}/qc", json={"items": {k: "C" for k in QC_KEYS}, "mechanic_signature": SIG, "chief_signature": SIG})
    assert r.status_code == 200 and r.json()["qc"]["passed"] is True
    r = ctx["s"].post(f"{BASE}/work-orders/{wid}/status", json={"status": "finalizata"})
    assert r.status_code == 200 and r.json()["status"] == "finalizata"


def test_signature_approval_records_paper_false(ctx):
    wid, _ = ctx["mk"]("SIG")
    r = _dec(ctx, wid, {"approved": True, "signature": SIG, "name": "TEST"})
    assert r.status_code == 200
    assert r.json()[0]["decision"]["paper_approved"] is False
    assert _wo(ctx, wid)["status"] == "aprobata"


def test_public_rejects_paper_approval(ctx):
    wid, q = ctx["mk"]("PUBPAPER")
    for body in ({"approved": True, "paper_approved": True, "name": "TEST"},
                 {"approved": True, "signature": SIG, "paper_approved": True, "name": "TEST"}):
        r = requests.post(f"{BASE}/public/quotes/{q['token']}/decision", json=body)
        assert r.status_code in (400, 403), r.text
    w = _wo(ctx, wid)
    assert w["status"] == "asteapta_oferta" and w["quotes"][0]["status"] == "draft"
    # public without signature also 400
    r = requests.post(f"{BASE}/public/quotes/{q['token']}/decision", json={"approved": True, "name": "TEST"})
    assert r.status_code == 400
    # public with signature still OK
    r = requests.post(f"{BASE}/public/quotes/{q['token']}/decision", json={"approved": True, "signature": SIG, "name": "TEST"})
    assert r.status_code == 200
    assert _wo(ctx, wid)["status"] == "aprobata"


def test_reject_without_signature_ok(ctx):
    wid, _ = ctx["mk"]("REJ")
    r = _dec(ctx, wid, {"approved": False, "reason": "TEST"})
    assert r.status_code == 200 and r.json()[0]["status"] == "rejected"
    assert _wo(ctx, wid)["status"] == "asteapta_oferta"
