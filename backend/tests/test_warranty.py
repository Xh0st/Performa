# Warranty module: auto certificate at fiscal invoice, PDF, listing active/expired, claims -> zero-cost "Garanție" WO, claim update, WO alerts, RBAC.
# Run serially: pytest /app/backend/tests/test_warranty.py -n 0  (module-scoped TEST fixture; full cleanup + counter restore at end)
import sys
from datetime import date

import fitz
import pytest
import requests
from bson import ObjectId
from dateutil.relativedelta import relativedelta

sys.path.insert(0, "/app/backend/tests")
from warranty_fixtures import BASE, mdb, residue, session, setup, teardown  # noqa: E402


@pytest.fixture(scope="module")
def s():
    return session()


@pytest.fixture(scope="module")
def st(s):
    data = setup(s)
    yield data
    res = teardown(data)
    print("CLEANUP", res, "RESIDUE", residue(data["tag"]))
    assert all(v == 0 for v in residue(data["tag"]).values())


def cert_doc(st):
    return mdb().warranty_certificates.find_one({"invoice_id": st["invoice"]})


# --- 1) certificate auto-created exactly once, periods
class TestA_Certificate:
    def test_exactly_one_certificate_and_none_for_proforma(self, st):
        db = mdb()
        assert db.warranty_certificates.count_documents({"invoice_id": st["invoice"]}) == 1
        assert db.warranty_certificates.count_documents({"invoice_id": st["proforma"]}) == 0

    def test_periods(self, st):
        c = cert_doc(st)
        issue = date.fromisoformat(st["issue_date"])
        by = {ln["source_line_id"]: ln for ln in c["lines"]}
        assert set(by) == {"g_p1", "g_p2", "g_lab"}
        assert by["g_p1"]["warranty_months"] == 12 and by["g_p1"]["valid_to"] == (issue + relativedelta(months=12)).isoformat()
        assert by["g_p2"]["warranty_months"] == 24 and by["g_p2"]["valid_to"] == (issue + relativedelta(months=24)).isoformat()
        assert by["g_lab"]["warranty_months"] == 3 and by["g_lab"]["label"] == "Manoperă"
        assert by["g_lab"]["valid_to"] == (issue + relativedelta(months=3)).isoformat()
        assert c["invoice_ref"] == st["invoice_ref"] and c["work_order_id"] == st["wo"] and c["vehicle_id"] == st["vehicle"]
        assert c["number"].startswith(f"GAR-{issue.year}-")

    def test_invoice_exposes_only_metadata(self, s, st):
        inv = s.get(f"{BASE}/invoices/{st['invoice']}").json()
        wc = inv["warranty_certificate"]
        assert set(wc) == {"id", "number", "issued_date"}, wc
        prof = s.get(f"{BASE}/invoices/{st['proforma']}").json()
        assert prof["warranty_certificate"] is None


# --- 2) PDF
class TestB_PDF:
    def test_pdf_valid_with_diacritics(self, s, st):
        r = s.get(f"{BASE}/warranties/invoices/{st['invoice']}/certificate")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        num = cert_doc(st)["number"]
        assert f'filename="{num}.pdf"' in r.headers.get("content-disposition", "")
        assert r.content[:5] == b"%PDF-"
        doc = fitz.open(stream=r.content, filetype="pdf")
        text = "".join(p.get_text() for p in doc)
        open("/tmp/warranty_cert.pdf", "wb").write(r.content)
        for needle in ("CERTIFICAT DE GARANȚIE", "Articol / operațiune", "Manoperă", "TEST Plăcuțe frână față", "12 luni", "24 luni", "3 luni",
                       st["invoice_ref"], num):
            assert needle in text, needle

    def test_pdf_404_without_certificate(self, s, st):
        assert s.get(f"{BASE}/warranties/invoices/{st['proforma']}/certificate").status_code == 404
        assert s.get(f"{BASE}/warranties/invoices/{st['proforma']}").status_code == 404

    def test_pdf_special_chars_in_description(self, s, st):
        db = mdb()
        c = cert_doc(st)
        orig = c["lines"][0]["description"]
        db.warranty_certificates.update_one({"_id": c["_id"]}, {"$set": {"lines.0.description": "Ulei & filtru <5W30>"}})
        try:
            r = s.get(f"{BASE}/warranties/invoices/{st['invoice']}/certificate")
            assert r.status_code == 200, f"PDF fails for '&'/'<' in description: {r.status_code}"
        finally:
            db.warranty_certificates.update_one({"_id": c["_id"]}, {"$set": {"lines.0.description": orig}})


# --- 3) listing active/expired + 6) WO alerts
class TestC_ListingAlerts:
    def test_active_listing(self, s, st):
        num = cert_doc(st)["number"]
        act = s.get(f"{BASE}/warranties", params={"status": "active"}).json()
        row = next(r for r in act if r["number"] == num)
        assert row["status"] == "active" and len(row["active_lines"]) == 3
        assert num not in [r["number"] for r in s.get(f"{BASE}/warranties", params={"status": "expired"}).json()]
        assert num in [r["number"] for r in s.get(f"{BASE}/warranties", params={"status": ""}).json()]

    def test_wo_alert_active(self, s, st):
        wo = s.get(f"{BASE}/work-orders/{st['wo']}").json()
        num = cert_doc(st)["number"]
        assert [a for a in wo["warranty_alerts"] if a["number"] == num and a["active_lines"] == 3]

    def test_expired_listing_and_alert_gone(self, s, st):
        db = mdb()
        c = cert_doc(st)
        orig = [ln["valid_to"] for ln in c["lines"]]
        db.warranty_certificates.update_one({"_id": c["_id"]}, {"$set": {f"lines.{i}.valid_to": "2020-01-01" for i in range(len(orig))}})
        try:
            exp = s.get(f"{BASE}/warranties", params={"status": "expired"}).json()
            row = next(r for r in exp if r["number"] == c["number"])
            assert row["status"] == "expired" and row["active_lines"] == []
            wo = s.get(f"{BASE}/work-orders/{st['wo']}").json()
            assert not [a for a in wo["warranty_alerts"] if a["number"] == c["number"]]
        finally:
            db.warranty_certificates.update_one({"_id": c["_id"]}, {"$set": {f"lines.{i}.valid_to": v for i, v in enumerate(orig)}})


# --- 4) claims validation and creation
class TestD_Claims:
    @pytest.mark.parametrize("payload_lines,desc", [
        ([{"source_line_id": "g_p1", "qty": 0}], "d"),
        ([{"source_line_id": "g_p1", "qty": -1}], "d"),
        ([{"source_line_id": "g_p1", "qty": 3}], "d"),
        ([{"source_line_id": "nope", "qty": 1}], "d"),
        ([], "d"),
        ([{"source_line_id": "g_p1", "qty": 1}], "   "),
    ])
    def test_invalid_claims_rejected(self, s, st, payload_lines, desc):
        before = mdb().work_orders.count_documents({"is_warranty": True})
        r = s.post(f"{BASE}/warranty-claims", json={"invoice_id": st["invoice"], "description": desc, "lines": payload_lines})
        assert r.status_code == 400, r.text
        assert mdb().work_orders.count_documents({"is_warranty": True}) == before

    def test_no_certificate_rejected(self, s, st):
        r = s.post(f"{BASE}/warranty-claims", json={"invoice_id": st["proforma"], "description": "x", "lines": [{"source_line_id": "g_p1", "qty": 1}]})
        assert r.status_code == 400

    def test_expired_line_rejected(self, s, st):
        db = mdb()
        c = cert_doc(st)
        idx = [ln["source_line_id"] for ln in c["lines"]].index("g_lab")
        orig = c["lines"][idx]["valid_to"]
        db.warranty_certificates.update_one({"_id": c["_id"]}, {"$set": {f"lines.{idx}.valid_to": "2020-01-01"}})
        try:
            r = s.post(f"{BASE}/warranty-claims", json={"invoice_id": st["invoice"], "description": "TEST exp",
                                                        "lines": [{"source_line_id": "g_lab", "qty": 1}]})
            assert r.status_code == 400
        finally:
            db.warranty_certificates.update_one({"_id": c["_id"]}, {"$set": {f"lines.{idx}.valid_to": orig}})

    def test_duplicate_line_in_request_over_qty(self, s, st):
        r = s.post(f"{BASE}/warranty-claims", json={"invoice_id": st["invoice"], "description": "TEST dup",
                                                    "lines": [{"source_line_id": "g_p1", "qty": 2}, {"source_line_id": "g_p1", "qty": 2}]})
        if r.status_code == 200:
            mdb().warranty_claims.delete_one({"_id": ObjectId(r.json()["id"])})
            mdb().work_orders.delete_one({"_id": ObjectId(r.json()["work_order_id"])})
        assert r.status_code == 400, "duplicate source_line_id lets claimed qty (4) exceed invoiced qty (2)"

    def test_valid_claim_creates_zero_cost_wo(self, s, st):
        db = mdb()
        before = db.work_orders.count_documents({"vehicle_id": st["vehicle"], "is_warranty": True})
        r = s.post(f"{BASE}/warranty-claims", json={"invoice_id": st["invoice"], "description": "TEST Zgomot la frânare",
                                                    "lines": [{"source_line_id": "g_p1", "qty": 1}, {"source_line_id": "g_lab", "qty": 1.5}]})
        assert r.status_code == 200, r.text
        cl = r.json()
        st["claim"] = cl
        assert cl["number"].startswith("DG-") and cl["invoice_id"] == st["invoice"] and cl["invoice_ref"] == st["invoice_ref"]
        assert cl["technical_result"] == "in_asteptare" and cl["resolution"] == "in_analiza" and cl["supplier_return_status"] == "nu_este_cazul"
        assert [ln["qty"] for ln in cl["lines"]] == [1, 1.5]
        assert db.work_orders.count_documents({"vehicle_id": st["vehicle"], "is_warranty": True}) == before + 1
        wo = s.get(f"{BASE}/work-orders/{cl['work_order_id']}").json()
        assert wo["number"] == cl["work_order_number"] and wo["is_warranty"] is True and wo["warranty_claim_number"] == cl["number"]
        assert wo["client_id"] == st["client"] and wo["vehicle_id"] == st["vehicle"] and wo["status"] == "noua"
        assert len(wo["lines"]) == 2 and all(ln["unit_price"] == 0 for ln in wo["lines"])
        assert {ln["type"] for ln in wo["lines"]} == {"part", "labor"}
        assert cl["number"] in wo["complaint"]

    def test_claims_list(self, s, st):
        rows = s.get(f"{BASE}/warranty-claims").json()
        assert st["claim"]["id"] in [r["id"] for r in rows]

    def test_cumulative_overclaim(self, s, st):
        # first claim took 1 of 2 for g_p1; claim 2 more -> cumulative 3 > 2 invoiced
        r = s.post(f"{BASE}/warranty-claims", json={"invoice_id": st["invoice"], "description": "TEST second",
                                                    "lines": [{"source_line_id": "g_p1", "qty": 2}]})
        if r.status_code == 200:
            st["claim2"] = r.json()
        assert r.status_code == 400, "cumulative claimed qty across claims (3) exceeds invoiced qty (2)"


# --- 5) claim update
class TestE_Update:
    @pytest.mark.parametrize("field,value", [("technical_result", "x"), ("supplier_return_status", "x"), ("resolution", "x")])
    def test_invalid_enum(self, s, st, field, value):
        r = s.put(f"{BASE}/warranty-claims/{st['claim']['id']}", json={field: value})
        assert r.status_code == 400

    def test_not_found(self, s):
        assert s.put(f"{BASE}/warranty-claims/{ObjectId()}", json={}).status_code == 404
        assert s.put(f"{BASE}/warranty-claims/bad", json={}).status_code == 404

    def test_update_persists_and_links_kept(self, s, st):
        body = {"technical_result": "neconform", "supplier_return_status": "trimis", "supplier_return_id": "",
                "resolution": "admis_inlocuit", "notes": "TEST piesă defectă"}
        r = s.put(f"{BASE}/warranty-claims/{st['claim']['id']}", json=body)
        assert r.status_code == 200
        row = next(x for x in s.get(f"{BASE}/warranty-claims").json() if x["id"] == st["claim"]["id"])
        for k, v in body.items():
            assert row[k] == v
        assert row["invoice_id"] == st["invoice"] and row["work_order_id"] == st["claim"]["work_order_id"]
        assert row["updated_by"]

    def test_supplier_return_id_validated(self, s, st):
        r = s.put(f"{BASE}/warranty-claims/{st['claim']['id']}", json={"supplier_return_status": "trimis", "supplier_return_id": str(ObjectId()),
                                                                        "resolution": "in_analiza", "technical_result": "neconform"})
        assert r.status_code in (400, 404), "nonexistent supplier_return_id accepted"

    def test_conform_cannot_be_admitted(self, s, st):
        r = s.put(f"{BASE}/warranty-claims/{st['claim']['id']}", json={"technical_result": "conform", "resolution": "admis_rambursat"})
        assert r.status_code == 400, "technical_result=conform (no defect) + resolution=admis accepted (no cross-validation)"


# --- RBAC
class TestF_RBAC:
    def test_no_token(self):
        assert requests.get(f"{BASE}/warranties").status_code == 401
        assert requests.get(f"{BASE}/warranty-claims").status_code == 401

    def test_mecanic_forbidden(self, st):
        m = session("mecanic@")
        assert m.get(f"{BASE}/warranties").status_code == 403
        assert m.post(f"{BASE}/warranty-claims", json={"invoice_id": st["invoice"], "description": "x", "lines": []}).status_code == 403

    def test_magazioner_can_use_claim_flow(self, st):
        m = session("magazie@")
        assert m.get(f"{BASE}/warranties").status_code == 200
        # ClaimDialog/download need these; magazioner has 'warranties' but not 'invoices'
        assert m.get(f"{BASE}/warranties/invoices/{st['invoice']}").status_code == 200
        assert m.get(f"{BASE}/warranties/invoices/{st['invoice']}/certificate").status_code == 200
