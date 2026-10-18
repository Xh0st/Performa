import uuid
from datetime import timedelta, date
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from core import db, ser, oid, iso, now, require, audit, get_or_404, next_seq, get_settings, calc_totals
from routes_stock import consume_fifo, receive_stock
from efactura import build_ubl

router = APIRouter(prefix="/api")
DOC_BY_METHOD = {"numerar": ("chitanta", "CH"), "pos": ("bon_pos", "POS"), "transfer": ("ordin_plata", "OP"), "online": ("confirmare_online", "WEB")}


class InvoiceIn(BaseModel):
    type: str = "fiscal"


@router.get("/invoices")
async def list_invoices(status: str = "", type: str = "", user=Depends(require("invoices"))):
    flt = {}
    if status:
        flt["status"] = status
    if type:
        flt["type"] = type
    return [ser(i) for i in await db.invoices.find(flt, {"efactura.xml": 0}).sort("created_at", -1).to_list(2000)]


@router.post("/invoices/from-work-order/{wid}")
async def invoice_from_wo(wid: str, body: InvoiceIn, user=Depends(require("invoices"))):
    w = await get_or_404("work_orders", wid)
    if not w.get("lines"):
        raise HTTPException(400, "Comanda nu are linii de facturat")
    if body.type == "fiscal":
        if w["status"] != "finalizata":
            raise HTTPException(400, "Doar comenzile finalizate (după control calitate) pot fi facturate fiscal")
        if w.get("invoice_id"):
            raise HTTPException(400, "Comanda este deja facturată")
    s = await get_settings()
    c = await get_or_404("clients", w["client_id"])
    v = await get_or_404("vehicles", w["vehicle_id"])
    lines = [dict(ln) for ln in w["lines"]]
    totals = calc_totals(lines)
    key = "invoice" if body.type == "fiscal" else "proforma"
    seq = await next_seq(key)
    issue = date.today()
    inv = {"type": body.type, "series": s.get("invoice_series", "SRV") if body.type == "fiscal" else s.get("proforma_series", "PF"),
           "number": f"{seq:06d}", "issue_date": issue.isoformat(),
           "due_date": (issue + timedelta(days=s.get("payment_terms_days", 15))).isoformat(),
           "currency": "RON", "work_order_id": wid, "work_order_number": w["number"], "client_id": w["client_id"],
           "vehicle": f"{v['make']} {v['model']} · {v['plate']} · VIN {v['vin']}", "mileage": w.get("mileage_in"),
           "seller": {k: s.get(k, "") for k in ("name", "cui", "reg_com", "address", "city", "county_code", "iban", "bank", "phone", "email", "capital")},
           "buyer": {"name": c["name"], "cui": c.get("cui", ""), "cnp": c.get("cnp", ""), "reg_com": c.get("reg_com", ""),
                     "address": c.get("address", ""), "city": c.get("city", ""), "county_code": c.get("county", ""),
                     "phone": c.get("phone", ""), "email": c.get("email", "")},
           "lines": lines, "totals": totals, "paid_amount": 0.0, "status": "unpaid", "cogs": 0.0,
           "efactura": {"status": "not_sent", "history": []}, "created_by": user["name"], "created_at": iso()}
    if body.type == "fiscal":
        ref = f"{inv['series']}{inv['number']}"
        for ln in lines:
            if ln["type"] in ("part", "consumable") and ln.get("product_id"):
                inv["cogs"] += await consume_fifo(ln["product_id"], ln["qty"], ref)
        inv["cogs"] = round(inv["cogs"], 2)
    r = await db.invoices.insert_one(inv)
    if body.type == "fiscal":
        await db.work_orders.update_one({"_id": w["_id"]}, {"$set": {"status": "facturata", "invoice_id": str(r.inserted_id), "invoiced_at": iso()},
                                                            "$push": {"status_history": {"status": "facturata", "at": iso(), "by": user["name"], "note": f"Factura {inv['series']}{inv['number']}"}}})
    await audit(user, "create", "invoice", str(r.inserted_id), f"{inv['series']}{inv['number']}")
    if body.type == "fiscal":
        from rar_autopass import queue_submission_safely
        from routes_efactura import schedule_auto_send

        rar_work_order = await db.work_orders.find_one({"_id": w["_id"]})
        rar_invoice = await db.invoices.find_one({"_id": r.inserted_id})
        await queue_submission_safely(rar_work_order, rar_invoice, "invoice_issued")
        schedule_auto_send(await db.invoices.find_one({"_id": r.inserted_id}))
    return ser(await db.invoices.find_one({"_id": r.inserted_id}, {"efactura.xml": 0}))


@router.get("/invoices/{iid}")
async def get_invoice(iid: str, user=Depends(require("invoices"))):
    inv = ser(await get_or_404("invoices", iid))
    inv.get("efactura", {}).pop("xml", None)
    inv["efactura"]["has_receipt"] = bool(await db.efactura_files.find_one({"invoice_id": iid}, {"_id": 1}))
    inv["payments"] = [ser(p) for p in await db.payments.find({"invoice_id": iid}).sort("date", 1).to_list(200)]
    if inv.get("kind") != "credit_note":
        credited = await credited_by_line(iid)
        for ln in inv["lines"]:
            ln["credited_qty"] = credited.get(ln.get("id"), 0)
    return inv


async def credited_by_line(iid: str) -> dict:
    out = {}
    async for cn in db.invoices.find({"original_invoice_id": iid}, {"lines": 1}):
        for ln in cn["lines"]:
            out[ln["original_line_id"]] = round(out.get(ln["original_line_id"], 0) + abs(ln["qty"]), 4)
    return out


class StornoLine(BaseModel):
    line_id: str
    qty: float


class StornoIn(BaseModel):
    reason: str = ""
    restock: bool = False
    lines: List[StornoLine]


async def _sold_cost(product_id: str, ref: str) -> float:
    mv = await db.stock_moves.find_one({"product_id": product_id, "ref": ref, "kind": "out"})
    if mv:
        return mv["unit_cost"]
    p = await db.products.find_one({"_id": oid(product_id)}, {"avg_cost": 1})
    return p.get("avg_cost", 0) if p else 0


@router.post("/invoices/{iid}/storno")
async def storno_invoice(iid: str, body: StornoIn, user=Depends(require("invoices"))):
    inv = await get_or_404("invoices", iid)
    if inv["type"] != "fiscal" or inv.get("kind") == "credit_note":
        raise HTTPException(400, "Doar facturile fiscale pot fi stornate")
    if not body.reason.strip():
        raise HTTPException(400, "Motivul stornării este obligatoriu")
    credited = await credited_by_line(iid)
    orig = {ln.get("id"): ln for ln in inv["lines"]}
    lines = []
    for sl in body.lines:
        if sl.qty <= 0:
            continue
        ln = orig.get(sl.line_id)
        if not ln:
            raise HTTPException(400, "Linie inexistentă pe factura originală")
        avail = round(ln["qty"] - credited.get(sl.line_id, 0), 4)
        if sl.qty > avail + 1e-6:
            raise HTTPException(400, f"{ln['description']}: cantitate maximă stornabilă {avail}")
        lines.append({**ln, "id": str(uuid.uuid4()), "original_line_id": sl.line_id, "qty": -sl.qty})
    if not lines:
        raise HTTPException(400, "Selectați cel puțin o linie de stornat")
    totals = calc_totals(lines)
    seq = await next_seq("invoice")
    orig_ref = f"{inv['series']}{inv['number']}"
    today = date.today().isoformat()
    cn = {"type": "fiscal", "kind": "credit_note", "series": inv["series"], "number": f"{seq:06d}", "issue_date": today, "due_date": today,
          "currency": inv.get("currency", "RON"), "work_order_id": inv.get("work_order_id"), "work_order_number": inv.get("work_order_number"),
          "client_id": inv.get("client_id"), "vehicle": inv.get("vehicle"), "mileage": inv.get("mileage"), "seller": inv["seller"], "buyer": inv["buyer"],
          "lines": lines, "totals": totals, "paid_amount": 0.0, "status": "credit", "cogs": 0.0, "original_invoice_id": iid,
          "original_ref": orig_ref, "original_issue_date": inv["issue_date"], "storno_reason": body.reason.strip(), "restocked": body.restock,
          "efactura": {"status": "not_sent", "history": []}, "created_by": user["name"], "created_at": iso()}
    r = await db.invoices.insert_one(cn)
    ref = f"{cn['series']}{cn['number']}"
    cogs = 0.0
    if body.restock:
        for ln in lines:
            if ln["type"] in ("part", "consumable") and ln.get("product_id"):
                cost = await _sold_cost(ln["product_id"], orig_ref)
                await receive_stock(ln["product_id"], abs(ln["qty"]), cost, ref, iso(), f"RETUR {orig_ref}")
                cogs -= abs(ln["qty"]) * cost
        await db.invoices.update_one({"_id": r.inserted_id}, {"$set": {"cogs": round(cogs, 2)}})
    for ln in lines:
        credited[ln["original_line_id"]] = credited.get(ln["original_line_id"], 0) + abs(ln["qty"])
    full = all(credited.get(ln.get("id"), 0) >= ln["qty"] - 1e-6 for ln in inv["lines"])
    credited_amount = round(inv.get("credited_amount", 0) + abs(totals["gross"]), 2)
    settled = inv.get("paid_amount", 0) + credited_amount >= inv["totals"]["gross"] - 0.001
    await db.invoices.update_one({"_id": inv["_id"]}, {"$set": {"credited_amount": credited_amount, "storno_status": "total" if full else "partial",
                                                                  "status": "paid" if settled else inv["status"]},
                                                         "$push": {"credit_notes": {"id": str(r.inserted_id), "ref": ref, "gross": totals["gross"], "at": iso()}}})
    await audit(user, "storno", "invoice", iid, f"{ref} storno {orig_ref}")
    from routes_efactura import schedule_auto_send
    schedule_auto_send(await db.invoices.find_one({"_id": r.inserted_id}))
    return ser(await db.invoices.find_one({"_id": r.inserted_id}, {"efactura.xml": 0}))


@router.get("/invoices/{iid}/efactura/xml")
async def efactura_xml(iid: str, user=Depends(require("invoices"))):
    inv = await get_or_404("invoices", iid)
    if inv["type"] != "fiscal":
        raise HTTPException(400, "e-Factura se generează doar pentru facturi fiscale")
    xml = build_ubl(inv)
    if inv["efactura"]["status"] == "not_sent":
        await db.invoices.update_one({"_id": inv["_id"]}, {"$set": {"efactura.status": "generated"}, "$push": {"efactura.history": {"event": "XML generat", "at": iso()}}})
    return Response(content=xml, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="efactura_{inv["series"]}{inv["number"]}.xml"'})


class PaymentIn(BaseModel):
    invoice_id: str
    amount: float
    method: str
    reference: str = ""


@router.post("/payments")
async def create_payment(body: PaymentIn, user=Depends(require("payments"))):
    if body.method not in DOC_BY_METHOD:
        raise HTTPException(400, "Metodă de plată invalidă")
    inv = await get_or_404("invoices", body.invoice_id)
    if inv["type"] != "fiscal" or inv.get("kind") == "credit_note":
        raise HTTPException(400, "Încasările se înregistrează pe facturi fiscale (nu pe facturi de stornare)")
    due = round(inv["totals"]["gross"] - inv.get("paid_amount", 0) - inv.get("credited_amount", 0), 2)
    if body.amount <= 0 or body.amount > due + 0.001:
        raise HTTPException(400, f"Suma trebuie să fie între 0 și {due:.2f} RON")
    paid = round(inv.get("paid_amount", 0) + body.amount, 2)
    status = "paid" if paid + inv.get("credited_amount", 0) >= inv["totals"]["gross"] - 0.001 else "partial"
    upd = await db.invoices.update_one({"_id": inv["_id"], "paid_amount": inv.get("paid_amount", 0)},
                                       {"$set": {"paid_amount": paid, "status": status}})
    if upd.modified_count == 0:
        raise HTTPException(409, "Factura a fost modificată între timp. Reîncercați.")
    doc_type, prefix = DOC_BY_METHOD[body.method]
    seq = await next_seq(f"pay_{doc_type}")
    p = {"invoice_id": body.invoice_id, "invoice_ref": f"{inv['series']}{inv['number']}", "client_name": inv["buyer"]["name"],
         "amount": round(body.amount, 2), "method": body.method, "doc_type": doc_type, "doc_number": f"{prefix}-{seq:06d}",
         "reference": body.reference, "date": iso(), "cashier": user["name"]}
    r = await db.payments.insert_one(p)
    await audit(user, "create", "payment", str(r.inserted_id), p["doc_number"])
    return ser(await db.payments.find_one({"_id": r.inserted_id}))


@router.get("/payments")
async def list_payments(day: str = "", user=Depends(require("payments"))):
    flt = {"date": {"$regex": f"^{day}"}} if day else {}
    return [ser(p) for p in await db.payments.find(flt).sort("date", -1).to_list(2000)]


@router.get("/payments/{pid}")
async def get_payment(pid: str, user=Depends(require("invoices"))):
    return ser(await get_or_404("payments", pid))


@router.get("/cash-register")
async def cash_register(day: str = "", user=Depends(require("payments"))):
    day = day or now().date().isoformat()
    before = await db.payments.aggregate([{"$match": {"method": "numerar", "date": {"$lt": day}}},
                                          {"$group": {"_id": None, "s": {"$sum": "$amount"}}}]).to_list(1)
    opening = round(before[0]["s"], 2) if before else 0.0
    entries = [ser(p) for p in await db.payments.find({"method": "numerar", "date": {"$regex": f"^{day}"}}).sort("date", 1).to_list(1000)]
    total_in = round(sum(e["amount"] for e in entries), 2)
    return {"day": day, "opening": opening, "entries": entries, "total_in": total_in, "total_out": 0, "closing": round(opening + total_in, 2)}
