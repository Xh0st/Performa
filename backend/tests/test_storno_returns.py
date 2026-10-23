# Storno (CreditNote), restock on/off, supplier returns (with/without NIR), inbox PDF and multi-VAT UBL regression.
# Run serially: pytest /app/backend/tests/test_storno_returns.py -n 0   (shared TEST fixture, module scoped; full cleanup at end)
import sys
import xml.etree.ElementTree as ET
import pytest
import requests
import fitz
from bson import ObjectId

sys.path.insert(0, "/app/backend")
sys.path.insert(0, "/app/backend/tests")
from storno_fixtures import BASE, session, setup, teardown, residue, mdb, creds  # noqa: E402

NS = {"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
      "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"}


@pytest.fixture(scope="module")
def s():
    return session()


@pytest.fixture(scope="module")
def st(s):
    data = setup(s)
    data["cn"] = {}
    yield data
    res = teardown(data)
    print("CLEANUP", res, "RESIDUE", residue(data["tag"]))
    assert all(v == 0 for v in residue(data["tag"]).values())


def prod(s, pid):
    return next(p for p in s.get(f"{BASE}/products", params={"q": pid}).json())


def stock(s, st, key):
    return mdb().products.find_one({"_id": ObjectId(st[key])})["stock_qty"]


def moves(st, key, ref):
    return list(mdb().stock_moves.find({"product_id": st[key], "ref": ref}))


def subtotals(root):
    tt = root.find("cac:TaxTotal", NS)
    out = {}
    for sub in tt.findall("cac:TaxSubtotal", NS):
        out[float(sub.find("cac:TaxCategory/cbc:Percent", NS).text)] = (float(sub.find("cbc:TaxableAmount", NS).text),
                                                                        float(sub.find("cbc:TaxAmount", NS).text))
    return float(tt.find("cbc:TaxAmount", NS).text), out


# --- fixture sanity: invoice consumed stock FIFO
class TestA_Setup:
    def test_invoice_created(self, s, st):
        inv = s.get(f"{BASE}/invoices/{st['invoice']}").json()
        assert inv["totals"] == {"net": 605.0, "vat": 119.05, "gross": 724.05, "by_type": {"part": 380.0, "labor": 225.0}}
        assert inv["cogs"] == 190.0
        assert all(ln["credited_qty"] == 0 for ln in inv["lines"])
        assert stock(s, st, "p1") == 11 and stock(s, st, "p2") == 3


# --- storno validation + partial (restock ON) + total (restock OFF)
class TestB_Storno:
    def test_validation(self, s, st):
        url = f"{BASE}/invoices/{st['invoice']}/storno"
        assert s.post(url, json={"reason": " ", "lines": [{"line_id": "l_p1", "qty": 1}]}).status_code == 400
        r = s.post(url, json={"reason": "TEST", "lines": [{"line_id": "l_p1", "qty": 4}]})
        assert r.status_code == 400 and "3" in r.json()["detail"]
        assert s.post(url, json={"reason": "TEST", "lines": [{"line_id": "nope", "qty": 1}]}).status_code == 400
        assert s.post(url, json={"reason": "TEST", "lines": [{"line_id": "l_p1", "qty": 0}]}).status_code == 400
        assert s.post(url, json={"reason": "TEST", "lines": []}).status_code == 400
        assert s.post(f"{BASE}/invoices/000000000000000000000000/storno", json={"reason": "x", "lines": []}).status_code == 404

    def test_partial_restock_on(self, s, st):
        r = s.post(f"{BASE}/invoices/{st['invoice']}/storno", json={"reason": "TEST partial", "restock": True,
                                                                  "lines": [{"line_id": "l_p1", "qty": 1}, {"line_id": "l_lab", "qty": 0.5}]})
        assert r.status_code == 200, r.text
        cn = r.json()
        st["cn"]["partial"] = cn["id"]
        assert cn["kind"] == "credit_note" and cn["original_invoice_id"] == st["invoice"] and cn["original_ref"] == st["invoice_ref"]
        assert cn["status"] == "credit" and cn["restocked"] is True and cn["storno_reason"] == "TEST partial"
        assert cn["totals"]["gross"] == -211.75 and cn["totals"]["net"] == -175.0 and cn["totals"]["vat"] == -36.75
        assert sorted(ln["qty"] for ln in cn["lines"]) == [-1, -0.5]
        assert {ln["original_line_id"] for ln in cn["lines"]} == {"l_p1", "l_lab"}
        assert cn["cogs"] == -50.0
        ref = f"{cn['series']}{cn['number']}"
        assert stock(s, st, "p1") == 12 and stock(s, st, "p2") == 3
        mv = moves(st, "p1", ref)
        assert len(mv) == 1 and mv[0]["kind"] == "in" and mv[0]["qty"] == 1 and mv[0]["unit_cost"] == 50
        inv = s.get(f"{BASE}/invoices/{st['invoice']}").json()
        cq = {ln["id"]: ln["credited_qty"] for ln in inv["lines"]}
        assert cq == {"l_p1": 1, "l_p2": 0, "l_lab": 0.5}
        assert inv["storno_status"] == "partial" and inv["credited_amount"] == 211.75 and inv["status"] == "unpaid"
        assert inv["credit_notes"][0]["id"] == cn["id"] and inv["credit_notes"][0]["gross"] == -211.75

    def test_over_credit_after_partial(self, s, st):
        r = s.post(f"{BASE}/invoices/{st['invoice']}/storno", json={"reason": "TEST", "lines": [{"line_id": "l_p1", "qty": 2.5}]})
        assert r.status_code == 400 and "2" in r.json()["detail"]

    def test_payment_due_reflects_credit(self, s, st):
        r = s.post(f"{BASE}/payments", json={"invoice_id": st["invoice"], "amount": 600, "method": "numerar"})
        assert r.status_code == 400 and "512.30" in r.json()["detail"]

    def test_total_restock_off(self, s, st):
        r = s.post(f"{BASE}/invoices/{st['invoice']}/storno", json={"reason": "TEST rest", "restock": False,
                                                                  "lines": [{"line_id": "l_p1", "qty": 2}, {"line_id": "l_p2", "qty": 2}, {"line_id": "l_lab", "qty": 1}]})
        assert r.status_code == 200, r.text
        cn = r.json()
        st["cn"]["total"] = cn["id"]
        assert cn["totals"]["gross"] == -512.3 and cn["restocked"] is False and cn["cogs"] == 0
        ref = f"{cn['series']}{cn['number']}"
        assert stock(s, st, "p1") == 12 and stock(s, st, "p2") == 3
        assert moves(st, "p1", ref) == [] and moves(st, "p2", ref) == []
        inv = s.get(f"{BASE}/invoices/{st['invoice']}").json()
        assert {ln["id"]: ln["credited_qty"] for ln in inv["lines"]} == {"l_p1": 3, "l_p2": 2, "l_lab": 1.5}
        assert inv["storno_status"] == "total" and inv["credited_amount"] == 724.05 and inv["status"] == "paid"
        assert len(inv["credit_notes"]) == 2

    def test_no_more_storno(self, s, st):
        r = s.post(f"{BASE}/invoices/{st['invoice']}/storno", json={"reason": "TEST", "lines": [{"line_id": "l_p2", "qty": 1}]})
        assert r.status_code == 400
        r = s.post(f"{BASE}/invoices/{st['cn']['total']}/storno", json={"reason": "TEST", "lines": [{"line_id": "x", "qty": 1}]})
        assert r.status_code == 400
        r = s.post(f"{BASE}/payments", json={"invoice_id": st["cn"]["total"], "amount": 1, "method": "numerar"})
        assert r.status_code == 400

    def test_credit_note_detail_and_list(self, s, st):
        cn = s.get(f"{BASE}/invoices/{st['cn']['partial']}").json()
        assert cn["kind"] == "credit_note" and "credited_qty" not in cn["lines"][0]
        ids = [i["id"] for i in s.get(f"{BASE}/invoices").json()]
        assert st["cn"]["partial"] in ids and st["cn"]["total"] in ids

    def test_rbac_mecanic(self, st):
        txt = open("/app/memory/test_credentials.md").read()
        pw = [ln for ln in txt.splitlines() if "Demo users" in ln][0].split(":")[-1].strip(" )!") + "!"
        m = requests.Session()
        r = m.post(f"{BASE}/auth/login", json={"email": "mecanic@serviceauto.ro", "password": pw})
        if r.status_code != 200:
            pytest.skip("mecanic login failed")
        m.headers["Authorization"] = f"Bearer {r.json()['token']}"
        assert m.post(f"{BASE}/invoices/{st['invoice']}/storno", json={"reason": "x", "lines": []}).status_code == 403
        assert m.post(f"{BASE}/supplier-returns", json={"supplier_id": st["supplier"], "reason": "x", "lines": []}).status_code == 403


# --- UBL: CreditNote + Invoice with 2 VAT rates
class TestC_Ubl:
    def test_invoice_ubl_two_rates(self, s, st):
        r = s.get(f"{BASE}/invoices/{st['invoice']}/efactura/xml")
        assert r.status_code == 200
        root = ET.fromstring(r.content)
        assert root.tag.endswith("}Invoice") and root.find("cbc:InvoiceTypeCode", NS).text == "380"
        tax, subs = subtotals(root)
        assert subs == {11.0: (80.0, 8.8), 21.0: (525.0, 110.25)} and tax == 119.05
        assert round(sum(v for _, v in subs.values()), 2) == tax
        lmt = root.find("cac:LegalMonetaryTotal", NS)
        assert float(lmt.find("cbc:TaxExclusiveAmount", NS).text) == 605.0 and float(lmt.find("cbc:PayableAmount", NS).text) == 724.05
        assert len(root.findall("cac:InvoiceLine", NS)) == 3
        assert sum(float(e.find("cbc:LineExtensionAmount", NS).text) for e in root.findall("cac:InvoiceLine", NS)) == 605.0

    def test_credit_note_ubl(self, s, st):
        r = s.get(f"{BASE}/invoices/{st['cn']['total']}/efactura/xml")
        root = ET.fromstring(r.content)
        assert root.tag.endswith("}CreditNote") and root.find("cbc:CreditNoteTypeCode", NS).text == "381"
        ref = root.find("cac:BillingReference/cac:InvoiceDocumentReference", NS)
        assert ref.find("cbc:ID", NS).text == st["invoice_ref"]
        tax, subs = subtotals(root)
        assert subs == {11.0: (80.0, 8.8), 21.0: (350.0, 73.5)} and tax == 82.3
        lines = root.findall("cac:CreditNoteLine", NS)
        assert len(lines) == 3 and all(float(ln.find("cbc:CreditedQuantity", NS).text) > 0 for ln in lines)
        assert float(root.find("cac:LegalMonetaryTotal/cbc:PayableAmount", NS).text) == 512.3

    def test_validate_cn(self, s, st):
        r = s.post(f"{BASE}/invoices/{st['cn']['partial']}/efactura/validate")
        assert r.status_code == 200
        print("validate CN errors:", r.json()["errors"])

    def test_build_ubl_three_rates_unit(self):
        from efactura import build_ubl
        from core import calc_totals
        lines = [{"type": "part", "description": "A", "qty": 2, "unit_price": 10.555, "vat_rate": 21, "code": "A"},
                 {"type": "part", "description": "B", "qty": 1, "unit_price": 33.33, "vat_rate": 11},
                 {"type": "labor", "description": "C", "qty": 1, "unit_price": 50, "vat_rate": 0}]
        t = calc_totals(lines)
        inv = {"series": "TEST", "number": "1", "issue_date": "2026-01-01", "due_date": "2026-01-15", "lines": lines, "totals": t,
               "seller": {"name": "S", "cui": "RO1"}, "buyer": {"name": "B"}}
        root = ET.fromstring(build_ubl(inv).encode())
        tax, subs = subtotals(root)
        assert set(subs) == {0.0, 11.0, 21.0}
        assert round(sum(v for _, v in subs.values()), 2) == tax == t["vat"]
        assert round(sum(n for n, _ in subs.values()), 2) == t["net"]
        cats = [e.text for e in root.findall("cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:ID", NS)]
        assert cats == ["Z", "S", "S"]


# --- supplier returns
class TestD_Returns:
    def test_return_with_nir(self, s, st):
        r = s.post(f"{BASE}/supplier-returns", json={"supplier_id": st["supplier"], "nir_id": st["nir2"], "reason": "TEST defect",
                                                     "lines": [{"product_id": st["p1"], "qty": 3}]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["number"].startswith("RET-") and d["nir_number"] == st["nir2_number"] and d["nir_invoice_no"].startswith("TEST-F2")
        ln = d["lines"][0]
        assert ln["qty"] == 3 and ln["unit_cost"] == 60 and ln["value"] == 180 and ln["vat"] == 37.8 and ln["stock_cost"] == 180
        assert d["total"] == 180 and d["total_vat"] == 37.8
        assert stock(s, st, "p1") == 9
        mv = moves(st, "p1", d["number"])
        assert len(mv) == 1 and mv[0]["kind"] == "out" and mv[0]["unit_cost"] == 60
        n = s.get(f"{BASE}/nirs/{st['nir2']}").json()
        assert n["lines"][0]["returned_qty"] == 3
        assert s.get(f"{BASE}/supplier-returns/{d['id']}").json()["number"] == d["number"]
        assert d["id"] in [x["id"] for x in s.get(f"{BASE}/supplier-returns").json()]

    def test_nir_qty_limit(self, s, st):
        r = s.post(f"{BASE}/supplier-returns", json={"supplier_id": st["supplier"], "nir_id": st["nir2"], "reason": "TEST",
                                                     "lines": [{"product_id": st["p1"], "qty": 2}]})
        assert r.status_code == 400 and "1" in r.json()["detail"]

    def test_nir_wrong_supplier_and_product(self, s, st):
        r = s.post(f"{BASE}/supplier-returns", json={"supplier_id": st["supplier2"], "nir_id": st["nir2"], "reason": "TEST",
                                                     "lines": [{"product_id": st["p1"], "qty": 1}]})
        assert r.status_code == 400
        r = s.post(f"{BASE}/supplier-returns", json={"supplier_id": st["supplier"], "nir_id": st["nir2"], "reason": "TEST",
                                                     "lines": [{"product_id": st["p2"], "qty": 1}]})
        assert r.status_code == 400 and "nu se află" in r.json()["detail"]

    def test_return_without_nir_fifo(self, s, st):
        r = s.post(f"{BASE}/supplier-returns", json={"supplier_id": st["supplier"], "reason": "TEST fara NIR",
                                                     "lines": [{"product_id": st["p2"], "qty": 1}]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["nir_id"] == "" and d["nir_number"] == ""
        assert d["lines"][0]["unit_cost"] == 20 and d["total"] == 20 and d["total_vat"] == 2.2
        assert stock(s, st, "p2") == 2

    def test_duplicate_lines_aggregated(self, s, st):
        r = s.post(f"{BASE}/supplier-returns", json={"supplier_id": st["supplier"], "reason": "TEST dup",
                                                     "lines": [{"product_id": st["p1"], "qty": 1}, {"product_id": st["p1"], "qty": 1}]})
        assert r.status_code == 200
        d = r.json()
        assert len(d["lines"]) == 1 and d["lines"][0]["qty"] == 2 and d["lines"][0]["unit_cost"] == 50
        assert stock(s, st, "p1") == 7

    def test_validation(self, s, st):
        u = f"{BASE}/supplier-returns"
        assert s.post(u, json={"supplier_id": st["supplier"], "reason": "TEST", "lines": [{"product_id": st["p2"], "qty": 5}]}).status_code == 400
        assert s.post(u, json={"supplier_id": st["supplier"], "reason": "TEST", "lines": [{"product_id": st["p2"], "qty": 0}]}).status_code == 400
        assert s.post(u, json={"supplier_id": st["supplier"], "reason": "TEST", "lines": [{"product_id": st["p2"], "qty": -1}]}).status_code == 400
        assert s.post(u, json={"supplier_id": st["supplier"], "reason": "", "lines": [{"product_id": st["p2"], "qty": 1}]}).status_code == 400
        assert s.post(u, json={"supplier_id": st["supplier"], "reason": "TEST", "lines": []}).status_code == 400
        assert s.post(u, json={"supplier_id": "000000000000000000000000", "reason": "TEST", "lines": []}).status_code == 404
        assert stock(s, st, "p2") == 2 and stock(s, st, "p1") == 7


# --- inbox PDF (read-only on existing messages)
class TestE_Pdf:
    def test_pdf_all_messages(self, s):
        msgs = s.get(f"{BASE}/efactura/inbox").json()
        if not msgs:
            pytest.skip("no inbox messages")
        for m in msgs:
            r = s.get(f"{BASE}/efactura/inbox/{m['id']}/pdf")
            assert r.status_code == 200, (m["id"], r.text[:200])
            assert r.headers["content-type"] == "application/pdf" and r.content[:5] == b"%PDF-" and b"%%EOF" in r.content[-1024:]
            assert "inline" in r.headers.get("content-disposition", "")
            doc = fitz.open(stream=r.content, filetype="pdf")
            text = "".join(p.get_text() for p in doc)
            assert doc.page_count >= 1 and m["parsed"]["series_number"] in text
            pix = doc[0].get_pixmap(dpi=40)
            assert pix.width > 0

    def test_pdf_auth_and_404(self, s):
        msgs = s.get(f"{BASE}/efactura/inbox").json()
        if msgs:
            assert requests.get(f"{BASE}/efactura/inbox/{msgs[0]['id']}/pdf").status_code == 401
        assert s.get(f"{BASE}/efactura/inbox/000000000000000000000000/pdf").status_code == 404
