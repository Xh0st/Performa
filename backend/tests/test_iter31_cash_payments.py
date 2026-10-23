# Iter31: Cash receipts (chitanta/bon fiscal), FIFO allocation, POS/OP, cash register + bank deposits, payment filters, client regressions.
# All fixtures are TEST_ prefixed and fully removed (clients, invoices, payments, cash_movements, audit_logs, counters restored).
import os
import secrets
from datetime import datetime, timezone

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
TAG = secrets.token_hex(3).upper()
COUNTERS = ["pay_chitanta", "pay_bon_fiscal", "pay_bon_pos", "pay_ordin_plata", "pay_confirmare_online", "cash_deposit"]


def _creds(key):
    txt = open("/app/memory/test_credentials.md").read()
    line = [ln for ln in txt.splitlines() if key in ln][0]
    em, pw = [x.strip() for x in line.lstrip("- ").split("/")[:2]]
    return em, pw.split()[0]


def _mdb():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _iso():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture(scope="module")
def ctx():
    s = requests.Session()
    em, pw = _creds("andrei.melek")
    r = s.post(f"{BASE}/auth/login", json={"email": em, "password": pw})
    assert r.status_code == 200, r.text
    user = r.json()["user"]
    db = _mdb()
    tid, bid = user["tenant_id"], user["active_branch_id"]
    counters = {c: (db.counters.find_one({"_id": f"{tid}:{bid}:{c}"}) or {}).get("seq") for c in COUNTERS}
    st = {"s": s, "db": db, "tid": tid, "bid": bid, "clients": [], "invoices": [], "deposits": []}
    pf = s.post(f"{BASE}/clients", json={"type": "pf", "name": f"TEST_PF Cash {TAG}", "phone": "0700000001"})
    pj = s.post(f"{BASE}/clients", json={"type": "pj", "name": f"TEST_PJ Cash {TAG}", "cui": "RO123" + TAG[:3].encode().hex()[:4]})
    assert pf.status_code == 200, pf.text
    assert pj.status_code == 200, pj.text
    st["pf"], st["pj"] = pf.json(), pj.json()
    st["clients"] += [st["pf"]["id"], st["pj"]["id"]]

    def make_invoice(client_id, gross, due, num, inv_type="fiscal", kind=None):
        doc = {"type": inv_type, "series": "TSTC", "number": f"{TAG}{num}", "issue_date": "2026-01-01", "due_date": due,
               "client_id": client_id, "buyer": {"name": "TEST"}, "lines": [],
               "totals": {"net": round(gross / 1.21, 2), "vat": round(gross - gross / 1.21, 2), "gross": gross},
               "paid_amount": 0.0, "status": "unpaid", "efactura": {"status": "not_sent", "history": []},
               "created_at": _iso(), "tenant_id": tid, "branch_id": bid}
        if kind:
            doc["kind"] = kind
        iid = str(db.invoices.insert_one(doc).inserted_id)
        st["invoices"].append(iid)
        return iid

    st["make_invoice"] = make_invoice
    yield st
    # teardown
    cids = st["clients"]
    pays = list(db.payments.find({"client_id": {"$in": cids}}, {"_id": 1}))
    pay_ids = [str(p["_id"]) for p in pays]
    db.payments.delete_many({"client_id": {"$in": cids}})
    db.payments.delete_many({"invoice_id": {"$in": st["invoices"]}})
    db.invoices.delete_many({"_id": {"$in": [ObjectId(i) for i in st["invoices"]]}})
    db.cash_movements.delete_many({"_id": {"$in": [ObjectId(i) for i in st["deposits"]]}})
    db.clients.delete_many({"_id": {"$in": [ObjectId(i) for i in cids]}})
    db.audit_logs.delete_many({"entity_id": {"$in": cids + pay_ids + st["deposits"] + st["invoices"]}})
    for c, v in counters.items():
        key = f"{tid}:{bid}:{c}"
        if v is None:
            db.counters.delete_one({"_id": key})
        else:
            db.counters.update_one({"_id": key}, {"$set": {"seq": v}})


def _inv(ctx, iid):
    return ctx["db"].invoices.find_one({"_id": ObjectId(iid)})


# --- Client regressions
class TestClientRegression:
    def test_pj_default_credit_limit_zero(self, ctx):
        r = ctx["s"].get(f"{BASE}/clients/{ctx['pj']['id']}")
        assert r.status_code == 200
        assert r.json().get("credit_limit") == 0

    def test_pf_rejects_terms_credit(self, ctx):
        r = ctx["s"].post(f"{BASE}/clients", json={"type": "pf", "name": f"TEST_PF bad {TAG}", "payment_terms_days": 30, "credit_limit": 1000})
        if r.status_code == 200:
            ctx["clients"].append(r.json()["id"])
        assert r.status_code == 400


# --- Cash receipts on selected invoice
class TestCashReceipts:
    def test_chitanta_on_selected_invoice(self, ctx):
        iid = ctx["make_invoice"](ctx["pj"]["id"], 500.0, "2026-02-01", "01")
        r = ctx["s"].post(f"{BASE}/payments", json={"client_id": ctx["pj"]["id"], "invoice_id": iid, "amount": 200, "method": "numerar"})
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["doc_type"] == "chitanta" and p["doc_number"].startswith("CH-")
        assert p["allocations"] == [{"invoice_id": iid, "invoice_ref": f"TSTC{TAG}01", "amount": 200.0}]
        inv = _inv(ctx, iid)
        assert inv["paid_amount"] == 200.0 and inv["status"] == "partial"
        g = ctx["s"].get(f"{BASE}/payments/{p['id']}")
        assert g.status_code == 200 and g.json()["allocations"][0]["amount"] == 200.0

    def test_bon_fiscal_for_pf(self, ctx):
        iid = ctx["make_invoice"](ctx["pf"]["id"], 121.0, "2026-02-01", "02")
        r = ctx["s"].post(f"{BASE}/payments", json={"client_id": ctx["pf"]["id"], "invoice_id": iid, "amount": 121, "method": "numerar", "cash_document": "fiscal_receipt"})
        assert r.status_code == 200, r.text
        assert r.json()["doc_type"] == "bon_fiscal" and r.json()["doc_number"].startswith("BF-")
        assert _inv(ctx, iid)["status"] == "paid"

    def test_bon_fiscal_rejected_for_pj(self, ctx):
        iid = ctx["make_invoice"](ctx["pj"]["id"], 100.0, "2026-02-01", "03")
        r = ctx["s"].post(f"{BASE}/payments", json={"client_id": ctx["pj"]["id"], "invoice_id": iid, "amount": 10, "method": "numerar", "cash_document": "fiscal_receipt"})
        assert r.status_code == 400, f"PJ got bon fiscal server-side: {r.status_code} {r.text[:200]}"

    def test_invoice_of_other_client_rejected(self, ctx):
        iid = ctx["make_invoice"](ctx["pf"]["id"], 50.0, "2026-02-01", "04")
        r = ctx["s"].post(f"{BASE}/payments", json={"client_id": ctx["pj"]["id"], "invoice_id": iid, "amount": 10, "method": "numerar"})
        assert r.status_code == 400
        assert _inv(ctx, iid)["paid_amount"] == 0

    def test_proforma_rejected(self, ctx):
        iid = ctx["make_invoice"](ctx["pf"]["id"], 50.0, "2026-02-01", "05", inv_type="proforma")
        r = ctx["s"].post(f"{BASE}/payments", json={"invoice_id": iid, "amount": 10, "method": "numerar"})
        assert r.status_code == 400

    def test_invalid_cash_document_does_not_mutate(self, ctx):
        iid = ctx["make_invoice"](ctx["pf"]["id"], 80.0, "2026-02-01", "06")
        r = ctx["s"].post(f"{BASE}/payments", json={"invoice_id": iid, "amount": 10, "method": "numerar", "cash_document": "xxx"})
        assert r.status_code == 400
        inv = _inv(ctx, iid)
        assert inv["paid_amount"] == 0, f"Invoice mutated despite 400: paid_amount={inv['paid_amount']}"

    def test_over_amount_selected_invoice_does_not_mutate(self, ctx):
        iid = ctx["make_invoice"](ctx["pf"]["id"], 70.0, "2026-02-01", "07")
        r = ctx["s"].post(f"{BASE}/payments", json={"invoice_id": iid, "amount": 100, "method": "numerar"})
        assert r.status_code == 400
        inv = _inv(ctx, iid)
        assert inv["paid_amount"] == 0, f"Invoice mutated despite 400: paid_amount={inv['paid_amount']} status={inv['status']}"
        # reset for next tests in case of bug
        ctx["db"].invoices.update_one({"_id": ObjectId(iid)}, {"$set": {"paid_amount": 0.0, "status": "unpaid"}})

    def test_invalid_method_and_zero_amount(self, ctx):
        r1 = ctx["s"].post(f"{BASE}/payments", json={"client_id": ctx["pf"]["id"], "amount": 10, "method": "crypto"})
        r2 = ctx["s"].post(f"{BASE}/payments", json={"client_id": ctx["pf"]["id"], "amount": 0, "method": "numerar"})
        r3 = ctx["s"].post(f"{BASE}/payments", json={"amount": 10, "method": "numerar"})
        assert (r1.status_code, r2.status_code, r3.status_code) == (400, 400, 400)


# --- FIFO allocation (dedicated client to control order)
class TestFifo:
    def test_fifo_by_due_date_and_overflow(self, ctx):
        c = ctx["s"].post(f"{BASE}/clients", json={"type": "pf", "name": f"TEST_PF FIFO {TAG}"}).json()
        ctx["clients"].append(c["id"])
        ctx["fifo_client"] = c["id"]
        late = ctx["make_invoice"](c["id"], 300.0, "2026-03-01", "F3")
        early = ctx["make_invoice"](c["id"], 100.0, "2026-01-10", "F1")
        mid = ctx["make_invoice"](c["id"], 200.0, "2026-02-01", "F2")
        ctx["make_invoice"](c["id"], 999.0, "2026-01-01", "FP", inv_type="proforma")
        ctx["make_invoice"](c["id"], 50.0, "2026-01-01", "FC", kind="credit_note")
        r = ctx["s"].post(f"{BASE}/payments", json={"client_id": c["id"], "amount": 250, "method": "numerar"})
        assert r.status_code == 200, r.text
        al = r.json()["allocations"]
        assert [(a["invoice_id"], a["amount"]) for a in al] == [(early, 100.0), (mid, 150.0)]
        assert r.json()["invoice_ref"] == f"TSTC{TAG}F1, TSTC{TAG}F2"
        assert _inv(ctx, early)["status"] == "paid" and _inv(ctx, mid)["paid_amount"] == 150.0 and _inv(ctx, mid)["status"] == "partial"
        assert _inv(ctx, late)["paid_amount"] == 0
        ctx["fifo"] = (early, mid, late)

    def test_fifo_overflow_rejected_without_mutation(self, ctx):
        early, mid, late = ctx["fifo"]
        # remaining due = 50 + 300 = 350
        r = ctx["s"].post(f"{BASE}/payments", json={"client_id": ctx["fifo_client"], "amount": 351, "method": "pos"})
        assert r.status_code == 400
        assert "depășește" in r.json().get("detail", "")
        m, l_ = _inv(ctx, mid), _inv(ctx, late)
        mutated = (m["paid_amount"], l_["paid_amount"])
        # restore if mutated so later tests are deterministic
        ctx["db"].invoices.update_one({"_id": ObjectId(mid)}, {"$set": {"paid_amount": 150.0, "status": "partial"}})
        ctx["db"].invoices.update_one({"_id": ObjectId(late)}, {"$set": {"paid_amount": 0.0, "status": "unpaid"}})
        assert mutated == (150.0, 0.0), f"Overflow 400 left invoices mutated: mid/late paid={mutated}"

    def test_pos_fifo_and_op_exact_balance(self, ctx):
        early, mid, late = ctx["fifo"]
        r = ctx["s"].post(f"{BASE}/payments", json={"client_id": ctx["fifo_client"], "amount": 100, "method": "pos", "reference": "TEST_POS"})
        assert r.status_code == 200, r.text
        assert r.json()["doc_type"] == "bon_pos" and r.json()["doc_number"].startswith("POS-")
        assert [(a["invoice_id"], a["amount"]) for a in r.json()["allocations"]] == [(mid, 50.0), (late, 50.0)]
        r2 = ctx["s"].post(f"{BASE}/payments", json={"client_id": ctx["fifo_client"], "invoice_id": late, "amount": 250, "method": "transfer"})
        assert r2.status_code == 200, r2.text
        assert r2.json()["doc_type"] == "ordin_plata" and r2.json()["doc_number"].startswith("OP-")
        assert all(_inv(ctx, i)["status"] == "paid" for i in (early, mid, late))
        r3 = ctx["s"].post(f"{BASE}/payments", json={"client_id": ctx["fifo_client"], "amount": 1, "method": "pos"})
        assert r3.status_code == 400

    def test_account_statement_fifo_once(self, ctx):
        r = ctx["s"].get(f"{BASE}/clients/{ctx['fifo_client']}/account-statement?page=1&page_size=100")
        assert r.status_code == 200, r.text
        d = r.json()
        pays = [m for m in d["items"] if m["kind"] == "payment"]
        assert len(pays) == 3, [m["reference"] for m in pays]
        assert len({m["entity_id"] for m in pays}) == 3
        assert round(sum(m["credit"] for m in pays), 2) == 600.0


# --- Payment list filters / pagination
class TestPaymentLists:
    def test_numerar_filter(self, ctx):
        r = ctx["s"].get(f"{BASE}/payments?method=numerar&page=1&page_size=20")
        assert r.status_code == 200
        d = r.json()
        assert len(d["items"]) <= 20 and d["page_size"] == 20
        assert all(p["method"] == "numerar" for p in d["items"])
        assert d["total"] == ctx["db"].payments.count_documents({"tenant_id": ctx["tid"], "branch_id": ctx["bid"], "method": "numerar"})

    def test_cashless_filter(self, ctx):
        r = ctx["s"].get(f"{BASE}/payments?method=pos,transfer&page=1&page_size=20")
        assert r.status_code == 200
        d = r.json()
        assert all(p["method"] in ("pos", "transfer") for p in d["items"])
        assert d["total"] == ctx["db"].payments.count_documents({"tenant_id": ctx["tid"], "branch_id": ctx["bid"], "method": {"$in": ["pos", "transfer"]}})
        assert any(p["client_id"] == ctx["fifo_client"] for p in d["items"])


# --- Cash register and bank deposits
class TestCashRegister:
    def test_register_only_cash_and_math(self, ctx):
        r = ctx["s"].get(f"{BASE}/cash-register")
        assert r.status_code == 200
        d = r.json()
        assert all(e["direction"] == "out" or e.get("method") == "numerar" for e in d["entries"])
        assert all(e.get("method") not in ("pos", "transfer") for e in d["entries"])
        assert d["closing"] == round(d["opening"] + d["total_in"] - d["total_out"], 2)
        ctx["reg_before"] = d

    def test_partial_deposit_and_total_and_overflow(self, ctx):
        before = ctx["s"].get(f"{BASE}/cash-register").json()
        avail = before["closing"]
        over = ctx["s"].post(f"{BASE}/cash-register/deposits", json={"amount": round(avail + 1, 2), "reference": "TEST_over"})
        assert over.status_code == 400
        zero = ctx["s"].post(f"{BASE}/cash-register/deposits", json={"amount": 0})
        assert zero.status_code == 400
        part = ctx["s"].post(f"{BASE}/cash-register/deposits", json={"amount": 10, "reference": "TEST_DEP"})
        assert part.status_code == 200, part.text
        ctx["deposits"].append(part.json()["id"])
        assert part.json()["doc_number"].startswith("DB-")
        after = ctx["s"].get(f"{BASE}/cash-register").json()
        assert after["closing"] == round(avail - 10, 2) and after["total_out"] == round(before["total_out"] + 10, 2)
        assert any(e["label"] == "depunere_banca" and e["id"] == part.json()["id"] for e in after["entries"])
        total = ctx["s"].post(f"{BASE}/cash-register/deposits", json={"amount": after["closing"], "reference": "TEST_TOTAL"})
        assert total.status_code == 200, total.text
        ctx["deposits"].append(total.json()["id"])
        final = ctx["s"].get(f"{BASE}/cash-register").json()
        assert final["closing"] == 0
        again = ctx["s"].post(f"{BASE}/cash-register/deposits", json={"amount": 0.01})
        assert again.status_code == 400
        # remove deposits immediately so real register is restored
        ctx["db"].cash_movements.delete_many({"_id": {"$in": [ObjectId(i) for i in ctx["deposits"]]}})
        restored = ctx["s"].get(f"{BASE}/cash-register").json()
        assert restored["closing"] == avail
