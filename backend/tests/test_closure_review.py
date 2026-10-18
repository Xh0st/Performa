# Direct closure of non-invoiced work orders + Administrare > Verificare închideri (approve / reopen) regression tests (iteration 7)
import secrets
from datetime import datetime, timezone

import pytest
from bson import ObjectId

from warranty_fixtures import BASE, mdb, session

TAG = "CLR" + secrets.token_hex(3).upper()
REAL_NUMBER = "CL-2026-00086"
PROJ = {"status": 1, "quotes": 1, "status_history": 1, "closure_review": 1, "pre_closure_status": 1, "closed_at": 1, "invoice_id": 1}
OPERATIONAL = ["noua", "diagnosticare", "asteapta_oferta", "aprobata", "in_lucru", "asteapta_piese", "finalizata"]
APPROVED_Q = [{"version": 1, "status": "approved", "number": "DV-TEST"}]


def iso():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture(scope="module")
def ctx():
    db = mdb()
    real = db.work_orders.find_one({"number": REAL_NUMBER}, PROJ)
    s = session()
    cid = db.clients.insert_one({"name": f"TEST_Client {TAG}", "type": "pf", "phone": "0700000000", "created_at": iso()}).inserted_id
    vid = db.vehicles.insert_one({"client_id": str(cid), "vin": f"TEST{TAG}".ljust(17, "0")[:17], "plate": f"TS{TAG}",
                                  "make": "Test", "model": "Car", "mileage": 1000, "created_at": iso()}).inserted_id
    made = []

    def mk(suffix, status="asteapta_oferta", quotes=None, qc=None, lines=None, history=None, **extra):
        doc = {"number": f"TEST-{TAG}-{suffix}", "client_id": str(cid), "vehicle_id": str(vid), "status": status, "mileage_in": 1000,
               "complaint": "TEST", "lines": lines or [], "quotes": quotes or [], "qc": qc or {},
               "status_history": history if history is not None else [{"status": status, "at": iso(), "by": "TEST", "note": ""}],
               "created_at": iso(), "reception": {}, "mechanic_ids": []} | extra
        wid = str(db.work_orders.insert_one(doc).inserted_id)
        made.append(wid)
        return wid

    def listed():
        r = s.get(f"{BASE}/closure-exceptions/work-orders")
        assert r.status_code == 200, r.text
        return {x["id"]: x for x in r.json()}

    yield {"s": s, "db": db, "mk": mk, "real": real, "listed": listed}
    db.work_orders.delete_many({"$or": [{"_id": {"$in": [ObjectId(w) for w in made]}}, {"vehicle_id": str(vid)}]})
    db.audit_logs.delete_many({"entity_id": {"$in": made}})
    db.time_entries.delete_many({"work_order_id": {"$in": made}})
    db.notifications.delete_many({"work_order_id": {"$in": made}})
    db.vehicles.delete_one({"_id": vid})
    db.clients.delete_one({"_id": cid})
    assert db.work_orders.find_one({"number": REAL_NUMBER}, PROJ) == real, "Real CL-2026-00086 was modified!"
    assert db.work_orders.count_documents({"number": {"$regex": TAG}}) == 0


# --- approved quote: every operational status -> inchisa without QC, pre_closure_status kept, listed
@pytest.mark.parametrize("st", OPERATIONAL)
def test_approved_quote_any_status_closes_without_qc(ctx, st):
    s = ctx["s"]
    wid = ctx["mk"](f"APP{st}", status=st, quotes=APPROVED_Q)
    r = s.post(f"{BASE}/work-orders/{wid}/status", json={"status": "inchisa"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "inchisa" and d["closed_at"]
    assert d["pre_closure_status"] == st
    assert d["closure_quote_rule"]["review"] is True
    assert d["status_history"][-1]["status"] == "inchisa"
    row = ctx["listed"]().get(wid)
    assert row, "closed WO not in closure review list"
    assert row["number"] == f"TEST-{TAG}-APP{st}" and row["client_name"].startswith("TEST_Client")


# --- no quote / rejected (real API flow) / draft quote -> direct close
def test_no_quote_closes(ctx):
    s, wid = ctx["s"], ctx["mk"]("NOQ", status="noua", quotes=[])
    r = s.post(f"{BASE}/work-orders/{wid}/status", json={"status": "inchisa"})
    assert r.status_code == 200, r.text
    assert r.json()["pre_closure_status"] == "noua"
    assert wid in ctx["listed"]()
    ctx["noq"] = wid


def test_rejected_quote_closes(ctx):
    s = ctx["s"]
    wid = ctx["mk"]("REJ", status="diagnosticare")
    assert s.post(f"{BASE}/work-orders/{wid}/lines", json={"type": "labor", "description": "TEST manopera", "qty": 1, "unit_price": 100}).status_code == 200
    assert s.post(f"{BASE}/work-orders/{wid}/quotes", json={"valid_days": 7}).status_code == 200
    assert s.post(f"{BASE}/work-orders/{wid}/quotes/1/decision", json={"approved": False, "reason": "TEST"}).status_code == 200
    r = s.post(f"{BASE}/work-orders/{wid}/status", json={"status": "inchisa"})
    assert r.status_code == 200, r.text
    assert r.json()["pre_closure_status"] == "asteapta_oferta"
    assert wid in ctx["listed"]()


def test_draft_quote_closes(ctx):
    wid = ctx["mk"]("DRAFT", quotes=[{"version": 1, "status": "draft"}])
    r = ctx["s"].post(f"{BASE}/work-orders/{wid}/status", json={"status": "inchisa"})
    assert r.status_code == 200, r.text


def test_warranty_wo_closes_and_listed(ctx):
    wid = ctx["mk"]("GAR", is_warranty=True)
    r = ctx["s"].post(f"{BASE}/work-orders/{wid}/status", json={"status": "inchisa"})
    assert r.status_code == 200, r.text
    assert wid in ctx["listed"]()


# --- finalizata still requires QC
def test_finalizata_still_requires_qc(ctx):
    wid = ctx["mk"]("FINQC", status="in_lucru", quotes=APPROVED_Q)
    r = ctx["s"].post(f"{BASE}/work-orders/{wid}/status", json={"status": "finalizata"})
    assert r.status_code == 400


# --- invoiced orders can never become inchisa
@pytest.mark.parametrize("target", ["inchisa", "finalizata", "in_lucru", "facturata"])
def test_facturata_immutable(ctx, target):
    s = ctx["s"]
    wid = ctx.get("fact") or ctx["mk"]("FACT", status="facturata", invoice_id=str(ObjectId()), invoiced_at=iso(), quotes=APPROVED_Q)
    ctx["fact"] = wid
    r = s.post(f"{BASE}/work-orders/{wid}/status", json={"status": target})
    assert r.status_code == 400
    assert s.get(f"{BASE}/work-orders/{wid}").json()["status"] == "facturata"


def test_invoice_id_with_non_facturata_status_cannot_close(ctx):
    wid = ctx["mk"]("INVID", status="finalizata", invoice_id=str(ObjectId()), quotes=APPROVED_Q)
    r = ctx["s"].post(f"{BASE}/work-orders/{wid}/status", json={"status": "inchisa"})
    assert r.status_code == 400, f"WO with invoice_id was closed: {r.status_code}"


# --- iteration 8: invoice_id data drift - any stored status, any target status -> 400, never listed
@pytest.mark.parametrize("st", OPERATIONAL + ["inchisa"])
def test_invoice_id_drift_any_status_rejects_close(ctx, st):
    s = ctx["s"]
    wid = ctx["mk"](f"DRIFT{st}", status=st, invoice_id=str(ObjectId()), quotes=APPROVED_Q,
                    **({"closed_at": iso()} if st == "inchisa" else {}))
    for target in ("inchisa", "in_lucru", "noua"):
        r = s.post(f"{BASE}/work-orders/{wid}/status", json={"status": target})
        assert r.status_code == 400, f"{st}->{target}: {r.status_code} {r.text}"
    assert s.get(f"{BASE}/work-orders/{wid}").json()["status"] == st
    assert wid not in ctx["listed"]()
    assert s.post(f"{BASE}/work-orders/{wid}/closure-review", json={}).status_code == 400
    assert s.post(f"{BASE}/work-orders/{wid}/reopen", json={}).status_code == 400


def test_list_includes_empty_or_null_invoice_id(ctx):
    w1 = ctx["mk"]("NULLINV", status="inchisa", invoice_id=None, closed_at=iso(), pre_closure_status="aprobata")
    w2 = ctx["mk"]("EMPTYINV", status="inchisa", invoice_id="", closed_at=iso(), pre_closure_status="aprobata")
    listed = ctx["listed"]()
    assert w1 in listed and w2 in listed
    r = ctx["s"].post(f"{BASE}/work-orders/{w1}/reopen", json={})
    assert r.status_code == 200 and r.json()["status"] == "aprobata"
    assert w1 not in ctx["listed"]()


def test_list_excludes_invoiced(ctx):
    for row in ctx["listed"]().values():
        assert not row.get("invoice_id"), f"{row['number']} invoiced but listed"
        assert row["status"] == "inchisa"


# --- approve: removed from list, stays inchisa
def test_approve_removes_from_list(ctx):
    s, wid = ctx["s"], ctx["noq"]
    r = s.post(f"{BASE}/work-orders/{wid}/closure-review", json={"note": "TEST review"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "inchisa" and d["closure_review"]["status"] == "aprobat" and d["closure_review"]["note"] == "TEST review"
    assert wid not in ctx["listed"]()
    assert s.get(f"{BASE}/work-orders/{wid}").json()["status"] == "inchisa"


# --- reopen: back to pre_closure_status, removed from list, history kept; re-close re-enters list
def test_reopen_restores_previous_status(ctx):
    s = ctx["s"]
    wid = ctx["mk"]("REOP", status="asteapta_piese", quotes=APPROVED_Q)
    assert s.post(f"{BASE}/work-orders/{wid}/status", json={"status": "inchisa"}).status_code == 200
    r = s.post(f"{BASE}/work-orders/{wid}/reopen", json={"note": ""})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "asteapta_piese"
    assert d["reopened_at"] and d["reopened_by"]
    hist = [h["status"] for h in d["status_history"]]
    assert hist[-2:] == ["inchisa", "asteapta_piese"]
    assert d["status_history"][-1]["note"] == "Redeschis din verificare închideri"
    assert wid not in ctx["listed"]()
    # editable again
    assert s.post(f"{BASE}/work-orders/{wid}/lines", json={"type": "labor", "description": "TEST", "qty": 1, "unit_price": 1}).status_code == 200
    # close again from another status -> listed again, new pre_closure_status
    assert s.post(f"{BASE}/work-orders/{wid}/status", json={"status": "in_lucru"}).status_code == 200
    r2 = s.post(f"{BASE}/work-orders/{wid}/status", json={"status": "inchisa"})
    assert r2.status_code == 200 and r2.json()["pre_closure_status"] == "in_lucru"
    assert wid in ctx["listed"]()


def test_reopen_after_approve(ctx):
    s, wid = ctx["s"], ctx["noq"]
    r = s.post(f"{BASE}/work-orders/{wid}/reopen", json={"note": "TEST"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "noua" and not r.json().get("closure_review")


def test_reopen_legacy_without_pre_closure_status(ctx):
    hist = [{"status": "noua", "at": iso(), "by": "T", "note": ""}, {"status": "in_lucru", "at": iso(), "by": "T", "note": ""},
            {"status": "inchisa", "at": iso(), "by": "T", "note": ""}]
    wid = ctx["mk"]("LEG", status="inchisa", history=hist, closed_at=iso())
    r = ctx["s"].post(f"{BASE}/work-orders/{wid}/reopen", json={})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_lucru"


# --- validation / RBAC
def test_review_and_reopen_require_closed_uninvoiced(ctx):
    s = ctx["s"]
    open_wid = ctx["mk"]("OPEN", status="in_lucru")
    inv_wid = ctx["mk"]("INVCL", status="inchisa", invoice_id=str(ObjectId()), closed_at=iso())
    for wid in (open_wid, inv_wid):
        assert s.post(f"{BASE}/work-orders/{wid}/closure-review", json={}).status_code == 400
        assert s.post(f"{BASE}/work-orders/{wid}/reopen", json={}).status_code == 400
    assert inv_wid not in ctx["listed"](), "invoiced closed WO appears in closure review list"


def test_non_admin_forbidden(ctx):
    s2 = session("mecanic@")
    wid = ctx["mk"]("RBAC", status="inchisa", closed_at=iso())
    assert s2.get(f"{BASE}/closure-exceptions/work-orders").status_code == 403
    assert s2.post(f"{BASE}/work-orders/{wid}/closure-review", json={}).status_code == 403
    assert s2.post(f"{BASE}/work-orders/{wid}/reopen", json={}).status_code == 403
    assert ctx["s"].get(f"{BASE}/work-orders/{wid}").json()["status"] == "inchisa"


def test_unauthenticated_401():
    import requests
    assert requests.get(f"{BASE}/closure-exceptions/work-orders").status_code == 401


# --- real CL-2026-00086: read only
def test_real_wo_readonly_snapshot(ctx):
    real = ctx["real"]
    assert real, "CL-2026-00086 missing"
    assert not real.get("invoice_id")
    listed = ctx["listed"]()
    if real["status"] == "inchisa" and not real.get("closure_review"):
        assert str(real["_id"]) in listed
    else:
        pytest.skip(f"CL-2026-00086 is currently '{real['status']}' (changed by a real user, not the test) - not in list")
