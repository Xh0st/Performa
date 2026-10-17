import io
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Optional
from fastapi import HTTPException
from pydantic import BaseModel
from core import db, ser, oid, iso, now, get_settings
from anaf_service import anaf_request, cif_digits, get_cfg, BASES, download_zip, log
from routes_stock import create_nir, NirIn, NirLine

NS = {"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
      "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"}


def _t(el, path, default=""):
    x = el.find(path, NS) if el is not None else None
    return (x.text or "").strip() if x is not None and x.text else default


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def parse_ubl(xml: str) -> dict:
    try:
        root = ET.fromstring(xml.encode() if isinstance(xml, str) else xml)
    except ET.ParseError as e:
        raise HTTPException(400, f"XML invalid: {e}")
    if not root.tag.endswith("Invoice") and not root.tag.endswith("CreditNote"):
        raise HTTPException(400, "Fișierul nu este o factură UBL")
    sup = root.find("cac:AccountingSupplierParty/cac:Party", NS)
    cui = _t(sup, "cac:PartyTaxScheme/cbc:CompanyID") or _t(sup, "cac:PartyLegalEntity/cbc:CompanyID")
    lines = []
    for ln in root.findall("cac:InvoiceLine", NS) + root.findall("cac:CreditNoteLine", NS):
        qty_el = ln.find("cbc:InvoicedQuantity", NS)
        if qty_el is None:
            qty_el = ln.find("cbc:CreditedQuantity", NS)
        qty = _f(qty_el.text if qty_el is not None else 0)
        net = _f(_t(ln, "cbc:LineExtensionAmount"))
        lines.append({"idx": len(lines), "name": _t(ln, "cac:Item/cbc:Name"),
                      "seller_code": _t(ln, "cac:Item/cac:SellersItemIdentification/cbc:ID"),
                      "unit_code": qty_el.attrib.get("unitCode", "") if qty_el is not None else "", "qty": qty,
                      "price": round(net / qty, 4) if qty else _f(_t(ln, "cac:Price/cbc:PriceAmount")), "net": net,
                      "vat_rate": _f(_t(ln, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent", "21"))})
    tot = root.find("cac:LegalMonetaryTotal", NS)
    return {"supplier_cui": cui, "supplier_cif": cif_digits(cui), "supplier_name": _t(sup, "cac:PartyLegalEntity/cbc:RegistrationName"),
            "supplier_address": _t(sup, "cac:PostalAddress/cbc:StreetName"), "series_number": _t(root, "cbc:ID"),
            "issue_date": _t(root, "cbc:IssueDate"), "due_date": _t(root, "cbc:DueDate"), "currency": _t(root, "cbc:DocumentCurrencyCode", "RON"),
            "lines": lines, "net": _f(_t(tot, "cbc:TaxExclusiveAmount")), "gross": _f(_t(tot, "cbc:TaxInclusiveAmount")),
            "vat": _f(_t(root, "cac:TaxTotal/cbc:TaxAmount"))}


def norm_no(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _xml_from_zip(content: bytes):
    inv_xml, sig = "", ""
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for n in z.namelist():
            data = z.read(n).decode("utf-8", "ignore")
            if n.lower().startswith("semnatura"):
                sig = data
            elif n.lower().endswith(".xml"):
                inv_xml = data
    return inv_xml, sig


async def store_message(meta: dict, xml: str, signature: str = "", source: str = "spv"):
    parsed = parse_ubl(xml)
    doc = {**meta, "source": source, "xml": xml, "signature_xml": signature, "parsed": parsed, "status": "parsed", "received_at": iso()}
    if meta.get("message_id"):
        await db.efactura_inbox.update_one({"message_id": meta["message_id"]}, {"$setOnInsert": doc}, upsert=True)
    else:
        await db.efactura_inbox.insert_one(doc)


async def sync_inbox(days: int = 60) -> dict:
    cfg = await get_cfg()
    if cfg["environment"] not in BASES:
        raise HTTPException(400, "Sincronizarea SPV necesită mediu Test sau Producție conectat. În simulare folosiți „Import XML”.")
    s = await get_settings()
    r = await anaf_request("GET", "/listaMesajeFactura", {"zile": days, "cif": cif_digits(s.get("cui")), "filtru": "P"})
    data = r.json()
    if data.get("eroare"):
        if "Nu exista mesaje" in data["eroare"]:
            return {"new": 0, "total": 0}
        raise HTTPException(502, data["eroare"])
    new = 0
    for m in data.get("mesaje", []):
        if await db.efactura_inbox.find_one({"message_id": m["id"]}, {"_id": 1}):
            continue
        try:
            xml, sig = _xml_from_zip(await download_zip(m["id"]))
            await store_message({"message_id": m["id"], "id_solicitare": m.get("id_solicitare"), "cif_emitent": m.get("cif"),
                                 "data_creare": m.get("data_creare"), "detalii": m.get("detalii")}, xml, sig)
            new += 1
        except HTTPException as e:
            await log("inbox", False, f"mesaj {m['id']}: {e.detail}", env=cfg["environment"])
    await log("inbox", True, f"Sincronizare: {new} facturi noi din {len(data.get('mesaje', []))}", env=cfg["environment"])
    return {"new": new, "total": len(data.get("mesaje", []))}


async def find_supplier(parsed: dict):
    cif = parsed["supplier_cif"]
    async for s in db.suppliers.find():
        if cif and cif_digits(s.get("cui")) == cif:
            return s
    return await db.suppliers.find_one({"name": {"$regex": f"^{re.escape(parsed['supplier_name'])}$", "$options": "i"}}) if parsed["supplier_name"] else None


async def find_duplicate_nir(parsed: dict, supplier):
    if not supplier:
        return None
    target = norm_no(parsed["series_number"])
    async for n in db.nirs.find({"supplier_id": str(supplier["_id"])}):
        no = norm_no(n.get("invoice_no"))
        if no and (no == target or (len(no) >= 3 and target.endswith(no)) or (len(target) >= 3 and no.endswith(target))):
            return n
    return None


async def suggest_products(parsed: dict):
    out = {}
    for ln in parsed["lines"]:
        key = ln["seller_code"] or ln["name"]
        mp = await db.product_mappings.find_one({"supplier_cif": parsed["supplier_cif"], "key": key})
        pid = mp["product_id"] if mp else None
        if not pid and ln["seller_code"]:
            code = ln["seller_code"]
            p = await db.products.find_one({"$or": [{"code": code}, {"oe_code": code}, {"aftermarket_code": code}]})
            pid = str(p["_id"]) if p else None
        out[ln["idx"]] = pid
    return out


async def inbox_detail(mid: str) -> dict:
    m = await db.efactura_inbox.find_one({"_id": oid(mid)}, {"signature_xml": 0})
    if not m:
        raise HTTPException(404, "Mesaj inexistent")
    d = ser(m)
    d.pop("xml", None)
    sup = await find_supplier(m["parsed"])
    dup = await find_duplicate_nir(m["parsed"], sup)
    d["supplier"] = ser(sup) if sup else None
    d["duplicate_nir"] = ser(dup) if dup and str(dup["_id"]) != m.get("nir_id") else None
    d["suggestions"] = await suggest_products(m["parsed"])
    return d


class MapLine(BaseModel):
    idx: int
    product_id: Optional[str] = None
    create: bool = False
    skip: bool = False


class MapIn(BaseModel):
    mappings: List[MapLine]
    force: bool = False


async def _resolve(m: dict, body: MapIn):
    parsed = m["parsed"]
    sup = await find_supplier(parsed)
    if not sup:
        r = await db.suppliers.insert_one({"name": parsed["supplier_name"] or parsed["supplier_cui"], "cui": parsed["supplier_cui"],
                                           "address": parsed.get("supplier_address", ""), "api_enabled": False, "created_at": iso()})
        sup = await db.suppliers.find_one({"_id": r.inserted_id})
    resolved = []
    by_idx = {x.idx: x for x in body.mappings}
    for ln in parsed["lines"]:
        mp = by_idx.get(ln["idx"])
        if not mp or mp.skip:
            continue
        pid = mp.product_id
        if mp.create or not pid:
            code = ln["seller_code"] or f"EF-{now().strftime('%y%m%d')}-{ln['idx'] + 1}-{str(m['_id'])[-4:]}"
            exist = await db.products.find_one({"code": code})
            if exist:
                pid = str(exist["_id"])
            else:
                r = await db.products.insert_one({"code": code, "name": ln["name"][:120], "oe_code": "", "aftermarket_code": ln["seller_code"],
                                                  "brand": "", "category": "piese", "unit": "buc", "location": "", "warehouse": "Depozit Central",
                                                  "sale_price": round(ln["price"] * 1.35, 2), "min_stock": 0, "vat_rate": ln["vat_rate"],
                                                  "warranty_months": 24, "stock_qty": 0, "avg_cost": 0, "created_at": iso()})
                pid = str(r.inserted_id)
        await db.product_mappings.update_one({"supplier_cif": parsed["supplier_cif"], "key": ln["seller_code"] or ln["name"]},
                                             {"$set": {"product_id": pid, "at": iso()}}, upsert=True)
        resolved.append((ln, pid))
    if not resolved:
        raise HTTPException(400, "Nicio linie mapată")
    return sup, resolved


async def create_nir_from_message(mid: str, body: MapIn, user: dict):
    m = await db.efactura_inbox.find_one({"_id": oid(mid)})
    if not m:
        raise HTTPException(404, "Mesaj inexistent")
    if m.get("nir_id"):
        raise HTTPException(400, "Factura are deja NIR asociat")
    dup = await find_duplicate_nir(m["parsed"], await find_supplier(m["parsed"]))
    if dup and not body.force:
        raise HTTPException(409, f"Factură găsită în sistem! NIR {dup['number']} – folosiți Overwrite / Link cu e-Factura")
    sup, resolved = await _resolve(m, body)
    p = m["parsed"]
    nir = await create_nir(NirIn(supplier_id=str(sup["_id"]), invoice_no=p["series_number"], date=f"{p['issue_date']}T12:00:00+00:00" if p["issue_date"] else "",
                                 lines=[NirLine(product_id=pid, qty=ln["qty"], unit_cost=ln["price"]) for ln, pid in resolved]), user)
    await db.nirs.update_one({"_id": oid(nir["id"])}, {"$set": {"source": "efactura", "efactura_message_id": str(m["_id"]), "efactura_linked": True,
                                                                 "supplier_cui": p["supplier_cui"]}})
    await db.efactura_inbox.update_one({"_id": m["_id"]}, {"$set": {"status": "nir_created", "nir_id": nir["id"], "nir_number": nir["number"]}})
    return nir


async def link_overwrite(mid: str, nir_id: str, body: MapIn, user: dict):
    m = await db.efactura_inbox.find_one({"_id": oid(mid)})
    nir = await db.nirs.find_one({"_id": oid(nir_id)})
    if not m or not nir:
        raise HTTPException(404, "Mesaj sau NIR inexistent")
    if nir.get("efactura_linked") and nir.get("efactura_message_id") != mid:
        raise HTTPException(400, "NIR-ul este deja legat de altă factură e-Factura")
    _, resolved = await _resolve(m, body)
    old = {ln["product_id"]: ln for ln in nir["lines"]}
    new_lines, changes = [], []
    for ln, pid in resolved:
        p = await db.products.find_one({"_id": oid(pid)})
        prev = old.pop(pid, None)
        qty, cost = ln["qty"], ln["price"]
        if prev:
            delta = round(qty - prev["qty"], 4)
            stock, avg = p.get("stock_qty", 0), p.get("avg_cost", 0)
            new_stock = stock + delta
            new_avg = round((stock * avg - prev["qty"] * prev["unit_cost"] + qty * cost) / new_stock, 4) if new_stock > 0 else cost
            await db.products.update_one({"_id": p["_id"]}, {"$inc": {"stock_qty": delta}, "$set": {"avg_cost": new_avg, "last_cost": cost}})
            await db.stock_lots.update_one({"product_id": pid, "ref": nir["number"]},
                                           {"$inc": {"qty_remaining": delta}, "$set": {"qty_in": qty, "unit_cost": cost}})
            await db.stock_moves.update_one({"product_id": pid, "ref": nir["number"], "kind": "in"}, {"$set": {"qty": qty, "unit_cost": cost}})
            if delta or abs(cost - prev["unit_cost"]) > 0.0001:
                changes.append(f"{p['code']}: {prev['qty']}→{qty} buc, {prev['unit_cost']}→{cost} RON")
        else:
            from routes_stock import receive_stock
            await receive_stock(pid, qty, cost, nir["number"], nir["date"])
            changes.append(f"{p['code']}: linie nouă {qty} buc")
        val = round(qty * cost, 2)
        new_lines.append({"product_id": pid, "code": p["code"], "name": p["name"], "unit": p.get("unit", "buc"), "qty": qty, "unit_cost": cost,
                          "value": val, "vat": round(val * ln["vat_rate"] / 100, 2), "lot": "", "efactura_name": ln["name"]})
    kept = list(old.values())
    total = round(sum(x["value"] for x in new_lines + kept), 2)
    p = m["parsed"]
    await db.nirs.update_one({"_id": nir["_id"]}, {"$set": {
        "lines": new_lines + kept, "total": total, "total_vat": round(sum(x["vat"] for x in new_lines + kept), 2), "invoice_no": p["series_number"],
        "efactura_linked": True, "efactura_message_id": mid, "supplier_cui": p["supplier_cui"], "updated_from_efactura_at": iso(),
        "updated_by": user["name"], "unmatched_lines": [x["code"] for x in kept]}})
    await db.efactura_inbox.update_one({"_id": m["_id"]}, {"$set": {"status": "linked", "nir_id": nir_id, "nir_number": nir["number"], "changes": changes}})
    return {"nir_id": nir_id, "number": nir["number"], "changes": changes, "unmatched_nir_lines": [x["code"] for x in kept]}
