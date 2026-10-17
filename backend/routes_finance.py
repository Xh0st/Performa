import random
from datetime import timedelta, date
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from core import db, ser, oid, iso, now, require, audit, get_or_404, next_seq, get_settings, calc_totals
from routes_stock import consume_fifo
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
        from routes_efactura import schedule_auto_send
        schedule_auto_send(await db.invoices.find_one({"_id": r.inserted_id}))
    return ser(await db.invoices.find_one({"_id": r.inserted_id}, {"efactura.xml": 0}))


@router.get("/invoices/{iid}")
async def get_invoice(iid: str, user=Depends(require("invoices"))):
    inv = ser(await get_or_404("invoices", iid))
    inv.get("efactura", {}).pop("xml", None)
    inv["efactura"]["has_receipt"] = bool(await db.efactura_files.find_one({"invoice_id": iid}, {"_id": 1}))
    inv["payments"] = [ser(p) for p in await db.payments.find({"invoice_id": iid}).sort("date", 1).to_list(200)]
    return inv


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
    if inv["type"] != "fiscal":
        raise HTTPException(400, "Încasările se înregistrează pe facturi fiscale")
    due = round(inv["totals"]["gross"] - inv.get("paid_amount", 0), 2)
    if body.amount <= 0 or body.amount > due + 0.001:
        raise HTTPException(400, f"Suma trebuie să fie între 0 și {due:.2f} RON")
    paid = round(inv.get("paid_amount", 0) + body.amount, 2)
    status = "paid" if paid >= inv["totals"]["gross"] - 0.001 else "partial"
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
