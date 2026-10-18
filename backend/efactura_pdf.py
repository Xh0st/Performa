import io
import xml.etree.ElementTree as ET
from pathlib import Path
from fastapi import HTTPException
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from xml.sax.saxutils import escape

NS = {"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
      "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"}
FONTS = Path(__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont("LS", str(FONTS / "LiberationSans-Regular.ttf")))
pdfmetrics.registerFont(TTFont("LSB", str(FONTS / "LiberationSans-Bold.ttf")))
ST = {k: ParagraphStyle(k, fontName=f, fontSize=s, leading=s * 1.3, alignment=al) for k, f, s, al in (
    ("n", "LS", 8, 0), ("b", "LSB", 8, 0), ("r", "LS", 8, 2), ("rb", "LSB", 9, 2), ("h", "LSB", 16, 2), ("sub", "LS", 9, 2), ("sm", "LS", 7, 0))}
TYPE_LABEL = {"380": "FACTURĂ", "381": "NOTĂ DE CREDIT / STORNARE", "384": "FACTURĂ CORECTATĂ", "389": "AUTOFACTURĂ", "751": "FACTURĂ – INFORMAȚII CONTABILE"}


def _t(el, path, default=""):
    x = el.find(path, NS) if el is not None else None
    return (x.text or "").strip() if x is not None and x.text else default


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _m(v, cur=""):
    s = f"{_f(v):,.2f}".replace(",", " ").replace(".", ",")
    return f"{s} {cur}".strip()


def _party(p):
    return {"name": _t(p, "cac:PartyLegalEntity/cbc:RegistrationName") or _t(p, "cac:PartyName/cbc:Name"),
            "vat": _t(p, "cac:PartyTaxScheme/cbc:CompanyID"), "legal": _t(p, "cac:PartyLegalEntity/cbc:CompanyID"),
            "reg": _t(p, "cac:PartyLegalEntity/cbc:CompanyLegalForm"),
            "addr": ", ".join(x for x in (_t(p, "cac:PostalAddress/cbc:StreetName"), _t(p, "cac:PostalAddress/cbc:CityName"),
                                          _t(p, "cac:PostalAddress/cbc:CountrySubentity"), _t(p, "cac:PostalAddress/cac:Country/cbc:IdentificationCode")) if x),
            "contact": " · ".join(x for x in (_t(p, "cac:Contact/cbc:Telephone"), _t(p, "cac:Contact/cbc:ElectronicMail")) if x)}


def parse_full(xml: str) -> dict:
    try:
        root = ET.fromstring(xml.encode() if isinstance(xml, str) else xml)
    except ET.ParseError as e:
        raise HTTPException(400, f"XML invalid: {e}")
    cn = root.tag.endswith("CreditNote")
    lines = []
    for ln in root.findall("cac:CreditNoteLine" if cn else "cac:InvoiceLine", NS):
        q = ln.find("cbc:CreditedQuantity" if cn else "cbc:InvoicedQuantity", NS)
        lines.append({"name": _t(ln, "cac:Item/cbc:Name"), "desc": _t(ln, "cac:Item/cbc:Description"),
                      "code": _t(ln, "cac:Item/cac:SellersItemIdentification/cbc:ID"), "qty": _f(q.text if q is not None else 0),
                      "unit": q.attrib.get("unitCode", "") if q is not None else "", "price": _f(_t(ln, "cac:Price/cbc:PriceAmount")),
                      "net": _f(_t(ln, "cbc:LineExtensionAmount")), "vat": _t(ln, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent", "0")})
    taxes = [{"base": _f(_t(s, "cbc:TaxableAmount")), "amount": _f(_t(s, "cbc:TaxAmount")), "cat": _t(s, "cac:TaxCategory/cbc:ID"),
              "rate": _t(s, "cac:TaxCategory/cbc:Percent", "0")} for s in root.findall("cac:TaxTotal/cac:TaxSubtotal", NS)]
    tot = root.find("cac:LegalMonetaryTotal", NS)
    return {"type": _t(root, "cbc:CreditNoteTypeCode" if cn else "cbc:InvoiceTypeCode", "381" if cn else "380"),
            "id": _t(root, "cbc:ID"), "issue": _t(root, "cbc:IssueDate"),
            "due": _t(root, "cbc:DueDate") or _t(root, "cac:PaymentMeans/cbc:PaymentDueDate"),
            "cur": _t(root, "cbc:DocumentCurrencyCode", "RON"), "notes": [n.text.strip() for n in root.findall("cbc:Note", NS) if n.text],
            "billing_ref": _t(root, "cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID"), "order_ref": _t(root, "cac:OrderReference/cbc:ID"),
            "seller": _party(root.find("cac:AccountingSupplierParty/cac:Party", NS)), "buyer": _party(root.find("cac:AccountingCustomerParty/cac:Party", NS)),
            "iban": _t(root, "cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID"), "bank": _t(root, "cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:Name"),
            "terms": _t(root, "cac:PaymentTerms/cbc:Note"), "lines": lines, "taxes": taxes,
            "net": _f(_t(tot, "cbc:TaxExclusiveAmount")), "vat": _f(_t(root, "cac:TaxTotal/cbc:TaxAmount")),
            "gross": _f(_t(tot, "cbc:TaxInclusiveAmount")), "allowance": _f(_t(tot, "cbc:AllowanceTotalAmount")),
            "prepaid": _f(_t(tot, "cbc:PrepaidAmount")), "payable": _f(_t(tot, "cbc:PayableAmount"))}


def _P(text, st="n"):
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), ST[st])


def _party_cell(label, p):
    rows = [_P(label, "sm"), _P(p["name"], "b")]
    if p["vat"] or p["legal"]:
        rows.append(_P(f"CIF: {p['vat'] or p['legal']}" + (f" · Reg. Com.: {p['reg']}" if p["reg"] else "")))
    if p["addr"]:
        rows.append(_P(p["addr"]))
    if p["contact"]:
        rows.append(_P(p["contact"]))
    return rows


def render_pdf(xml: str, meta: dict) -> bytes:
    d = parse_full(xml)
    cur = d["cur"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
                            title=f"e-Factura {d['id']}", author=d["seller"]["name"])
    W = A4[0] - 28 * mm
    head = Table([[_party_cell("FURNIZOR", d["seller"]),
                   [_P(TYPE_LABEL.get(d["type"], f"FACTURĂ (tip {d['type']})"), "h"), _P(f"Nr. {d['id']}", "rb"),
                    _P(f"Data emiterii: {d['issue']}", "sub")] + ([_P(f"Scadență: {d['due']}", "sub")] if d["due"] else [])
                   + ([_P(f"Factura stornată: {d['billing_ref']}", "sub")] if d["billing_ref"] else []) + [_P(f"Monedă: {cur}", "sub")]]],
                 colWidths=[W * 0.55, W * 0.45])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, colors.black), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    buyer = Table([[_party_cell("CUMPĂRĂTOR", d["buyer"]),
                    [_P("PLATĂ", "sm")] + ([_P(f"IBAN: {d['iban']}")] if d["iban"] else [_P("—")]) + ([_P(d["bank"])] if d["bank"] else [])
                    + ([_P(d["terms"])] if d["terms"] else []) + ([_P(f"Referință comandă: {d['order_ref']}")] if d["order_ref"] else [])]],
                  colWidths=[W * 0.55, W * 0.45])
    buyer.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                               ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F5F7")), ("TOPPADDING", (0, 0), (-1, -1), 6)]))
    rows = [[_P(h, "b") for h in ("Nr.", "Denumire produs / serviciu", "Cod", "UM", "Cant.", "Preț unitar", "Valoare", "TVA %")]]
    for i, ln in enumerate(d["lines"], 1):
        rows.append([_P(i), _P(ln["name"] + (f"\n{ln['desc']}" if ln["desc"] else "")), _P(ln["code"]), _P(ln["unit"]),
                     _P(f"{ln['qty']:g}", "r"), _P(_m(ln["price"]), "r"), _P(_m(ln["net"]), "r"), _P(ln["vat"], "r")])
    lines = Table(rows, colWidths=[W * w for w in (0.05, 0.37, 0.12, 0.06, 0.08, 0.12, 0.13, 0.07)], repeatRows=1)
    lines.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9AA0A6")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EAED")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    tax_rows = [[_P(h, "b") for h in ("Categorie TVA", "Cotă", "Bază impozabilă", "Valoare TVA")]] + [
        [_P(t["cat"]), _P(f"{t['rate']}%", "r"), _P(_m(t["base"], cur), "r"), _P(_m(t["amount"], cur), "r")] for t in d["taxes"]]
    taxes = Table(tax_rows, colWidths=[W * 0.14, W * 0.08, W * 0.16, W * 0.14])
    taxes.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9AA0A6")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EAED"))]))
    tot_rows = [["Total fără TVA", _m(d["net"], cur)], ["Total TVA", _m(d["vat"], cur)], ["Total cu TVA", _m(d["gross"], cur)]]
    if d["allowance"]:
        tot_rows.insert(1, ["Reduceri", _m(d["allowance"], cur)])
    if d["prepaid"]:
        tot_rows.append(["Avans plătit", _m(d["prepaid"], cur)])
    tot_rows.append(["TOTAL DE PLATĂ", _m(d["payable"], cur)])
    totals = Table([[_P(a, "b" if a == "TOTAL DE PLATĂ" else "n"), _P(b, "rb" if a == "TOTAL DE PLATĂ" else "r")] for a, b in tot_rows],
                   colWidths=[W * 0.24, W * 0.22])
    totals.setStyle(TableStyle([("LINEABOVE", (0, -1), (-1, -1), 1, colors.black)]))
    bottom = Table([[taxes, totals]], colWidths=[W * 0.54, W * 0.46])
    bottom.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story = [head, Spacer(1, 6), buyer, Spacer(1, 8), lines, Spacer(1, 8), bottom]
    if d["notes"]:
        story += [Spacer(1, 8), _P("Mențiuni", "b")] + [_P(n) for n in d["notes"]]
    src = " · ".join(x for x in (f"Index descărcare SPV: {meta['message_id']}" if meta.get("message_id") else "",
                                 f"Index încărcare: {meta['id_solicitare']}" if meta.get("id_solicitare") else "",
                                 f"Fișier importat: {meta['filename']}" if meta.get("filename") else "") if x)

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("LS", 6.5)
        canvas.setFillColor(colors.HexColor("#5F6368"))
        canvas.drawString(14 * mm, 9 * mm, "Vizualizare generată local din fișierul XML e-Factura (UBL / CIUS-RO). Documentul fiscal original este XML-ul semnat de MF.")
        canvas.drawString(14 * mm, 6 * mm, src[:160])
        canvas.drawRightString(A4[0] - 14 * mm, 6 * mm, f"Pagina {_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
