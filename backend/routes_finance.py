import uuid
import re
import io
from datetime import timedelta, date
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from fastapi.responses import Response
from pydantic import BaseModel
from core import db, ser, oid, iso, now, require, audit, get_or_404, next_seq, get_settings, calc_totals
from routes_stock import consume_fifo, receive_stock
from efactura import build_ubl
from pagination import fetch_page, page_response
from client_finance import client_credit_position

router = APIRouter(prefix="/api")
DOC_BY_METHOD = {
    "pos": ("bon_pos", "POS"),
    "transfer": ("ordin_plata", "OP"),
    "online": ("confirmare_online", "WEB"),
}
CASH_DOCUMENTS = {
    "receipt": ("chitanta", "CH"),
    "fiscal_receipt": ("bon_fiscal", "BF"),
    "collection_order": ("dispozitie_incasare", "DI"),
}


class InvoiceIn(BaseModel):
    type: str = "fiscal"


@router.get("/invoices")
async def list_invoices(
    status: str = "",
    type: str = "",
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 0,
    page_size: int = 20,
    user=Depends(require("invoices")),
):
    flt = {}
    if status:
        flt["status"] = status
    if type:
        flt["type"] = type
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        flt["$or"] = [
            {"series": rx},
            {"number": rx},
            {"buyer.name": rx},
            {"buyer.cui": rx},
            {"vehicle": rx},
            {"work_order_number": rx},
        ]
    if date_from or date_to:
        flt["issue_date"] = {}
        if date_from:
            flt["issue_date"]["$gte"] = date_from
        if date_to:
            flt["issue_date"]["$lte"] = date_to
    projection = {"efactura.xml": 0}
    if not page:
        rows = await db.invoices.find(flt, projection).sort("created_at", -1).to_list(2000)
        return [ser(item) for item in rows]
    rows, total, current_page, size = await fetch_page(
        db.invoices,
        flt,
        [("created_at", -1)],
        page,
        page_size,
        projection,
    )
    summary = await db.invoices.aggregate([
        {"$match": flt},
        {"$group": {"_id": None, "gross": {"$sum": "$totals.gross"}}},
    ]).to_list(1)
    return page_response(
        [ser(item) for item in rows],
        total,
        current_page,
        size,
        summary={"gross": round((summary[0] if summary else {}).get("gross", 0), 2)},
    )


@router.post("/invoices/from-work-order/{wid}")
async def invoice_from_wo(wid: str, body: InvoiceIn, user=Depends(require("invoices"))):
    w = await get_or_404("work_orders", wid)
    if not w.get("lines"):
        raise HTTPException(400, "Comanda nu are linii de facturat")
    if body.type == "fiscal":
        from routes_service import quote_closure_rule

        if w["status"] != "finalizata":
            raise HTTPException(400, "Doar comenzile finalizate (după control calitate) pot fi facturate fiscal")
        if w.get("is_warranty"):
            raise HTTPException(400, "Comenzile de garanție nu se facturează clientului")
        if not w.get("qc", {}).get("passed"):
            raise HTTPException(400, "Controlul calității final trebuie promovat înainte de facturare")
        if not any(quote.get("status") == "approved" for quote in w.get("quotes", [])):
            raise HTTPException(400, "Factura fiscală necesită un deviz emis și aprobat")
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
    payment_terms_days = c.get("payment_terms_days") if c.get("type") == "pj" else None
    payment_terms_days = payment_terms_days if payment_terms_days and payment_terms_days > 0 else 0
    inv = {"type": body.type, "series": s.get("invoice_series", "SRV") if body.type == "fiscal" else s.get("proforma_series", "PF"),
           "number": f"{seq:06d}", "issue_date": issue.isoformat(),
           "due_date": (issue + timedelta(days=payment_terms_days)).isoformat(),
           "payment_terms_days": payment_terms_days,
           "payment_condition": "CASH" if not payment_terms_days else f"{payment_terms_days} zile",
           "currency": "RON", "work_order_id": wid, "work_order_number": w["number"], "client_id": w["client_id"],
           "vehicle": f"{v['make']} {v['model']} · {v['plate']} · VIN {v['vin']}", "mileage": w.get("mileage_in"),
           "seller": {k: s.get(k, "") for k in ("name", "cui", "reg_com", "address", "city", "county_code", "iban", "bank", "phone", "email", "capital", "subscription_plan", "custom_logo_data_url")},
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
    credit_warning = None
    if body.type == "fiscal" and c.get("type") == "pj":
        position = await client_credit_position(w["client_id"])
        projected = round(position["outstanding"] + totals["gross"], 2)
        credit_limit = float(c.get("credit_limit") or 0)
        if projected > credit_limit:
            credit_warning = {
                "limit": credit_limit,
                "outstanding": position["outstanding"],
                "projected": projected,
            }
    r = await db.invoices.insert_one(inv)
    if body.type == "fiscal":
        await db.work_orders.update_one({"_id": w["_id"]}, {"$set": {"status": "facturata", "invoice_id": str(r.inserted_id), "invoiced_at": iso()},
                                                            "$push": {"status_history": {"status": "facturata", "at": iso(), "by": user["name"], "note": f"Factura {inv['series']}{inv['number']}"}}})
    await audit(user, "create", "invoice", str(r.inserted_id), f"{inv['series']}{inv['number']}")
    if body.type == "fiscal":
        from rar_autopass import queue_submission_safely
        from routes_efactura import schedule_auto_send
        from warranty_service import create_certificate

        rar_work_order = await db.work_orders.find_one({"_id": w["_id"]})
        rar_invoice = await db.invoices.find_one({"_id": r.inserted_id})
        await queue_submission_safely(rar_work_order, rar_invoice, "invoice_issued")
        try:
            await create_certificate(rar_invoice, w, s)
        except Exception as exc:  # noqa: BLE001
            await db.warranty_logs.insert_one({
                "invoice_id": str(r.inserted_id),
                "event": "certificate_error",
                "message": str(exc)[:1500],
                "at": iso(),
            })
        schedule_auto_send(await db.invoices.find_one({"_id": r.inserted_id}))
    result = ser(await db.invoices.find_one({"_id": r.inserted_id}, {"efactura.xml": 0}))
    if credit_warning:
        result["credit_warning"] = credit_warning
    return result


@router.get("/invoices/{iid}")
async def get_invoice(iid: str, user=Depends(require("invoices"))):
    inv = ser(await get_or_404("invoices", iid))
    settings = await get_settings()
    inv.setdefault("seller", {})
    inv["seller"]["subscription_plan"] = settings.get("subscription_plan", "BASIC")
    if settings.get("subscription_plan") != "BASIC":
        inv["seller"]["custom_logo_data_url"] = settings.get("custom_logo_data_url", "")
    else:
        inv["seller"].pop("custom_logo_data_url", None)
    inv.setdefault("efactura", {}).pop("xml", None)
    inv["efactura"]["has_receipt"] = bool(await db.efactura_files.find_one({"invoice_id": iid}, {"_id": 1}))
    payment_docs = await db.payments.find(
        {"$or": [{"invoice_id": iid}, {"allocations.invoice_id": iid}]},
    ).sort("date", 1).to_list(200)
    inv["payments"] = []
    for payment in payment_docs:
        item = ser(payment)
        allocation = next(
            (entry for entry in payment.get("allocations", []) if entry.get("invoice_id") == iid),
            None,
        )
        if allocation:
            item["amount"] = allocation["amount"]
        inv["payments"].append(item)
    if inv.get("kind") != "credit_note":
        credited = await credited_by_line(iid)
        for ln in inv["lines"]:
            ln["credited_qty"] = credited.get(ln.get("id"), 0)
    certificate = await db.warranty_certificates.find_one(
        {"invoice_id": iid},
        {"number": 1, "issued_date": 1},
    )
    inv["warranty_certificate"] = ser(certificate) if certificate else None
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
    certificate = await db.warranty_certificates.find_one({"invoice_id": iid})
    if certificate:
        credited_lines = {line["original_line_id"]: abs(line["qty"]) for line in lines}
        for coverage in certificate.get("lines", []):
            if coverage["source_line_id"] in credited_lines:
                coverage["qty"] = max(0, coverage["qty"] - credited_lines[coverage["source_line_id"]])
                coverage["credited_qty"] = coverage.get("credited_qty", 0) + credited_lines[coverage["source_line_id"]]
                if coverage["qty"] <= 0:
                    coverage["valid_to"] = "1900-01-01"
        await db.warranty_certificates.update_one({"_id": certificate["_id"]}, {"$set": {"lines": certificate["lines"]}})
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
    invoice_id: str = ""
    client_id: str = ""
    amount: float
    method: str
    cash_document: str = "receipt"
    reference: str = ""


class CashDepositIn(BaseModel):
    amount: float
    reference: str = ""
    notes: str = ""


class CashPayoutIn(BaseModel):
    kind: str
    beneficiary: str
    amount: float
    reference: str = ""
    notes: str = ""


class CashReversalIn(BaseModel):
    reason: str


def invoice_due(invoice: dict) -> float:
    return round(
        invoice["totals"]["gross"]
        - invoice.get("paid_amount", 0)
        - invoice.get("credited_amount", 0),
        2,
    )


async def payment_plan(client_id: str, amount: float, invoice_id: str = "") -> list[dict]:
    if invoice_id:
        invoices = [await get_or_404("invoices", invoice_id)]
    else:
        invoices = await db.invoices.find(
            {"client_id": client_id, "type": "fiscal", "kind": {"$ne": "credit_note"}},
        ).sort([("due_date", 1), ("issue_date", 1), ("created_at", 1)]).to_list(5000)
    remaining = round(amount, 2)
    allocations = []
    for invoice in invoices:
        due = invoice_due(invoice)
        if due <= 0:
            continue
        applied = round(min(remaining, due), 2)
        paid = round(invoice.get("paid_amount", 0) + applied, 2)
        status = "paid" if paid + invoice.get("credited_amount", 0) >= invoice["totals"]["gross"] - 0.001 else "partial"
        allocations.append({
            "invoice_id": str(invoice["_id"]),
            "invoice_ref": f"{invoice['series']}{invoice['number']}",
            "amount": applied,
            "previous_paid": invoice.get("paid_amount", 0),
            "previous_status": invoice.get("status", "unpaid"),
            "paid": paid,
            "status": status,
        })
        remaining = round(remaining - applied, 2)
        if remaining <= 0:
            break
    if remaining > 0:
        raise HTTPException(400, "Suma depășește soldul facturilor fiscale restante")
    return allocations


async def apply_payment_plan(allocations: list[dict]):
    applied = []
    try:
        for allocation in allocations:
            updated = await db.invoices.update_one(
                {"_id": oid(allocation["invoice_id"]), "paid_amount": allocation["previous_paid"]},
                {"$set": {"paid_amount": allocation["paid"], "status": allocation["status"]}},
            )
            if updated.modified_count == 0:
                raise HTTPException(409, "Factura a fost modificată între timp. Reîncercați.")
            applied.append(allocation)
    except Exception:
        for allocation in reversed(applied):
            await db.invoices.update_one(
                {"_id": oid(allocation["invoice_id"]), "paid_amount": allocation["paid"]},
                {"$set": {"paid_amount": allocation["previous_paid"], "status": allocation["previous_status"]}},
            )
        raise


@router.post("/payments")
async def create_payment(body: PaymentIn, user=Depends(require("payments"))):
    if body.method not in {"numerar", *DOC_BY_METHOD}:
        raise HTTPException(400, "Metodă de plată invalidă")
    if body.amount <= 0:
        raise HTTPException(400, "Suma trebuie să fie mai mare decât zero")
    invoice = await get_or_404("invoices", body.invoice_id) if body.invoice_id else None
    client_id = body.client_id or (invoice or {}).get("client_id", "")
    if not client_id:
        raise HTTPException(400, "Selectați clientul sau factura fiscală restantă")
    client = await get_or_404("clients", client_id)
    if invoice and (invoice["type"] != "fiscal" or invoice.get("kind") == "credit_note"):
        raise HTTPException(400, "Încasările se înregistrează numai pe facturi fiscale")
    if invoice and invoice["client_id"] != client_id:
        raise HTTPException(400, "Factura selectată nu aparține clientului")
    if body.method == "numerar":
        if body.cash_document not in CASH_DOCUMENTS:
            raise HTTPException(400, "Document de numerar invalid")
        if body.cash_document == "fiscal_receipt" and client.get("type") != "pf":
            raise HTTPException(400, "Bonul fiscal este disponibil numai pentru persoane fizice")
        doc_type, prefix = CASH_DOCUMENTS[body.cash_document]
    else:
        doc_type, prefix = DOC_BY_METHOD[body.method]
    allocations = await payment_plan(client_id, body.amount, body.invoice_id)
    await apply_payment_plan(allocations)
    seq = await next_seq(f"pay_{doc_type}")
    refs = ", ".join(item["invoice_ref"] for item in allocations)
    p = {
        "invoice_id": allocations[0]["invoice_id"],
        "invoice_ref": refs,
        "client_id": client_id,
        "client_name": client["name"],
        "allocations": [{key: value for key, value in item.items() if key in {"invoice_id", "invoice_ref", "amount"}} for item in allocations],
        "amount": round(body.amount, 2),
        "method": body.method,
        "doc_type": doc_type,
        "doc_number": f"{prefix}-{seq:06d}",
        "reference": body.reference,
        "date": iso(),
        "cashier": user["name"],
    }
    r = await db.payments.insert_one(p)
    await audit(user, "create", "payment", str(r.inserted_id), p["doc_number"])
    return ser(await db.payments.find_one({"_id": r.inserted_id}))


@router.get("/payments")
async def list_payments(
    day: str = "",
    method: str = "",
    q: str = "",
    page: int = 0,
    page_size: int = 20,
    user=Depends(require("payments")),
):
    if day:
        try:
            date.fromisoformat(day)
        except ValueError as exc:
            raise HTTPException(422, "Data trebuie să fie în format YYYY-MM-DD") from exc
    flt = {"date": {"$regex": f"^{re.escape(day)}"}} if day else {}
    if method:
        methods = [value for value in method.split(",") if value]
        flt["method"] = {"$in": methods} if len(methods) > 1 else methods[0]
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        flt["$or"] = [{"client_name": rx}, {"doc_number": rx}, {"invoice_ref": rx}]
    if not page:
        rows = await db.payments.find(flt).sort("date", -1).to_list(2000)
        return [ser(item) for item in rows]
    rows, total, current_page, size = await fetch_page(
        db.payments,
        flt,
        [("date", -1)],
        page,
        page_size,
    )
    return page_response([ser(item) for item in rows], total, current_page, size)


@router.get("/payments/{pid}")
async def get_payment(pid: str, user=Depends(require("invoices"))):
    return ser(await get_or_404("payments", pid))


@router.get("/cash-register")
async def cash_register(day: str = "", user=Depends(require("payments"))):
    day = day or now().date().isoformat()
    before_receipts = await db.payments.aggregate([
        {"$match": {"method": "numerar", "date": {"$lt": day}}},
        {"$group": {"_id": None, "amount": {"$sum": "$amount"}}},
    ]).to_list(1)
    before_deposits = await db.cash_movements.aggregate([
        {"$match": {"kind": {"$in": ["bank_deposit", "expense_settlement", "payment_order", "receipt_reversal"]}, "date": {"$lt": day}}},
        {"$group": {"_id": None, "amount": {"$sum": "$amount"}}},
    ]).to_list(1)
    opening = round(
        (before_receipts[0]["amount"] if before_receipts else 0)
        - (before_deposits[0]["amount"] if before_deposits else 0),
        2,
    )
    receipts = await db.payments.find(
        {"method": "numerar", "date": {"$regex": f"^{re.escape(day)}"}},
    ).sort("date", 1).to_list(1000)
    deposits = await db.cash_movements.find(
        {"kind": {"$in": ["bank_deposit", "expense_settlement", "payment_order", "receipt_reversal"]}, "date": {"$regex": f"^{re.escape(day)}"}},
    ).sort("date", 1).to_list(1000)
    entries = [
        {**ser(item), "direction": "in", "label": item["doc_type"]}
        for item in receipts
    ]
    entries.extend(
        {**ser(item), "direction": "out", "label": "depunere_banca", "client_name": "Depunere bancă"}
        for item in deposits
    )
    entries.sort(key=lambda item: item["date"])
    total_in = round(sum(item["amount"] for item in entries if item["direction"] == "in"), 2)
    total_out = round(sum(item["amount"] for item in entries if item["direction"] == "out"), 2)
    return {"day": day, "opening": opening, "entries": entries, "total_in": total_in, "total_out": total_out, "closing": round(opening + total_in - total_out, 2)}


@router.post("/cash-register/deposits")
async def create_cash_deposit(body: CashDepositIn, user=Depends(require("payments"))):
    if body.amount <= 0:
        raise HTTPException(400, "Suma depunerii trebuie să fie mai mare decât zero")
    register = await cash_register(user=user)
    if body.amount > register["closing"] + 0.001:
        raise HTTPException(400, "Depunerea depășește numerarul disponibil în casă")
    seq = await next_seq("cash_deposit")
    doc = {
        "kind": "bank_deposit",
        "amount": round(body.amount, 2),
        "doc_number": f"DB-{seq:06d}",
        "reference": body.reference,
        "notes": body.notes,
        "date": iso(),
        "created_by": user["name"],
    }
    result = await db.cash_movements.insert_one(doc)
    await audit(user, "create", "cash_deposit", str(result.inserted_id), doc["doc_number"])
    return ser(await db.cash_movements.find_one({"_id": result.inserted_id}))


@router.post("/cash-register/payouts")
async def create_cash_payout(body: CashPayoutIn, user=Depends(require("payments"))):
    if body.kind not in {"expense_settlement", "payment_order"}:
        raise HTTPException(400, "Tip plată invalid")
    if body.amount <= 0 or not body.beneficiary.strip():
        raise HTTPException(400, "Beneficiarul și suma sunt obligatorii")
    register = await cash_register(user=user)
    if body.amount > register["closing"] + 0.001:
        raise HTTPException(400, "Plata depășește numerarul disponibil în casă")
    prefix = "DC" if body.kind == "expense_settlement" else "DP"
    sequence = await next_seq(f"cash_{body.kind}")
    movement = {
        "kind": body.kind,
        "amount": round(body.amount, 2),
        "doc_number": f"{prefix}-{sequence:06d}",
        "beneficiary": body.beneficiary.strip(),
        "reference": body.reference,
        "notes": body.notes,
        "date": iso(),
        "created_by": user["name"],
    }
    result = await db.cash_movements.insert_one(movement)
    await audit(user, "create", body.kind, str(result.inserted_id), movement["doc_number"])
    return ser(await db.cash_movements.find_one({"_id": result.inserted_id}))


async def cash_register_rows(date_from: str, date_to: str, cash_only: bool) -> dict:
    payment_filter = {"date": {"$gte": date_from, "$lte": f"{date_to}T23:59:59"}}
    if cash_only:
        payment_filter["method"] = "numerar"
    payments = await db.payments.find(payment_filter).sort("date", 1).to_list(5000)
    opening_payment_filter = {"date": {"$lt": date_from}}
    if cash_only:
        opening_payment_filter["method"] = "numerar"
    opening_payments = await db.payments.find(opening_payment_filter).to_list(5000)
    movements = await db.cash_movements.find(
        {"date": {"$gte": date_from, "$lte": f"{date_to}T23:59:59"}},
    ).sort("date", 1).to_list(5000)
    opening_movements = await db.cash_movements.find({"date": {"$lt": date_from}}).to_list(5000)
    rows = [{"date": p["date"], "document": p["doc_number"], "label": p.get("client_name", ""), "in": p["amount"], "out": 0} for p in payments]
    rows.extend({"date": m["date"], "document": m["doc_number"], "label": m.get("beneficiary", "Depunere bancă"), "in": 0, "out": m["amount"]} for m in movements)
    rows.sort(key=lambda row: (row["date"], row["document"]))
    opening = round(
        sum(item["amount"] for item in opening_payments)
        - sum(item["amount"] for item in opening_movements),
        2,
    )
    for row in rows:
        opening = round(opening + row["in"] - row["out"], 2)
        row["balance"] = opening
    return {"items": rows, "opening": opening if not rows else rows[0]["balance"] - rows[0]["in"] + rows[0]["out"], "closing": opening, "date_from": date_from, "date_to": date_to}


@router.get("/cash-register/report")
async def cash_register_report(date_from: str, date_to: str, cash_only: bool = True, user=Depends(require("payments"))):
    return await cash_register_rows(date_from, date_to, cash_only)


@router.get("/cash-register/report.pdf")
async def cash_register_report_pdf(date_from: str, date_to: str, cash_only: bool = True, user=Depends(require("payments"))):
    report = await cash_register_rows(date_from, date_to, cash_only)
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    pdf.setTitle("Registru de casă")
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, 800, "REGISTRU ÎNCASĂRI NUMERAR" if cash_only else "REGISTRU TOATE MIȘCĂRILE")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(40, 782, f"Interval: {date_from} - {date_to}")
    y = 754
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(40, y, "Data")
    pdf.drawString(105, y, "Document")
    pdf.drawString(210, y, "Explicație")
    pdf.drawRightString(425, y, "Intrări")
    pdf.drawRightString(495, y, "Ieșiri")
    pdf.drawRightString(555, y, "Sold")
    pdf.setFont("Helvetica", 8)
    for row in report["items"]:
        y -= 16
        if y < 45:
            pdf.showPage()
            y = 780
            pdf.setFont("Helvetica", 8)
        pdf.drawString(40, y, row["date"][:10])
        pdf.drawString(105, y, row["document"])
        pdf.drawString(210, y, row["label"][:35])
        pdf.drawRightString(425, y, f"{row['in']:.2f}")
        pdf.drawRightString(495, y, f"{row['out']:.2f}")
        pdf.drawRightString(555, y, f"{row['balance']:.2f}")
    pdf.save()
    return Response(content=output.getvalue(), media_type="application/pdf")


@router.post("/payments/{pid}/reverse")
async def reverse_cash_payment(pid: str, body: CashReversalIn, user=Depends(require("payments"))):
    payment = await get_or_404("payments", pid)
    allowed_documents = {"chitanta", "bon_fiscal", "dispozitie_incasare"}
    if payment.get("method") != "numerar" or payment.get("doc_type") not in allowed_documents:
        raise HTTPException(400, "Se pot storna doar documente de încasare în numerar")
    if payment.get("reversed_at"):
        raise HTTPException(400, "Documentul este deja stornat")
    if not body.reason.strip():
        raise HTTPException(400, "Motivul stornării este obligatoriu")
    allocations = payment.get("allocations") or [{"invoice_id": payment["invoice_id"], "amount": payment["amount"]}]
    for allocation in allocations:
        invoice = await get_or_404("invoices", allocation["invoice_id"])
        paid = round(max(0, invoice.get("paid_amount", 0) - allocation["amount"]), 2)
        status = "paid" if paid + invoice.get("credited_amount", 0) >= invoice["totals"]["gross"] - 0.001 else ("partial" if paid else "unpaid")
        await db.invoices.update_one({"_id": invoice["_id"]}, {"$set": {"paid_amount": paid, "status": status}})
    sequence = await next_seq("cash_receipt_reversal")
    movement = {
        "kind": "receipt_reversal",
        "amount": payment["amount"],
        "doc_number": f"ST-{sequence:06d}",
        "beneficiary": payment.get("client_name", ""),
        "reference": payment["doc_number"],
        "reason": body.reason.strip(),
        "payment_id": pid,
        "date": iso(),
        "created_by": user["name"],
    }
    result = await db.cash_movements.insert_one(movement)
    await db.payments.update_one({"_id": payment["_id"]}, {"$set": {"reversed_at": iso(), "reversed_by": user["name"]}})
    await audit(user, "reverse", "payment", pid, movement["doc_number"])
    return ser(await db.cash_movements.find_one({"_id": result.inserted_id}))
