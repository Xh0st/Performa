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


def build_ubl(inv: dict) -> str:
    """UBL 2.1 Invoice conform CIUS-RO (RO e-Factura)."""
    cur = inv.get("currency", "RON")
    t = inv["totals"]
    groups = {}
    for ln in inv["lines"]:
        g = groups.setdefault(float(ln.get("vat_rate", 21)), [0.0, 0.0])
        g[0] += ln["net"]
        g[1] += ln["vat"]
    subtotals = "".join(
        f"<cac:TaxSubtotal><cbc:TaxableAmount currencyID=\"{cur}\">{n:.2f}</cbc:TaxableAmount><cbc:TaxAmount currencyID=\"{cur}\">{v:.2f}</cbc:TaxAmount>"
        f"<cac:TaxCategory><cbc:ID>{'S' if rate else 'Z'}</cbc:ID><cbc:Percent>{rate:.2f}</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>"
        f"</cac:TaxCategory></cac:TaxSubtotal>" for rate, (n, v) in sorted(groups.items()))
    lines_xml = ""
    for i, ln in enumerate(inv["lines"], 1):
        unit = "HUR" if ln["type"] == "labor" else "H87"
        price = round(ln["net"] / ln["qty"], 4) if ln["qty"] else 0
        lines_xml += (
            f"<cac:InvoiceLine><cbc:ID>{i}</cbc:ID><cbc:InvoicedQuantity unitCode=\"{unit}\">{ln['qty']:.2f}</cbc:InvoicedQuantity>"
            f"<cbc:LineExtensionAmount currencyID=\"{cur}\">{ln['net']:.2f}</cbc:LineExtensionAmount>"
            f"<cac:Item><cbc:Name>{x(ln['description'][:100])}</cbc:Name>"
            + (f"<cac:SellersItemIdentification><cbc:ID>{x(ln['code'])}</cbc:ID></cac:SellersItemIdentification>" if ln.get("code") else "")
            + f"<cac:ClassifiedTaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>{ln.get('vat_rate', 21):.2f}</cbc:Percent>"
            f"<cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:ClassifiedTaxCategory></cac:Item>"
            f"<cac:Price><cbc:PriceAmount currencyID=\"{cur}\">{price:.4f}</cbc:PriceAmount></cac:Price></cac:InvoiceLine>")
    seller = inv["seller"]
    payment = ""
    if seller.get("iban"):
        payment = (f"<cac:PaymentMeans><cbc:PaymentMeansCode>31</cbc:PaymentMeansCode><cac:PayeeFinancialAccount>"
                   f"<cbc:ID>{x(seller['iban'])}</cbc:ID><cbc:Name>{x(seller.get('bank', ''))}</cbc:Name></cac:PayeeFinancialAccount></cac:PaymentMeans>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
        'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
        'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">'
        f"<cbc:CustomizationID>{CIUS_RO}</cbc:CustomizationID>"
        f"<cbc:ID>{x(inv['series'])}{inv['number']}</cbc:ID><cbc:IssueDate>{inv['issue_date']}</cbc:IssueDate>"
        f"<cbc:DueDate>{inv['due_date']}</cbc:DueDate><cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>"
        f"<cbc:Note>Comanda de lucru {x(inv.get('work_order_number', ''))}</cbc:Note>"
        f"<cbc:DocumentCurrencyCode>{cur}</cbc:DocumentCurrencyCode>"
        f"{_party('AccountingSupplierParty', seller, True)}{_party('AccountingCustomerParty', inv['buyer'], False)}{payment}"
        f"<cac:TaxTotal><cbc:TaxAmount currencyID=\"{cur}\">{t['vat']:.2f}</cbc:TaxAmount>{subtotals}</cac:TaxTotal>"
        f"<cac:LegalMonetaryTotal><cbc:LineExtensionAmount currencyID=\"{cur}\">{t['net']:.2f}</cbc:LineExtensionAmount>"
        f"<cbc:TaxExclusiveAmount currencyID=\"{cur}\">{t['net']:.2f}</cbc:TaxExclusiveAmount>"
        f"<cbc:TaxInclusiveAmount currencyID=\"{cur}\">{t['gross']:.2f}</cbc:TaxInclusiveAmount>"
        f"<cbc:PayableAmount currencyID=\"{cur}\">{t['gross']:.2f}</cbc:PayableAmount></cac:LegalMonetaryTotal>"
        f"{lines_xml}</Invoice>")
