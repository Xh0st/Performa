# Iteration 9: inline line edit (PUT /work-orders/{wid}/lines/{lid}), validation, LINE_LOCKED, status gate, paper quote approval.
import secrets
from datetime import datetime, timezone

import pytest
import requests
from bson import ObjectId

from warranty_fixtures import BASE, mdb, session

QC_KEYS = ["noxe", "frane", "geometrie", "faruri_geamuri_parbrize", "parametri_reglaje", "etanșeitate", "proba_drum"]
TAG = "LIE" + secrets.token_hex(3).upper()
REAL = ("CL-2026-00086", "CL-2026-00083", "CL-2026-00069")
SIG = "data:image/png;base64,TEST"


def iso():
    return datetime.now(timezone.utc).isoformat()


def lines():
    return [
        {"id": "li_part", "type": "part", "description": "TEST piesa", "qty": 2, "unit_price": 100, "discount": 0, "vat_rate": 21,
         "product_id": "", "code": "P-1", "unit": "buc", "source_warehouse": "Depozit Central"},
        {"id": "li_lab", "type": "labor", "description": "TEST manopera", "qty": 1, "unit_price": 150, "discount": 0, "vat_rate": 21,
         "product_id": "", "code": "", "unit": "ore", "labor_category": "mecanic_senior", "mechanic_id": ""},
    ]


@pytest.fixture(scope="module")
def ctx():
    db, s = mdb(), session()
    real = {n: db.work_orders.find_one({"number": n}) for n in REAL}
    cid = db.clients.insert_one({"name": f"TEST_Client {TAG}", "type": "pf", "phone": "0700000000", "email": "test@example.com",
                                 "created_at": iso()}).inserted_id
    vid = db.vehicles.insert_one({"client_id": str(cid), "vin": f"TEST{TAG}".ljust(17, "0")[:17], "plate": f"TS{TAG}",
                                  "make": "Test", "model": "Car", "mileage": 1000, "created_at": iso()}).inserted_id
    made = []

    def mk(suffix, status="diagnosticare", quotes=None, qc=None):
        doc = {"number": f"TEST-{TAG}-{suffix}", "client_id": str(cid), "vehicle_id": str(vid), "status": status, "mileage_in": 1000,
               "complaint": "TEST", "lines": lines(), "quotes": quotes or [], "qc": qc or {},
               "status_history": [], "created_at": iso(), "reception": {}, "mechanic_ids": []}
        wid = str(db.work_orders.insert_one(doc).inserted_id)
        made.append(wid)
        return wid

    mech = db.mechanics.find_one({"active": True}) or db.mechanics.find_one()
    yield {"s": s, "db": db, "mk": mk, "mech": str(mech["_id"]) if mech else None}
    for coll in ("notifications", "time_entries"):
        db[coll].delete_many({"work_order_id": {"$in": made}})
    db.audit_logs.delete_many({"entity_id": {"$in": made}})
    db.work_orders.delete_many({"$or": [{"_id": {"$in": [ObjectId(w) for w in made]}}, {"vehicle_id": str(vid)}]})
    db.vehicles.delete_one({"_id": vid})
    db.clients.delete_one({"_id": cid})
    for n, doc in real.items():
        assert db.work_orders.find_one({"number": n}) == doc, f"Real {n} was modified!"
    assert db.work_orders.count_documents({"number": {"$regex": TAG}}) == 0


def put(ctx, wid, lid, body):
    return ctx["s"].put(f"{BASE}/work-orders/{wid}/lines/{lid}", json=body)


def line(w, lid):
    return next(x for x in w["lines"] if x["id"] == lid)


# --- Part line update recalculates totals
def test_part_update_recalc(ctx):
    wid = ctx["mk"]("PART")
    r = put(ctx, wid, "li_part", {"description": "TEST piesa nou", "code": "P-NEW", "qty": 3, "unit_price": 200, "discount": 10})
    assert r.status_code == 200, r.text
    ln = line(r.json(), "li_part")
    assert ln["description"] == "TEST piesa nou" and ln["code"] == "P-NEW" and ln["qty"] == 3
    assert ln["source_warehouse"] == "Depozit Central"
    assert ln["unit_price"] == 200 and ln["discount"] == 10
    assert r.json()["totals"]["by_type"]["part"] == 540.0
    t = r.json()["totals"]
    assert t["net"] == 690.0 and t["vat"] == 144.9 and t["gross"] == 834.9
    g = ctx["s"].get(f"{BASE}/work-orders/{wid}").json()
    assert line(g, "li_part")["unit_price"] == 200 and g["totals"]["gross"] == 834.9


# --- Labor line update incl. mechanic
def test_labor_update_with_mechanic(ctx):
    if not ctx["mech"]:
        pytest.skip("no mechanic")
    wid = ctx["mk"]("LAB", status="in_lucru")
    r = put(ctx, wid, "li_lab", {"description": "TEST man nou", "qty": 2.5, "unit_price": 160, "discount": 5, "mechanic_id": ctx["mech"]})
    assert r.status_code == 200, r.text
    w = r.json()
    ln = line(w, "li_lab")
    assert ln["mechanic_id"] == ctx["mech"] and w["totals"]["by_type"]["labor"] == 380.0
    assert ctx["mech"] in w["mechanic_ids"]
    assert w["totals"]["net"] == 580.0


# --- Validation
@pytest.mark.parametrize("body", [{"qty": 0}, {"qty": -1}, {"unit_price": -0.01}, {"discount": -1}, {"discount": 100.5},
                                  {"description": "   "}])
def test_validation_400(ctx, body):
    wid = ctx["mk"]("VAL")
    r = put(ctx, wid, "li_part", body)
    assert r.status_code == 400, f"{body} -> {r.status_code} {r.text}"


def test_invalid_mechanic(ctx):
    wid = ctx["mk"]("VALM")
    r = put(ctx, wid, "li_lab", {"mechanic_id": "000000000000000000000000"})
    assert r.status_code in (400, 404), r.text
    r2 = put(ctx, wid, "li_lab", {"mechanic_id": "nonsense"})
    assert r2.status_code in (400, 404), r2.text


def test_edge_bounds_ok(ctx):
    wid = ctx["mk"]("EDGE")
    r = put(ctx, wid, "li_part", {"unit_price": 0, "discount": 100})
    assert r.status_code == 200 and r.json()["totals"]["by_type"]["part"] == 0


@pytest.mark.parametrize("body", [{"qty": None}, {"description": None}, {"unit_price": None}, {"discount": None}])
def test_explicit_null_no_500(ctx, body):
    wid = ctx["mk"]("NULL")
    r = put(ctx, wid, "li_part", body)
    assert r.status_code != 500, f"{body} -> 500"
    g = ctx["s"].get(f"{BASE}/work-orders/{wid}")
    assert g.status_code == 200, f"GET after {body} -> {g.status_code} (corrupted line)"


def test_unknown_line_404(ctx):
    wid = ctx["mk"]("404")
    assert put(ctx, wid, "nope", {"qty": 1}).status_code == 404


# --- LINE_LOCKED
@pytest.mark.parametrize("status", ["finalizata", "facturata", "inchisa"])
def test_locked_statuses(ctx, status):
    wid = ctx["mk"](f"LCK{status}", status=status)
    s = ctx["s"]
    assert put(ctx, wid, "li_part", {"qty": 5}).status_code == 400
    assert s.post(f"{BASE}/work-orders/{wid}/lines", json={"type": "labor", "description": "TEST", "qty": 1}).status_code == 400
    assert s.delete(f"{BASE}/work-orders/{wid}/lines/li_part").status_code == 400
    w = ctx["db"].work_orders.find_one({"_id": ObjectId(wid)})
    assert len(w["lines"]) == 2 and w["lines"][0]["qty"] == 2


@pytest.mark.parametrize("status", ["noua", "diagnosticare", "asteapta_oferta", "aprobata", "in_lucru", "asteapta_piese"])
def test_unlocked_statuses(ctx, status):
    wid = ctx["mk"](f"ULK{status}", status=status)
    assert put(ctx, wid, "li_part", {"discount": 20}).status_code == 200


# --- Status gate
@pytest.mark.parametrize("target", ["aprobata", "finalizata"])
def test_status_gate_no_quote(ctx, target):
    wid = ctx["mk"](f"G{target}", status="in_lucru")
    r = ctx["s"].post(f"{BASE}/work-orders/{wid}/status", json={"status": target})
    assert r.status_code == 400


def test_quote_flow_paper_then_finalize(ctx):
    s = ctx["s"]
    wid = ctx["mk"]("FLOW", status="diagnosticare")
    q = s.post(f"{BASE}/work-orders/{wid}/quotes", json={"valid_days": 7})
    assert q.status_code == 200
    token = q.json()[0]["token"]
    # no signature, no paper -> 400
    assert s.post(f"{BASE}/work-orders/{wid}/quotes/1/decision", json={"approved": True}).status_code == 400
    # public paper -> 403
    assert requests.post(f"{BASE}/public/quotes/{token}/decision", json={"approved": True, "paper_approved": True}).status_code == 403
    assert requests.post(f"{BASE}/public/quotes/{token}/decision", json={"approved": True, "signature": SIG, "paper_approved": True}).status_code == 403
    # internal paper OK
    r = s.post(f"{BASE}/work-orders/{wid}/quotes/1/decision", json={"approved": True, "paper_approved": True, "name": "TEST"})
    assert r.status_code == 200, r.text
    dec = r.json()[0]["decision"]
    assert r.json()[0]["status"] == "approved" and dec["paper_approved"] is True and dec["signature"] == "" and dec["via"] == "service"
    w = s.get(f"{BASE}/work-orders/{wid}").json()
    assert w["status"] == "aprobata"
    # finalizata without QC -> 400
    assert s.post(f"{BASE}/work-orders/{wid}/status", json={"status": "finalizata"}).status_code == 400
    # editing still allowed before finalizata
    assert put(ctx, wid, "li_part", {"unit_price": 110}).status_code == 200
    assert s.put(f"{BASE}/work-orders/{wid}/qc", json={"items": {k: "C" for k in QC_KEYS}, "mechanic_signature": SIG,
                                                        "chief_signature": SIG}).json()["qc"]["passed"] is True
    assert s.post(f"{BASE}/work-orders/{wid}/status", json={"status": "finalizata"}).status_code == 200
    assert put(ctx, wid, "li_part", {"unit_price": 120}).status_code == 400


def test_public_signed_still_works(ctx):
    s = ctx["s"]
    wid = ctx["mk"]("PUB", status="diagnosticare")
    token = s.post(f"{BASE}/work-orders/{wid}/quotes", json={"valid_days": 7}).json()[0]["token"]
    r = requests.post(f"{BASE}/public/quotes/{token}/decision", json={"approved": True, "signature": SIG, "name": "TEST"})
    assert r.status_code == 200
    assert s.get(f"{BASE}/work-orders/{wid}").json()["status"] == "aprobata"


# --- Warranty work orders: lines locked (PUT/POST/DELETE)
def test_warranty_lines_locked(ctx):
    wid = ctx["mk"]("WAR", status="in_lucru")
    ctx["db"].work_orders.update_one({"_id": ObjectId(wid)}, {"$set": {"is_warranty": True}})
    s = ctx["s"]
    r = put(ctx, wid, "li_part", {"unit_price": 999})
    assert r.status_code == 400 and "garan" in r.json()["detail"].lower()
    assert s.post(f"{BASE}/work-orders/{wid}/lines", json={"type": "labor", "description": "TEST", "qty": 1}).status_code == 400
    assert s.delete(f"{BASE}/work-orders/{wid}/lines/li_part").status_code == 400
    assert ctx["db"].work_orders.find_one({"_id": ObjectId(wid)})["lines"][0]["unit_price"] == 100


# --- Part source_warehouse/product_id not changeable via PUT (extra fields ignored)
def test_part_source_readonly(ctx):
    wid = ctx["mk"]("SRC")
    r = put(ctx, wid, "li_part", {"source_warehouse": "HACK", "product_id": "x", "vat_rate": 0, "type": "labor", "unit_price": 50})
    assert r.status_code == 200
    ln = line(r.json(), "li_part")
    assert ln["source_warehouse"] == "Depozit Central" and ln["vat_rate"] == 21 and ln["type"] == "part" and ln["unit_price"] == 50
