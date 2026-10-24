# Iter33: operator-entered document numbers (BF/DI/DP), per-type + per-issue-day uniqueness,
# fiscal receipt issue date (default today, no future), daily cash limit computed on closing date.
# All TEST_ data (client, invoices, payments, cash_movements, audit_logs) removed in teardown, counters restored.
import os
import secrets
from datetime import datetime, timezone, timedelta

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
TAG = secrets.token_hex(3).upper()
TODAY = datetime.now(timezone.utc).date()
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()
TWO_DAYS = (TODAY - timedelta(days=2)).isoformat()
TOMORROW = (TODAY + timedelta(days=1)).isoformat()
COUNTERS = ["pay_chitanta", "pay_bon_pos", "cash_expense_settlement", "cash_payment_order"]
NUM = str(700_000 + int(TAG, 16) % 200_000)  # unique-ish operator number


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
    moves_before = {m["_id"] for m in db.cash_movements.find({}, {"_id": 1})}
    st = {"s": s, "db": db, "invoices": [], "clients": []}

    def make_client(kind, name):
        r = s.post(f"{BASE}/clients", json={"type": kind, "name": f"TEST_{name} {TAG}", "phone": "0700000033",
                                             **({"cui": "RO123"} if kind == "pj" else {})})
        assert r.status_code == 200, r.text
        st["clients"].append(r.json()["id"])
        return r.json()

    def make_invoice(client_id, gross, num):
        doc = {"type": "fiscal", "series": "TSTN", "number": f"{TAG}{num}", "issue_date": "2026-01-01", "due_date": "2026-01-02",
               "client_id": client_id, "buyer": {"name": "TEST"}, "lines": [],
               "totals": {"net": round(gross / 1.21, 2), "vat": round(gross - gross / 1.21, 2), "gross": gross},
               "paid_amount": 0.0, "status": "unpaid", "efactura": {"status": "not_sent", "history": []},
               "created_at": datetime.now(timezone.utc).isoformat(), "tenant_id": tid, "branch_id": bid}
        iid = str(db.invoices.insert_one(doc).inserted_id)
        st["invoices"].append(iid)
        return iid

    st["make_client"], st["make_invoice"] = make_client, make_invoice
    st["pf"] = make_client("pf", "PF Num")
    yield st
    pay_ids = [str(p["_id"]) for p in db.payments.find({"client_id": {"$in": st["clients"]}}, {"_id": 1})]
    new_moves = [m["_id"] for m in db.cash_movements.find({}, {"_id": 1}) if m["_id"] not in moves_before]
    db.payments.delete_many({"client_id": {"$in": st["clients"]}})
    db.invoices.delete_many({"_id": {"$in": [ObjectId(i) for i in st["invoices"]]}})
    db.cash_movements.delete_many({"_id": {"$in": new_moves}})
    db.clients.delete_many({"_id": {"$in": [ObjectId(c) for c in st["clients"]]}})
    db.audit_logs.delete_many({"entity_id": {"$in": st["clients"] + pay_ids + [str(m) for m in new_moves] + st["invoices"]}})
    for c, v in counters.items():
        key = f"{tid}:{bid}:{c}"
        if v is None:
            db.counters.delete_one({"_id": key})
        else:
            db.counters.update_one({"_id": key}, {"$set": {"seq": v}})


def pay(ctx, amount, doc, reference, issue_date=None, client=None):
    client = client or ctx["pf"]
    inv = ctx["make_invoice"](client["id"], amount, secrets.token_hex(2))
    body = {"client_id": client["id"], "invoice_id": inv, "amount": amount, "method": "numerar",
            "cash_document": doc, "reference": reference}
    if issue_date is not None:
        body["document_issue_date"] = issue_date
    return ctx["s"].post(f"{BASE}/payments", json=body)


# --- Fiscal receipt date ---
class TestFiscalReceiptDate:
    def test_default_issue_date_is_today(self, ctx):
        r = pay(ctx, 10, "fiscal_receipt", str(int(NUM) + 1))
        assert r.status_code == 200, r.text
        assert r.json()["document_issue_date"] == TODAY.isoformat()
        assert r.json()["doc_number"] == f"BF-{int(NUM) + 1:06d}"

    def test_future_date_rejected(self, ctx):
        r = pay(ctx, 10, "fiscal_receipt", str(int(NUM) + 2), TOMORROW)
        assert r.status_code == 400 and "viitor" in r.json()["detail"]

    def test_invalid_date_rejected(self, ctx):
        r = pay(ctx, 10, "fiscal_receipt", str(int(NUM) + 3), "24/10/2026")
        assert r.status_code == 400

    def test_bf_45_format(self, ctx):
        r = pay(ctx, 10, "fiscal_receipt", "45", TWO_DAYS)
        assert r.status_code == 200, r.text
        assert r.json()["doc_number"] == "BF-000045" and r.json()["document_issue_date"] == TWO_DAYS
        # same number + same issue date rejected
        d = pay(ctx, 10, "fiscal_receipt", "45", TWO_DAYS)
        assert d.status_code == 400, d.text
        # same number, different date allowed
        ok = pay(ctx, 10, "fiscal_receipt", "45", YESTERDAY)
        assert ok.status_code == 200, ok.text
        assert ok.json()["doc_number"] == "BF-000045"

    def test_non_numeric_reference_rejected(self, ctx):
        for ref in ["", "abc", "BF-45", " "]:
            r = pay(ctx, 10, "fiscal_receipt", ref)
            assert r.status_code == 400, (ref, r.text)

    def test_bf_only_for_pf(self, ctx):
        pj = ctx["make_client"]("pj", "PJ Num")
        r = pay(ctx, 10, "fiscal_receipt", "77", client=pj)
        assert r.status_code == 400

    def test_list_returns_issue_date(self, ctx):
        r = ctx["s"].get(f"{BASE}/payments", params={"method": "numerar", "q": "BF-000045", "page": 1, "page_size": 50})
        assert r.status_code == 200
        mine = [p for p in r.json()["items"] if p["client_id"] == ctx["pf"]["id"]]
        assert {p["document_issue_date"] for p in mine} == {TWO_DAYS, YESTERDAY}
        # closing (created) date is today though
        assert all(p["date"].startswith(TODAY.isoformat()) for p in mine)


# --- Cash limit uses closing date, not receipt date ---
class TestCashLimitClosingDate:
    def test_historical_bf_counts_today(self, ctx):
        pf2 = ctx["make_client"]("pf", "PF Limit")
        a = pay(ctx, 9000, "fiscal_receipt", str(int(NUM) + 10), TWO_DAYS, client=pf2)
        assert a.status_code == 200, a.text
        b = pay(ctx, 1500, "receipt", f"TEST_{TAG}", client=pf2)
        assert b.status_code == 400 and "Limita" in b.json()["detail"], b.text
        c = pay(ctx, 1500, "fiscal_receipt", str(int(NUM) + 11), YESTERDAY, client=pf2)
        assert c.status_code == 400 and "Limita" in c.json()["detail"], c.text
        ok = pay(ctx, 1000, "fiscal_receipt", str(int(NUM) + 12), YESTERDAY, client=pf2)
        assert ok.status_code == 200, ok.text


# --- DI numbering ---
class TestCollectionOrder:
    def test_di_3_format(self, ctx):
        r = pay(ctx, 10, "collection_order", "3")
        assert r.status_code == 200, r.text
        assert r.json()["doc_number"] == "DI-000003"
        ctx["di3"] = True

    def test_di_duplicate_same_day_rejected(self, ctx):
        r = pay(ctx, 10, "collection_order", "3")
        assert r.status_code == 400, f"duplicate DI-000003 same day accepted: {r.text}"

    def test_di_and_bf_same_number_independent(self, ctx):
        r = pay(ctx, 10, "fiscal_receipt", "3")
        assert r.status_code == 200, r.text
        assert r.json()["doc_number"] == "BF-000003"


# --- DP numbering ---
class TestPaymentOrder:
    def test_dp_3_and_duplicate(self, ctx):
        s = ctx["s"]
        pay(ctx, 200, "receipt", f"TEST_{TAG}")  # ensure cash available
        r = s.post(f"{BASE}/cash-register/payouts", json={"kind": "payment_order", "beneficiary": f"TEST_DP {TAG}",
                                                         "amount": 5, "document_number": "3"})
        assert r.status_code == 200, r.text
        assert r.json()["doc_number"] == "DP-000003"
        d = s.post(f"{BASE}/cash-register/payouts", json={"kind": "payment_order", "beneficiary": f"TEST_DP {TAG}",
                                                         "amount": 5, "document_number": "3"})
        assert d.status_code == 400, d.text
        z = s.post(f"{BASE}/cash-register/payouts", json={"kind": "payment_order", "beneficiary": f"TEST_DP {TAG}",
                                                         "amount": 5, "document_number": "003"})
        assert z.status_code == 400, f"003 should normalize to DP-000003 and be rejected: {z.text}"
        bad = s.post(f"{BASE}/cash-register/payouts", json={"kind": "payment_order", "beneficiary": f"TEST_DP {TAG}",
                                                           "amount": 5, "document_number": "x"})
        assert bad.status_code == 400

    def test_decont_unaffected_by_dp_number(self, ctx):
        r = ctx["s"].post(f"{BASE}/cash-register/payouts", json={"kind": "expense_settlement", "beneficiary": f"TEST_DC {TAG}",
                                                                 "amount": 1, "document_number": "3"})
        assert r.status_code == 200, r.text
        assert r.json()["doc_number"].startswith("DC-")
