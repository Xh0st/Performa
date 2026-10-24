# Iter32: Cash payouts (decont/dispozitie plata), cash receipt reversal (storno chitanta/bon), range registers + PDF.
# All TEST_ data is removed in teardown (clients, invoices, payments, cash_movements, audit_logs) and counters restored.
import os
import secrets
from datetime import datetime, timezone, date, timedelta

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
TAG = secrets.token_hex(3).upper()
COUNTERS = ["pay_chitanta", "pay_bon_fiscal", "pay_bon_pos", "cash_deposit", "cash_expense_settlement",
            "cash_payment_order", "cash_receipt_reversal"]
TODAY = datetime.now(timezone.utc).date().isoformat()


def _creds(key):
    line = [ln for ln in open("/app/memory/test_credentials.md").read().splitlines() if key in ln][0]
    em, pw = [x.strip() for x in line.lstrip("- ").split("/")[:2]]
    return em, pw.split()[0]


@pytest.fixture(scope="module")
def ctx():
    s = requests.Session()
    em, pw = _creds("andrei.melek")
    r = s.post(f"{BASE}/auth/login", json={"email": em, "password": pw})
    assert r.status_code == 200, r.text
    user = r.json()["user"]
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    tid, bid = user["tenant_id"], user["active_branch_id"]
    counters = {c: (db.counters.find_one({"_id": f"{tid}:{bid}:{c}"}) or {}).get("seq") for c in COUNTERS}
    movements_before = {m["_id"] for m in db.cash_movements.find({}, {"_id": 1})}
    st = {"s": s, "db": db, "tid": tid, "bid": bid, "invoices": []}
    pf = s.post(f"{BASE}/clients", json={"type": "pf", "name": f"TEST_PF Payout {TAG}", "phone": "0700000002"})
    assert pf.status_code == 200, pf.text
    st["pf"] = pf.json()

    def make_invoice(gross, num):
        doc = {"type": "fiscal", "series": "TSTP", "number": f"{TAG}{num}", "issue_date": "2026-01-01", "due_date": "2026-01-02",
               "client_id": st["pf"]["id"], "buyer": {"name": "TEST"}, "lines": [],
               "totals": {"net": round(gross / 1.21, 2), "vat": round(gross - gross / 1.21, 2), "gross": gross},
               "paid_amount": 0.0, "status": "unpaid", "efactura": {"status": "not_sent", "history": []},
               "created_at": datetime.now(timezone.utc).isoformat(), "tenant_id": tid, "branch_id": bid}
        iid = str(db.invoices.insert_one(doc).inserted_id)
        st["invoices"].append(iid)
        return iid

    st["make_invoice"] = make_invoice
    yield st
    cid = st["pf"]["id"]
    pay_ids = [str(p["_id"]) for p in db.payments.find({"client_id": cid}, {"_id": 1})]
    new_moves = [m["_id"] for m in db.cash_movements.find({}, {"_id": 1}) if m["_id"] not in movements_before]
    db.payments.delete_many({"client_id": cid})
    db.invoices.delete_many({"_id": {"$in": [ObjectId(i) for i in st["invoices"]]}})
    db.cash_movements.delete_many({"_id": {"$in": new_moves}})
    db.clients.delete_one({"_id": ObjectId(cid)})
    db.audit_logs.delete_many({"entity_id": {"$in": [cid] + pay_ids + [str(m) for m in new_moves] + st["invoices"]}})
    for c, v in counters.items():
        key = f"{tid}:{bid}:{c}"
        if v is None:
            db.counters.delete_one({"_id": key})
        else:
            db.counters.update_one({"_id": key}, {"$set": {"seq": v}})


def closing(s):
    r = s.get(f"{BASE}/cash-register", params={"day": TODAY})
    assert r.status_code == 200, r.text
    return r.json()["closing"]


def cash_pay(ctx, amount, invoice_id, doc="receipt"):
    reference = "45" if doc in {"fiscal_receipt", "collection_order"} else f"TEST_{TAG}"
    r = ctx["s"].post(f"{BASE}/payments", json={"client_id": ctx["pf"]["id"], "invoice_id": invoice_id, "amount": amount,
                                                 "method": "numerar", "cash_document": doc, "reference": reference})
    assert r.status_code == 200, r.text
    return r.json()


class TestPayouts:
    # Payout validation + effect on cash balance
    def test_payout_validation(self, ctx):
        s = ctx["s"]
        r = s.post(f"{BASE}/cash-register/payouts", json={"kind": "bogus", "beneficiary": "TEST_x", "amount": 1})
        assert r.status_code == 400
        r = s.post(f"{BASE}/cash-register/payouts", json={"kind": "expense_settlement", "beneficiary": "  ", "amount": 1})
        assert r.status_code == 400
        r = s.post(f"{BASE}/cash-register/payouts", json={"kind": "payment_order", "beneficiary": "TEST_x", "amount": 0})
        assert r.status_code == 400

    def test_payout_over_available_rejected(self, ctx):
        s = ctx["s"]
        avail = closing(s)
        r = s.post(f"{BASE}/cash-register/payouts", json={"kind": "expense_settlement", "beneficiary": "TEST_Ben",
                                                         "amount": round(avail + 1000, 2), "reference": f"TEST_{TAG}"})
        assert r.status_code == 400, r.text
        assert "depășește" in r.json().get("detail", "")

    def test_payouts_create_and_reduce_balance(self, ctx):
        s = ctx["s"]
        inv = ctx["make_invoice"](300.0, "P1")
        cash_pay(ctx, 300.0, inv)
        before = closing(s)
        r1 = s.post(f"{BASE}/cash-register/payouts", json={"kind": "expense_settlement", "beneficiary": "TEST_Decont",
                                                          "amount": 50, "reference": f"TEST_{TAG}"})
        assert r1.status_code == 200, r1.text
        assert r1.json()["doc_number"].startswith("DC-") and r1.json()["kind"] == "expense_settlement"
        r2 = s.post(f"{BASE}/cash-register/payouts", json={"kind": "payment_order", "beneficiary": "TEST_Disp",
                                                          "amount": 30, "document_number": "3", "reference": f"TEST_{TAG}"})
        assert r2.status_code == 200, r2.text
        assert r2.json()["doc_number"] == "DP-000003"
        after = closing(s)
        ctx["payouts_ok"] = True
        assert round(before - after, 2) == 80.0, f"daily cash register closing did not drop by payouts: before={before} after={after}"

    def test_cumulative_payouts_cannot_exceed_cash(self, ctx):
        s = ctx["s"]
        # report balance (all movements) shows real cash; daily register should match
        rep = s.get(f"{BASE}/cash-register/report", params={"date_from": "2000-01-01", "date_to": TODAY, "cash_only": True}).json()
        real = rep["closing"]
        r = s.post(f"{BASE}/cash-register/payouts", json={"kind": "payment_order", "beneficiary": "TEST_Over",
                                                         "amount": round(real + 10, 2), "document_number": "4", "reference": f"TEST_{TAG}"})
        if r.status_code == 200:
            ctx["db"].cash_movements.delete_one({"_id": ObjectId(r.json()["id"])})
        assert r.status_code == 400, f"payout {real + 10} accepted although real cash balance is {real}"


class TestReversal:
    # Storno chitanta / bon fiscal
    def test_reversal_flow(self, ctx):
        s, db = ctx["s"], ctx["db"]
        inv = ctx["make_invoice"](121.0, "R1")
        pay = cash_pay(ctx, 121.0, inv, "fiscal_receipt")
        assert pay["doc_type"] == "bon_fiscal"
        assert db.invoices.find_one({"_id": ObjectId(inv)})["status"] == "paid"
        assert s.post(f"{BASE}/payments/{pay['id']}/reverse", json={}).status_code == 422
        assert s.post(f"{BASE}/payments/{pay['id']}/reverse", json={"reason": "   "}).status_code == 400
        before = closing(s)
        r = s.post(f"{BASE}/payments/{pay['id']}/reverse", json={"reason": "TEST_ client renunta"})
        assert r.status_code == 200, r.text
        mv = r.json()
        assert mv["kind"] == "receipt_reversal" and mv["doc_number"].startswith("ST-")
        assert mv["amount"] == 121.0 and mv["reference"] == pay["doc_number"] and mv["reason"] == "TEST_ client renunta"
        i = db.invoices.find_one({"_id": ObjectId(inv)})
        assert i["paid_amount"] == 0 and i["status"] == "unpaid"
        assert db.payments.find_one({"_id": ObjectId(pay["id"])}).get("reversed_at")
        assert s.post(f"{BASE}/payments/{pay['id']}/reverse", json={"reason": "again"}).status_code == 400
        rep = s.get(f"{BASE}/cash-register/report", params={"date_from": TODAY, "date_to": TODAY, "cash_only": True}).json()
        st_row = [x for x in rep["items"] if x["document"] == mv["doc_number"]]
        assert st_row and st_row[0]["out"] == 121.0
        ctx["reversal_ok"] = True
        after = closing(s)
        assert round(before - after, 2) == 121.0, f"daily register closing ignores reversal: before={before} after={after}"

    def test_reversal_partial_chitanta(self, ctx):
        s, db = ctx["s"], ctx["db"]
        inv = ctx["make_invoice"](200.0, "R2")
        p1 = cash_pay(ctx, 80.0, inv)
        cash_pay(ctx, 50.0, inv)
        r = s.post(f"{BASE}/payments/{p1['id']}/reverse", json={"reason": "TEST_ gresit"})
        assert r.status_code == 200, r.text
        i = db.invoices.find_one({"_id": ObjectId(inv)})
        assert i["paid_amount"] == 50.0 and i["status"] == "partial"

    def test_pos_not_reversible(self, ctx):
        s = ctx["s"]
        inv = ctx["make_invoice"](40.0, "R3")
        r = s.post(f"{BASE}/payments", json={"client_id": ctx["pf"]["id"], "invoice_id": inv, "amount": 40, "method": "pos"})
        assert r.status_code == 200, r.text
        ctx["pos_doc"] = r.json()["doc_number"]
        rr = s.post(f"{BASE}/payments/{r.json()['id']}/reverse", json={"reason": "TEST_x"})
        assert rr.status_code == 400


class TestRegisters:
    # Range registers cash_only true/false, running balance, PDF
    def test_report_cash_only_vs_all(self, ctx):
        s = ctx["s"]
        rt = s.get(f"{BASE}/cash-register/report", params={"date_from": TODAY, "date_to": TODAY, "cash_only": True})
        rf = s.get(f"{BASE}/cash-register/report", params={"date_from": TODAY, "date_to": TODAY, "cash_only": False})
        assert rt.status_code == 200 and rf.status_code == 200
        t, f = rt.json(), rf.json()
        docs_t = {x["document"] for x in t["items"]}
        docs_f = {x["document"] for x in f["items"]}
        assert ctx.get("pos_doc") and ctx["pos_doc"] in docs_f and ctx["pos_doc"] not in docs_t
        assert docs_t <= docs_f
        for rep in (t, f):
            bal = rep["opening"]
            for row in rep["items"]:
                bal = round(bal + row["in"] - row["out"], 2)
                assert row["balance"] == bal
            assert rep["closing"] == bal

    def test_report_missing_params(self, ctx):
        assert ctx["s"].get(f"{BASE}/cash-register/report").status_code == 422

    def test_report_opening_carries_previous_balance(self, ctx):
        s = ctx["s"]
        full = s.get(f"{BASE}/cash-register/report", params={"date_from": "2000-01-01", "date_to": TODAY, "cash_only": True}).json()
        tomorrow = (date.fromisoformat(TODAY) + timedelta(days=1)).isoformat()
        nxt = s.get(f"{BASE}/cash-register/report", params={"date_from": tomorrow, "date_to": tomorrow, "cash_only": True}).json()
        assert nxt["opening"] == full["closing"], f"opening of next interval {nxt['opening']} != previous closing {full['closing']}"

    @pytest.mark.parametrize("cash_only", ["true", "false"])
    def test_pdf(self, ctx, cash_only):
        r = ctx["s"].get(f"{BASE}/cash-register/report.pdf", params={"date_from": TODAY, "date_to": TODAY, "cash_only": cash_only})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF" and len(r.content) > 800
