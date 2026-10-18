# Iteration 10 retest: PUT /work-orders/{wid}/lines/{lid} explicit-null handling (no 500, no data change), empty body 400.
import secrets
from datetime import datetime, timezone

import pytest
from bson import ObjectId

from warranty_fixtures import BASE, mdb, session

TAG = "NUL" + secrets.token_hex(3).upper()
REAL = ("CL-2026-00086", "CL-2026-00083", "CL-2026-00069")
FIELDS = ["description", "code", "qty", "unit_price", "discount", "mechanic_id"]


def iso():
    return datetime.now(timezone.utc).isoformat()


def lines():
    return [
        {"id": "n_part", "type": "part", "description": "TEST piesa", "qty": 2, "unit_price": 100, "discount": 5, "vat_rate": 21,
         "product_id": "", "code": "P-1", "unit": "buc", "source_warehouse": "Depozit Central"},
        {"id": "n_lab", "type": "labor", "description": "TEST manopera", "qty": 1, "unit_price": 150, "discount": 0, "vat_rate": 21,
         "product_id": "", "code": "", "unit": "ore", "labor_category": "mecanic_senior", "mechanic_id": "m_keep"},
    ]


@pytest.fixture(scope="module")
def ctx():
    db, s = mdb(), session()
    real = {n: db.work_orders.find_one({"number": n}) for n in REAL}
    cid = db.clients.insert_one({"name": f"TEST_Client {TAG}", "type": "pf", "phone": "0700000000", "created_at": iso()}).inserted_id
    vid = db.vehicles.insert_one({"client_id": str(cid), "vin": f"TEST{TAG}".ljust(17, "0")[:17], "plate": f"TS{TAG}",
                                  "make": "Test", "model": "Car", "mileage": 1000, "created_at": iso()}).inserted_id
    made = []

    def mk(suffix):
        doc = {"number": f"TEST-{TAG}-{suffix}", "client_id": str(cid), "vehicle_id": str(vid), "status": "diagnosticare",
               "mileage_in": 1000, "complaint": "TEST", "lines": lines(), "quotes": [], "qc": {}, "status_history": [],
               "created_at": iso(), "reception": {}, "mechanic_ids": ["m_keep"]}
        wid = str(db.work_orders.insert_one(doc).inserted_id)
        made.append(wid)
        return wid

    yield {"s": s, "db": db, "mk": mk}
    db.audit_logs.delete_many({"entity_id": {"$in": made}})
    db.work_orders.delete_many({"vehicle_id": str(vid)})
    db.vehicles.delete_one({"_id": vid})
    db.clients.delete_one({"_id": cid})
    for n, doc in real.items():
        assert db.work_orders.find_one({"number": n}) == doc, f"Real {n} was modified!"
    assert db.work_orders.count_documents({"number": {"$regex": TAG}}) == 0


def raw_lines(ctx, wid):
    return ctx["db"].work_orders.find_one({"_id": ObjectId(wid)})["lines"]


# --- Each field explicitly null (part + labor) -> 400, data unchanged
@pytest.mark.parametrize("lid", ["n_part", "n_lab"])
@pytest.mark.parametrize("field", FIELDS)
def test_single_null_400_unchanged(ctx, field, lid):
    wid = ctx["mk"](f"S{field[:3]}{lid[-1]}")
    before = raw_lines(ctx, wid)
    r = ctx["s"].put(f"{BASE}/work-orders/{wid}/lines/{lid}", json={field: None})
    assert r.status_code == 400, f"{field}=null -> {r.status_code} {r.text}"
    assert "detail" in r.json()
    assert raw_lines(ctx, wid) == before


# --- All fields null at once -> 400, unchanged
def test_all_null_400(ctx):
    wid = ctx["mk"]("ALL")
    before = raw_lines(ctx, wid)
    r = ctx["s"].put(f"{BASE}/work-orders/{wid}/lines/n_part", json={f: None for f in FIELDS})
    assert r.status_code == 400, r.text
    assert raw_lines(ctx, wid) == before


# --- Empty body / only unknown fields -> 400
@pytest.mark.parametrize("body", [{}, {"source_warehouse": "HACK"}, {"vat_rate": 0, "type": "labor"}])
def test_no_updatable_field_400(ctx, body):
    wid = ctx["mk"]("EMP")
    before = raw_lines(ctx, wid)
    r = ctx["s"].put(f"{BASE}/work-orders/{wid}/lines/n_part", json=body)
    assert r.status_code == 400, f"{body} -> {r.status_code}"
    assert raw_lines(ctx, wid) == before


# --- Mixed null + valid: nulls ignored, valid applied, other fields untouched
def test_mixed_null_and_valid(ctx):
    wid = ctx["mk"]("MIX")
    r = ctx["s"].put(f"{BASE}/work-orders/{wid}/lines/n_part",
                     json={"qty": 3, "description": None, "unit_price": None, "discount": None, "code": None})
    assert r.status_code == 200, r.text
    ln = next(x for x in r.json()["lines"] if x["id"] == "n_part")
    assert ln["qty"] == 3 and ln["description"] == "TEST piesa" and ln["unit_price"] == 100 and ln["discount"] == 5 and ln["code"] == "P-1"
    assert r.json()["totals"]["by_type"]["part"] == 285.0
    g = ctx["s"].get(f"{BASE}/work-orders/{wid}")
    assert g.status_code == 200
    assert next(x for x in g.json()["lines"] if x["id"] == "n_part")["qty"] == 3


# --- Labor: mechanic_id null ignored while price updated, mechanic kept
def test_labor_mechanic_null_kept(ctx):
    wid = ctx["mk"]("MEC")
    r = ctx["s"].put(f"{BASE}/work-orders/{wid}/lines/n_lab", json={"unit_price": 200, "mechanic_id": None})
    assert r.status_code == 200, r.text
    ln = next(x for x in raw_lines(ctx, wid) if x["id"] == "n_lab")
    assert ln["unit_price"] == 200 and ln["mechanic_id"] == "m_keep"


# --- Wrong types still 422 (not 500)
@pytest.mark.parametrize("body", [{"qty": "abc"}, {"discount": [1]}, {"description": {"a": 1}}])
def test_wrong_types_422(ctx, body):
    wid = ctx["mk"]("TYP")
    r = ctx["s"].put(f"{BASE}/work-orders/{wid}/lines/n_part", json=body)
    assert r.status_code == 422, f"{body} -> {r.status_code}"
