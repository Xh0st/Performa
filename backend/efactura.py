from xml.sax.saxutils import escape as x

CIUS_RO = "urn:cen.eu:en16931:2017#compliant#urn:efactura.mfinante.ro:CIUS-RO:1.0.1"


def _party(tag: str, p: dict, is_seller: bool) -> str:
    cui = (p.get("cui") or "").upper().replace(" ", "")
    is_pj = bool(cui)
    vat_id = cui if cui.startswith("RO") else ""
    legal_id = cui.replace("RO", "") if is_pj else (p.get("cnp") or "0000000000000")
    county = p.get("county_code") or "RO-B"
    tax = (f"<cac:PartyTaxScheme><cbc:CompanyID>{x(vat_id)}</cbc:CompanyID><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>"
           if vat_id else "")
    reg = f"<cbc:CompanyLegalForm>{x(p.get('reg_com', ''))}</cbc:CompanyLegalForm>" if is_seller and p.get("reg_com") else ""
    contact = ""
    if p.get("phone") or p.get("email"):
        contact = (f"<cac:Contact><cbc:Telephone>{x(p.get('phone', ''))}</cbc:Telephone>"
                   f"<cbc:ElectronicMail>{x(p.get('email', ''))}</cbc:ElectronicMail></cac:Contact>")
    return (f"<cac:{tag}><cac:Party>"
            f"<cac:PostalAddress><cbc:StreetName>{x(p.get('address', '') or '-')}</cbc:StreetName>"
            f"<cbc:CityName>{x(p.get('city', '') or '-')}</cbc:CityName><cbc:CountrySubentity>{x(county)}</cbc:CountrySubentity>"
            f"<cac:Country><cbc:IdentificationCode>RO</cbc:IdentificationCode></cac:Country></cac:PostalAddress>"
            f"{tax}<cac:PartyLegalEntity><cbc:RegistrationName>{x(p.get('name', ''))}</cbc:RegistrationName>"
            f"<cbc:CompanyID>{x(legal_id)}</cbc:CompanyID>{reg}</cac:PartyLegalEntity>{contact}</cac:Party></cac:{tag}>")


def _cat(rate: float) -> str:
    return "S" if rate else "Z"


def build_ubl(inv: dict) -> str:
    """UBL 2.1 Invoice / CreditNote (stornare) conform CIUS-RO."""
    cn = inv.get("kind") == "credit_note"
    a = abs if cn else (lambda v: v)
    root, line_tag, qty_tag = ("CreditNote", "CreditNoteLine", "CreditedQuantity") if cn else ("Invoice", "InvoiceLine", "InvoicedQuantity")
    cur = inv.get("currency", "RON")
    t = inv["totals"]
    groups = {}
    for ln in inv["lines"]:
        g = groups.setdefault(float(ln.get("vat_rate", 21)), [0.0, 0.0])
        g[0] += a(ln["net"])
        g[1] += a(ln["vat"])
    subtotals = "".join(
        f"<cac:TaxSubtotal><cbc:TaxableAmount currencyID=\"{cur}\">{n:.2f}</cbc:TaxableAmount><cbc:TaxAmount currencyID=\"{cur}\">{v:.2f}</cbc:TaxAmount>"
        f"<cac:TaxCategory><cbc:ID>{_cat(rate)}</cbc:ID><cbc:Percent>{rate:.2f}</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>"
        f"</cac:TaxCategory></cac:TaxSubtotal>" for rate, (n, v) in sorted(groups.items()))
    lines_xml = ""
    for i, ln in enumerate(inv["lines"], 1):
        unit = "HUR" if ln["type"] == "labor" else "H87"
        qty, net = a(ln["qty"]), a(ln["net"])
        price = round(net / qty, 4) if qty else 0
        rate = float(ln.get("vat_rate", 21))
        lines_xml += (
            f"<cac:{line_tag}><cbc:ID>{i}</cbc:ID><cbc:{qty_tag} unitCode=\"{unit}\">{qty:.2f}</cbc:{qty_tag}>"
            f"<cbc:LineExtensionAmount currencyID=\"{cur}\">{net:.2f}</cbc:LineExtensionAmount>"
            f"<cac:Item><cbc:Name>{x(ln['description'][:100])}</cbc:Name>"
            + (f"<cac:SellersItemIdentification><cbc:ID>{x(ln['code'])}</cbc:ID></cac:SellersItemIdentification>" if ln.get("code") else "")
            + f"<cac:ClassifiedTaxCategory><cbc:ID>{_cat(rate)}</cbc:ID><cbc:Percent>{rate:.2f}</cbc:Percent>"
            f"<cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:ClassifiedTaxCategory></cac:Item>"
            f"<cac:Price><cbc:PriceAmount currencyID=\"{cur}\">{price:.4f}</cbc:PriceAmount></cac:Price></cac:{line_tag}>")
    seller = inv["seller"]
    payment = ""
    if seller.get("iban"):
        payment = (f"<cac:PaymentMeans><cbc:PaymentMeansCode>31</cbc:PaymentMeansCode><cac:PayeeFinancialAccount>"
                   f"<cbc:ID>{x(seller['iban'])}</cbc:ID><cbc:Name>{x(seller.get('bank', ''))}</cbc:Name></cac:PayeeFinancialAccount></cac:PaymentMeans>")
    if cn:
        head = (f"<cbc:CreditNoteTypeCode>381</cbc:CreditNoteTypeCode>"
                f"<cbc:Note>Stornare factura {x(inv.get('original_ref', ''))}{' - ' + x(inv['storno_reason']) if inv.get('storno_reason') else ''}</cbc:Note>"
                f"<cbc:DocumentCurrencyCode>{cur}</cbc:DocumentCurrencyCode>"
                f"<cac:BillingReference><cac:InvoiceDocumentReference><cbc:ID>{x(inv.get('original_ref', ''))}</cbc:ID>"
                f"<cbc:IssueDate>{inv.get('original_issue_date', '')}</cbc:IssueDate></cac:InvoiceDocumentReference></cac:BillingReference>")
    else:
        head = (f"<cbc:DueDate>{inv['due_date']}</cbc:DueDate><cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>"
                f"<cbc:Note>Comanda de lucru {x(inv.get('work_order_number', ''))}</cbc:Note>"
                f"<cbc:DocumentCurrencyCode>{cur}</cbc:DocumentCurrencyCode>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<{root} xmlns="urn:oasis:names:specification:ubl:schema:xsd:{root}-2" '
        'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
        'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">'
        f"<cbc:CustomizationID>{CIUS_RO}</cbc:CustomizationID>"
        f"<cbc:ID>{x(inv['series'])}{inv['number']}</cbc:ID><cbc:IssueDate>{inv['issue_date']}</cbc:IssueDate>{head}"
        f"{_party('AccountingSupplierParty', seller, True)}{_party('AccountingCustomerParty', inv['buyer'], False)}{payment}"
        f"<cac:TaxTotal><cbc:TaxAmount currencyID=\"{cur}\">{a(t['vat']):.2f}</cbc:TaxAmount>{subtotals}</cac:TaxTotal>"
        f"<cac:LegalMonetaryTotal><cbc:LineExtensionAmount currencyID=\"{cur}\">{a(t['net']):.2f}</cbc:LineExtensionAmount>"
        f"<cbc:TaxExclusiveAmount currencyID=\"{cur}\">{a(t['net']):.2f}</cbc:TaxExclusiveAmount>"
        f"<cbc:TaxInclusiveAmount currencyID=\"{cur}\">{a(t['gross']):.2f}</cbc:TaxInclusiveAmount>"
        f"<cbc:PayableAmount currencyID=\"{cur}\">{a(t['gross']):.2f}</cbc:PayableAmount></cac:LegalMonetaryTotal>"
        f"{lines_xml}</{root}>")
