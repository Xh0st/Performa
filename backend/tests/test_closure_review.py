# Closure review / quote closure rules / facturata immutability regression tests (iteration 7)
import os
import secrets
from datetime import datetime, timezone

import pytest
from bson import ObjectId

from warranty_fixtures import BASE, mdb, session

TAG = "CLR" + secrets.token_hex(3).upper()
REAL_NUMBER = "CL-2026-00083"
QC_OK = {"passed": True, "at": "2026-01-01T00:00:00+00:00", "inspector_name": "TEST"}


def iso():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture(scope="module")
def ctx():
    db = mdb()
    real = db.work_orders.find_one({"number": REAL_NUMBER}, {"status": 1, "quotes": 1, "status_history": 1, "closure_review": 1})
    s = session()
    cid = db.clients.insert_one({"name": f"TEST_Client {TAG}", "type": "pf", "phone": "0700000000", "created_at": iso()}).inserted_id
    vid = db.vehicles.insert_one({"client_id": str(cid), "vin": f"TEST{TAG}".ljust(17, "0")[:17], "plate": f"TS{TAG}",
                                  "make": "Test", "model": "Car", "mileage": 1000, "created_at": iso()}).inserted_id
    made = []

    def mk(suffix, status="asteapta_oferta", quotes=None, qc=None, lines=None, **extra):
        doc = {"number": f"TEST-{TAG}-{suffix}", "client_id": str(cid), "vehicle_id": str(vid), "status": status, "mileage_in": 1000,
               "complaint": "TEST", "lines": lines or [], "quotes": quotes or [], "qc": qc or {}, "status_history": [],
               "created_at": iso(), "reception": {}, "mechanic_ids": []} | extra
        wid = str(db.work_orders.insert_one(doc).inserted_id)
        made.append(wid)
        return wid

    yield {"s": s, "db": db, "mk": mk, "real": real}
    db.work_orders.delete_many({"$or": [{"_id": {"$in": [ObjectId(w) for w in made]}}, {"vehicle_id": str(vid)}]})
    db.audit_logs.delete_many({"entity_id": {"$in": made}})
    db.time_entries.delete_many({"work_order_id": {"$in": made}})
    db.notifications.delete_many({"work_order_id": {"$in": made}})
    db.vehicles.delete_one({"_id": vid})
    db.clients.delete_one({"_id": cid})
    after = db.work_orders.find_one({"number": REAL_NUMBER}, {"status": 1, "quotes": 1, "status_history": 1, "closure_review": 1})
    assert after == real, "Real CL-2026-00083 was modified!"
    assert db.work_orders.count_documents({"number": {"$regex": TAG}}) == 0


# --- quote closure rule: no quote -> direct close
def test_no_quote_direct_close_from_asteapta_oferta(ctx):
    s, wid = ctx["s"], ctx["mk"]("NOQ")
    r = s.post(f"{BASE}/work-orders/{wid}/status", json={"status": "inchisa"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "inchisa"
    assert d["closure_quote_rule"]["reason"] == "fara_deviz_generat" and d["closure_quote_rule"]["review"] is True
    assert d["closed_at"]
    g = s.get(f"{BASE}/work-orders/{wid}").json()
    assert g["status"] == "inchisa"
    ctx["noq"] = wid


# --- exceptions list contains it, review removes it, history persists
def test_exception_listed_then_reviewed_disappears(ctx):
    s, wid = ctx["s"], ctx["noq"]
    lst = s.get(f"{BASE}/closure-exceptions/work-orders").json()
    assert wid in [x["id"] for x in lst]
    r = s.post(f"{BASE}/work-orders/{wid}/closure-review", json={"note": "TEST review"})
    assert r.status_code == 200, r.text
    assert r.json()["closure_review"]["note"] == "TEST review"
    lst2 = s.get(f"{BASE}/closure-exceptions/work-orders").json()
    assert wid not in [x["id"] for x in lst2]
    g = s.get(f"{BASE}/work-orders/{wid}").json()
    assert g["closure_review"]["by"] and g["closure_review"]["at"]


# --- rejected quote via real API flow can be closed
def test_rejected_quote_can_close(ctx):
    s = ctx["s"]
    wid = ctx["mk"]("REJ", status="diagnosticare")
    r = s.post(f"{BASE}/work-orders/{wid}/lines", json={"type": "labor", "description": "TEST manopera", "qty": 1, "unit_price": 100})
    assert r.status_code == 200, r.text
    q = s.post(f"{BASE}/work-orders/{wid}/quotes", json={"valid_days": 7})
    assert q.status_code == 200, q.text
    assert s.get(f"{BASE}/work-orders/{wid}").json()["status"] == "asteapta_oferta"
    # draft blocks
    b = s.post(f"{BASE}/work-orders/{wid}/status", json={"status": "inchisa"})
    assert b.status_code == 400
    dec = s.post(f"{BASE}/work-orders/{wid}/quotes/1/decision", json={"approved": False, "reason": "TEST"})
    assert dec.status_code == 200, dec.text
    r2 = s.post(f"{BASE}/work-orders/{wid}/status", json={"status": "inchisa"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["closure_quote_rule"]["reason"] == "deviz_respins"
    assert wid in [x["id"] for x in s.get(f"{BASE}/closure-exceptions/work-orders").json()]


# --- draft/sent quote blocks finalizata and inchisa (even with QC passed)
@pytest.mark.parametrize("qstatus", ["draft", "sent"])
def test_pending_quote_blocks(ctx, qstatus):
    s = ctx["s"]
    wid = ctx["mk"](f"PEND{qstatus}", quotes=[{"version": 1, "status": qstatus, "number": "DV-TEST"}], qc=QC_OK)
    for st in ("finalizata", "inchisa"):
        r = s.post(f"{BASE}/work-orders/{wid}/status", json={"status": st})
        assert r.status_code == 400, f"{st}: {r.text}"
        assert "Devizul" in r.json().get("detail", "")
    assert s.get(f"{BASE}/work-orders/{wid}").json()["status"] == "asteapta_oferta"


# --- other allowed exceptions: warranty (no review), closure categories (review)
@pytest.mark.parametrize("cat", ["fara_cost", "diagnoza", "constatare"])
def test_closure_category_allows_close(ctx, cat):
    s = ctx["s"]
    wid = ctx["mk"](f"CAT{cat}", status="in_lucru")
    u = s.put(f"{BASE}/work-orders/{wid}", json={"closure_category": cat})
    assert u.status_code == 200 and u.json()["closure_category"] == cat
    r = s.post(f"{BASE}/work-orders/{wid}/status", json={"status": "inchisa"})
    assert r.status_code == 200, r.text
    assert r.json()["closure_quote_rule"] == {"allowed": True, "reason": cat, "review": True}


def test_warranty_allows_close_without_review(ctx):
    s = ctx["s"]
    wid = ctx["mk"]("GAR", is_warranty=True)
    r = s.post(f"{BASE}/work-orders/{wid}/status", json={"status": "inchisa"})
    assert r.status_code == 200, r.text
    assert r.json()["closure_quote_rule"]["review"] is False
    assert wid not in [x["id"] for x in s.get(f"{BASE}/closure-exceptions/work-orders").json()]


def test_invalid_closure_category_rejected(ctx):
    wid = ctx["mk"]("BADCAT")
    r = ctx["s"].put(f"{BASE}/work-orders/{wid}", json={"closure_category": "xyz"})
    assert r.status_code == 400


# --- facturata is immutable
@pytest.mark.parametrize("target", ["inchisa", "finalizata", "in_lucru", "facturata"])
def test_facturata_immutable(ctx, target):
    s = ctx["s"]
    wid = ctx.get("fact") or ctx["mk"]("FACT", status="facturata", qc=QC_OK, invoiced_at=iso(),
                                       lines=[{"id": "l1", "type": "labor", "description": "x", "qty": 1, "unit_price": 10, "discount": 0, "vat_rate": 21}])
    ctx["fact"] = wid
    r = s.post(f"{BASE}/work-orders/{wid}/status", json={"status": target})
    assert r.status_code == 400
    assert s.get(f"{BASE}/work-orders/{wid}").json()["status"] == "facturata"


# --- review endpoint permissions/validation
def test_review_not_needed_returns_400(ctx):
    wid = ctx["mk"]("APPR", quotes=[{"version": 1, "status": "approved"}])
    r = ctx["s"].post(f"{BASE}/work-orders/{wid}/closure-review", json={"note": ""})
    assert r.status_code == 400


def test_non_admin_cannot_review(ctx):
    s2 = session("mecanic@")
    r = s2.get(f"{BASE}/closure-exceptions/work-orders")
    assert r.status_code == 403
    r = s2.post(f"{BASE}/work-orders/{ctx['noq']}/closure-review", json={})
    assert r.status_code == 403


# --- real CL-2026-00083: read only
def test_real_wo_readonly(ctx):
    real = ctx["real"]
    assert real, "CL-2026-00083 missing"
    assert real["status"] == "asteapta_oferta"
    assert not real.get("quotes")
