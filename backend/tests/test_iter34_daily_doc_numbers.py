# Iter34: BF/DI/DP/DC operator numbers -> 6-digit format, per tenant/branch/type/day uniqueness,
# leading-zero variants rejected, DC+DP coexist, DC number required, Mongo daily unique indexes.
# All TEST_ data removed in teardown, counters restored.
import os
import secrets
from datetime import datetime, timezone, timedelta

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
TAG = secrets.token_hex(3).upper()
TODAY = datetime.now(timezone.utc).date()
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()
COUNTERS = ["pay_chitanta", "pay_bon_pos", "cash_expense_settlement", "cash_payment_order"]
N = 800_000 + int(TAG, 16) % 150_000


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
    st = {"s": s, "db": db, "tid": tid, "bid": bid, "invoices": [], "clients": [], "raw_ids": []}

    def make_invoice(client_id, gross):
        doc = {"type": "fiscal", "series": "TSTQ", "number": f"{TAG}{secrets.token_hex(2)}", "issue_date": "2026-01-01",
               "due_date": "2026-01-02", "client_id": client_id, "buyer": {"name": "TEST"}, "lines": [],
               "totals": {"net": round(gross / 1.21, 2), "vat": round(gross - gross / 1.21, 2), "gross": gross},
               "paid_amount": 0.0, "status": "unpaid", "efactura": {"status": "not_sent", "history": []},
               "created_at": datetime.now(timezone.utc).isoformat(), "tenant_id": tid, "branch_id": bid}
        iid = str(db.invoices.insert_one(doc).inserted_id)
        st["invoices"].append(iid)
        return iid

    r = s.post(f"{BASE}/clients", json={"type": "pf", "name": f"TEST_PF34 {TAG}", "phone": "0700000034"})
    assert r.status_code == 200, r.text
    st["pf"] = r.json()
    st["clients"].append(st["pf"]["id"])
    st["make_invoice"] = make_invoice
    yield st
    pay_ids = [str(p["_id"]) for p in db.payments.find({"client_id": {"$in": st["clients"]}}, {"_id": 1})]
    new_moves = [m["_id"] for m in db.cash_movements.find({}, {"_id": 1}) if m["_id"] not in moves_before]
    db.payments.delete_many({"client_id": {"$in": st["clients"]}})
    db.payments.delete_many({"_id": {"$in": st["raw_ids"]}})
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


def pay(ctx, doc, ref, issue_date=None, amount=5):
    inv = ctx["make_invoice"](ctx["pf"]["id"], amount)
    body = {"client_id": ctx["pf"]["id"], "invoice_id": inv, "amount": amount, "method": "numerar",
            "cash_document": doc, "reference": ref}
    if issue_date:
        body["document_issue_date"] = issue_date
    return ctx["s"].post(f"{BASE}/payments", json=body)


def payout(ctx, kind, num, amount=1):
    return ctx["s"].post(f"{BASE}/cash-register/payouts", json={"kind": kind, "beneficiary": f"TEST_B34 {TAG}",
                                                                "amount": amount, "document_number": num})


class TestFormatAndDuplicates:
    def test_fund_cash(self, ctx):
        r = pay(ctx, "receipt", f"TEST_{TAG}", amount=100)
        assert r.status_code == 200, r.text

    @pytest.mark.parametrize("doc,prefix", [("fiscal_receipt", "BF"), ("collection_order", "DI")])
    def test_payment_docs_six_digits_and_zero_variants(self, ctx, doc, prefix):
        num = N + (1 if prefix == "BF" else 2)
        r = pay(ctx, doc, str(num % 1000 + 45))
        assert r.status_code == 200, r.text
        assert r.json()["doc_number"] == f"{prefix}-{num % 1000 + 45:06d}"
        assert r.json()["document_issue_date"] == TODAY.isoformat()
        for variant in [str(num % 1000 + 45), f"0{num % 1000 + 45}", f"{num % 1000 + 45:06d}", f"{num % 1000 + 45:09d}"]:
            d = pay(ctx, doc, variant)
            assert d.status_code == 400, (variant, d.text)
            assert "deja" in d.json()["detail"]

    @pytest.mark.parametrize("kind,prefix", [("expense_settlement", "DC"), ("payment_order", "DP")])
    def test_payout_docs_six_digits_and_zero_variants(self, ctx, kind, prefix):
        num = N % 1000 + 60
        r = payout(ctx, kind, str(num))
        assert r.status_code == 200, r.text
        assert r.json()["doc_number"] == f"{prefix}-{num:06d}"
        assert r.json()["document_issue_date"] == TODAY.isoformat()
        for variant in [str(num), f"00{num}", f"{num:06d}"]:
            d = payout(ctx, kind, variant)
            assert d.status_code == 400, (variant, d.text)

    def test_bf_same_number_other_day_allowed(self, ctx):
        num = str(N % 1000 + 45)
        r = pay(ctx, "fiscal_receipt", num, YESTERDAY)
        assert r.status_code == 200, r.text
        assert r.json()["document_issue_date"] == YESTERDAY
        assert pay(ctx, "fiscal_receipt", "0" + num, YESTERDAY).status_code == 400

    def test_di_ignores_issue_date_param(self, ctx):
        # DI date is not selectable: should stay today even if client sends a date
        r = pay(ctx, "collection_order", str(N % 1000 + 300), YESTERDAY)
        assert r.status_code == 200, r.text
        assert r.json()["document_issue_date"] == TODAY.isoformat()


class TestDcDpCoexist:
    def test_dc3_dp3_same_day(self, ctx):
        db = ctx["db"]
        existing = db.cash_movements.count_documents({"tenant_id": ctx["tid"], "branch_id": ctx["bid"],
                                                       "doc_number": {"$in": ["DC-000003", "DP-000003"]},
                                                       "document_issue_date": TODAY.isoformat()})
        if existing:
            pytest.skip("real DC/DP-000003 exists today")
        dc = payout(ctx, "expense_settlement", "3")
        dp = payout(ctx, "payment_order", "3")
        assert dc.status_code == 200 and dc.json()["doc_number"] == "DC-000003", dc.text
        assert dp.status_code == 200 and dp.json()["doc_number"] == "DP-000003", dp.text
        assert payout(ctx, "expense_settlement", "003").status_code == 400
        assert payout(ctx, "payment_order", "0003").status_code == 400
        lst = ctx["s"].get(f"{BASE}/cash-movements", params={"q": f"TEST_B34 {TAG}", "page": 1, "page_size": 100}).json()
        nums = [m["doc_number"] for m in lst["items"]]
        assert nums.count("DC-000003") == 1 and nums.count("DP-000003") == 1


class TestDcRequired:
    @pytest.mark.parametrize("num", ["", " ", "abc", "-3", "3.0", "DC-3"])
    def test_dc_number_required_numeric(self, ctx, num):
        r = payout(ctx, "expense_settlement", num)
        assert r.status_code == 400, (num, r.text)

    def test_dc_missing_field(self, ctx):
        r = ctx["s"].post(f"{BASE}/cash-register/payouts", json={"kind": "expense_settlement", "beneficiary": f"TEST_B34 {TAG}", "amount": 1})
        assert r.status_code == 400, r.text

    @pytest.mark.parametrize("num", ["\u00b3", "\u00b2\u00b3"])
    def test_unicode_superscript_digits_not_500(self, ctx, num):
        r = payout(ctx, "expense_settlement", num)
        assert r.status_code == 400, f"{num!r} -> {r.status_code} {r.text[:120]}"

    def test_unicode_superscript_payment_not_500(self, ctx):
        r = pay(ctx, "collection_order", "\u00b3")
        assert r.status_code == 400, f"-> {r.status_code} {r.text[:120]}"


class TestIndexes:
    def test_indexes_defined(self, ctx):
        db = ctx["db"]
        pi = db.payments.index_information()["daily_cash_document_number"]
        ci = db.cash_movements.index_information()["daily_payment_order_number"]
        assert pi["unique"] and ci["unique"]
        assert [k for k, _ in pi["key"]] == ["tenant_id", "branch_id", "doc_type", "doc_number", "document_issue_date"]
        assert [k for k, _ in ci["key"]] == ["tenant_id", "branch_id", "kind", "doc_number", "document_issue_date"]
        assert pi["partialFilterExpression"] == {"document_issue_date": {"$gt": ""}}
        assert ci["partialFilterExpression"] == {"document_issue_date": {"$gt": ""}}

    def test_index_enforced_and_tenant_scoped(self, ctx):
        db = ctx["db"]
        base = {"doc_type": "dispozitie_incasare", "doc_number": f"DI-{TAG}", "document_issue_date": TODAY.isoformat(),
                "client_id": "TEST_raw", "method": "numerar", "amount": 0, "date": "1999-01-01"}
        ctx["raw_ids"].append(db.payments.insert_one({**base, "tenant_id": ctx["tid"], "branch_id": ctx["bid"]}).inserted_id)
        with pytest.raises(DuplicateKeyError):
            db.payments.insert_one({**base, "tenant_id": ctx["tid"], "branch_id": ctx["bid"]})
        # other branch / other tenant allowed
        ctx["raw_ids"].append(db.payments.insert_one({**base, "tenant_id": ctx["tid"], "branch_id": "TEST_other"}).inserted_id)
        ctx["raw_ids"].append(db.payments.insert_one({**base, "tenant_id": "TEST_other", "branch_id": ctx["bid"]}).inserted_id)
        # empty issue date excluded from index
        ctx["raw_ids"].append(db.payments.insert_one({**base, "doc_number": f"CH-{TAG}", "document_issue_date": "", "tenant_id": ctx["tid"], "branch_id": ctx["bid"]}).inserted_id)
        ctx["raw_ids"].append(db.payments.insert_one({**base, "doc_number": f"CH-{TAG}", "document_issue_date": "", "tenant_id": ctx["tid"], "branch_id": ctx["bid"]}).inserted_id)
