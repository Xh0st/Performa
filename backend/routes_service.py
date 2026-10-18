import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from core import (db, ser, oid, iso, now, require, audit, get_or_404, next_seq, get_settings, calc_totals,
                  WO_STATUSES)

router = APIRouter(prefix="/api")
LIGHT = {"reception.photos": 0, "reception.signature": 0, "qc.mechanic_signature": 0, "qc.chief_signature": 0}
QC_ITEMS = [
    "noxe",
    "frane",
    "geometrie",
    "faruri_geamuri_parbrize",
    "parametri_reglaje",
    "etanșeitate",
    "proba_drum",
]
LOCKED = ("facturata", "inchisa")
CLOSURE_CATEGORIES = {"fara_cost", "diagnoza", "constatare"}


# ---------- Mechanics ----------
class MechanicIn(BaseModel):
    name: str
    specialty: str = "mecanic_senior"
    hourly_cost: float = 40
    phone: str = ""
    user_id: str = ""
    active: bool = True
    bonus_pct: float = 0


def hours_between(a: str, b: Optional[str]) -> float:
    end = datetime.fromisoformat(b) if b else now()
    return max(0.0, (end - datetime.fromisoformat(a)).total_seconds() / 3600)


async def mechanic_stats(month: str):
    entries = await db.time_entries.find({"start": {"$regex": f"^{month}"}}).to_list(20000)
    wos = await db.work_orders.find({"$or": [{"finished_at": {"$regex": f"^{month}"}}, {"invoiced_at": {"$regex": f"^{month}"}}]},
                                    {"lines": 1, "finished_at": 1, "invoiced_at": 1}).to_list(5000)
    stats = {}

    def s(mid):
        return stats.setdefault(mid, {"attendance": 0.0, "worked": 0.0, "norm": 0.0, "billed": 0.0, "clocked_in": False, "working_on": None})
    for e in entries:
        st = s(e["mechanic_id"])
        h = hours_between(e["start"], e.get("end"))
        st["attendance" if e["type"] == "attendance" else "worked"] += h
        if not e.get("end"):
            if e["type"] == "attendance":
                st["clocked_in"] = True
            else:
                st["working_on"] = e.get("work_order_id")
    for w in wos:
        for ln in w.get("lines", []):
            if ln["type"] == "labor" and ln.get("mechanic_id"):
                st = s(ln["mechanic_id"])
                if (w.get("finished_at") or "").startswith(month):
                    st["norm"] += ln["qty"]
                if (w.get("invoiced_at") or "").startswith(month):
                    st["billed"] += ln["qty"]
    for st in stats.values():
        for k in ("attendance", "worked", "norm", "billed"):
            st[k] = round(st[k], 2)
        st["productivity"] = round(st["billed"] / st["attendance"] * 100, 1) if st["attendance"] else 0
        st["efficiency"] = round(st["norm"] / st["worked"] * 100, 1) if st["worked"] else 0
    return stats


@router.get("/mechanics")
async def list_mechanics(month: str = "", user=Depends(require("workorders"))):
    month = month or now().strftime("%Y-%m")
    stats = await mechanic_stats(month)
    open_att = {e["mechanic_id"] for e in await db.time_entries.find({"type": "attendance", "end": None}).to_list(1000)}
    open_work = {e["mechanic_id"]: e.get("work_order_id") for e in await db.time_entries.find({"type": "work", "end": None}).to_list(1000)}
    out = []
    for m in await db.mechanics.find().sort("name", 1).to_list(500):
        d = ser(m)
        d["stats"] = stats.get(d["id"], {"attendance": 0, "worked": 0, "norm": 0, "billed": 0, "productivity": 0, "efficiency": 0})
        d["clocked_in"] = d["id"] in open_att
        d["working_on"] = open_work.get(d["id"])
        out.append(d)
    return out


@router.post("/mechanics")
async def create_mechanic(body: MechanicIn, user=Depends(require("settings"))):
    r = await db.mechanics.insert_one(body.model_dump() | {"created_at": iso()})
    await audit(user, "create", "mechanic", str(r.inserted_id), body.name)
    return ser(await db.mechanics.find_one({"_id": r.inserted_id}))


@router.put("/mechanics/{mid}")
async def update_mechanic(mid: str, body: MechanicIn, user=Depends(require("settings"))):
    await db.mechanics.update_one({"_id": oid(mid)}, {"$set": body.model_dump()})
    return ser(await get_or_404("mechanics", mid))


class ClockIn(BaseModel):
    action: str


@router.post("/mechanics/{mid}/clock")
async def clock(mid: str, body: ClockIn, user=Depends(require("mechanics"))):
    await get_or_404("mechanics", mid)
    open_e = await db.time_entries.find_one({"mechanic_id": mid, "type": "attendance", "end": None})
    if body.action == "in":
        if open_e:
            raise HTTPException(400, "Pontaj deja deschis")
        await db.time_entries.insert_one({"mechanic_id": mid, "type": "attendance", "start": iso(), "end": None})
    else:
        if not open_e:
            raise HTTPException(400, "Nu există pontaj deschis")
        await db.time_entries.update_many({"mechanic_id": mid, "type": "work", "end": None}, {"$set": {"end": iso()}})
        await db.time_entries.update_one({"_id": open_e["_id"]}, {"$set": {"end": iso()}})
    return {"ok": True}


@router.get("/mechanics/{mid}/entries")
async def mechanic_entries(mid: str, user=Depends(require("mechanics"))):
    return [ser(e) for e in await db.time_entries.find({"mechanic_id": mid}).sort("start", -1).to_list(200)]


# ---------- Work orders ----------
class ReceptionIn(BaseModel):
    client_id: str
    vehicle_id: str
    mileage_in: int
    fuel_level: str = "1/2"
    complaint: str
    observations: str = ""
    accessories: List[str] = []
    damages: List[str] = []
    photos: dict
    signature: str
    promised_date: str = ""
    elevator: str = ""
    advisor: str = ""


async def enrich(wos):
    cids = {w.get("client_id") for w in wos}
    vids = {w.get("vehicle_id") for w in wos}
    clients = {str(c["_id"]): c for c in await db.clients.find({"_id": {"$in": [oid(i) for i in cids if i]}}).to_list(5000)}
    vehicles = {str(v["_id"]): v for v in await db.vehicles.find({"_id": {"$in": [oid(i) for i in vids if i]}}).to_list(5000)}
    mechs = {str(m["_id"]): m["name"] for m in await db.mechanics.find().to_list(500)}
    out = []
    for w in wos:
        d = ser(w)
        c, v = clients.get(w.get("client_id"), {}), vehicles.get(w.get("vehicle_id"), {})
        d["client_name"] = c.get("name", "")
        d["client_phone"] = c.get("phone", "")
        d["vehicle"] = {"plate": v.get("plate", ""), "make": v.get("make", ""), "model": v.get("model", ""), "vin": v.get("vin", ""), "year": v.get("year")}
        d["mechanic_names"] = [mechs.get(m, "") for m in w.get("mechanic_ids", [])]
        d["totals"] = calc_totals([dict(x) for x in w.get("lines", [])])
        out.append(d)
    return out


@router.get("/work-orders")
async def list_work_orders(status: str = "", q: str = "", active: bool = False, user=Depends(require("workorders"))):
    flt = {}
    if status:
        flt["status"] = status
    elif active:
        flt["status"] = {"$nin": list(LOCKED)}
    if q:
        flt["number"] = {"$regex": re.escape(q), "$options": "i"}
    proj = LIGHT | {"quotes": 0}
    return await enrich(await db.work_orders.find(flt, proj).sort("created_at", -1).to_list(1000))


@router.post("/work-orders")
async def create_work_order(body: ReceptionIn, user=Depends(require("reception"))):
    if not body.signature:
        raise HTTPException(400, "Semnătura clientului este obligatorie")
    await get_or_404("clients", body.client_id)
    vehicle = await get_or_404("vehicles", body.vehicle_id)
    if vehicle["client_id"] != body.client_id:
        raise HTTPException(400, "Vehiculul nu aparține clientului")
    seq = await next_seq("work_order")
    number = f"CL-{now().year}-{seq:05d}"
    doc = {"number": number, "client_id": body.client_id, "vehicle_id": body.vehicle_id, "status": "noua",
           "mileage_in": body.mileage_in, "complaint": body.complaint, "diagnosis": "", "mechanic_ids": [],
           "elevator": body.elevator, "promised_date": body.promised_date, "advisor": body.advisor or user["name"],
           "reception": {"fuel_level": body.fuel_level, "observations": body.observations, "accessories": body.accessories,
                         "damages": body.damages, "photos": body.photos, "odometer_photo": None,
                         "signature": body.signature, "at": iso(), "by": user["name"]},
           "lines": [], "quotes": [], "qc": {}, "created_at": iso(), "created_by": user["id"],
           "status_history": [{"status": "noua", "at": iso(), "by": user["name"], "note": "Recepție vehicul"}]}
    r = await db.work_orders.insert_one(doc)
    if body.mileage_in > vehicle.get("mileage", 0):
        await db.vehicles.update_one({"_id": vehicle["_id"]}, {"$set": {"mileage": body.mileage_in}})
    await audit(user, "create", "work_order", str(r.inserted_id), number)
    return {"id": str(r.inserted_id), "number": number}


async def load_wo(wid: str):
    return await get_or_404("work_orders", wid)


@router.get("/work-orders/{wid}")
async def get_work_order(wid: str, user=Depends(require("workorders"))):
    w = (await enrich([await load_wo(wid)]))[0]
    w["time_entries"] = [ser(e) for e in await db.time_entries.find({"work_order_id": wid}).sort("start", -1).to_list(500)]
    today = now().date().isoformat()
    warranties = await db.warranty_certificates.find({"vehicle_id": w["vehicle_id"]}).to_list(100)
    w["warranty_alerts"] = [
        {"number": item["number"], "invoice_ref": item["invoice_ref"], "active_lines": len([line for line in item["lines"] if line["valid_to"] >= today])}
        for item in warranties
        if any(line["valid_to"] >= today for line in item["lines"])
    ]
    return w


class WOUpdate(BaseModel):
    complaint: Optional[str] = None
    diagnosis: Optional[str] = None
    mechanic_ids: Optional[List[str]] = None
    elevator: Optional[str] = None
    promised_date: Optional[str] = None
    closure_category: Optional[str] = None


def quote_closure_rule(work_order: dict) -> dict:
    quotes = work_order.get("quotes", [])
    if any(quote.get("status") == "approved" for quote in quotes):
        return {"allowed": True, "reason": "deviz_aprobat", "review": False}
    if any(quote.get("status") in {"draft", "sent"} for quote in quotes):
        return {"allowed": False, "reason": "deviz_in_asteptare", "review": False}
    if any(quote.get("status") == "rejected" for quote in quotes):
        return {"allowed": True, "reason": "deviz_respins", "review": True}
    if work_order.get("is_warranty"):
        return {"allowed": True, "reason": "garantie", "review": False}
    category = work_order.get("closure_category", "")
    if category in CLOSURE_CATEGORIES:
        return {"allowed": True, "reason": category, "review": True}
    if not quotes:
        return {"allowed": True, "reason": "fara_deviz_generat", "review": True}
    return {"allowed": False, "reason": "deviz_neaprobat", "review": False}


@router.put("/work-orders/{wid}")
async def update_work_order(wid: str, body: WOUpdate, user=Depends(require("workorders"))):
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if "closure_category" in upd and upd["closure_category"] not in CLOSURE_CATEGORIES | {""}:
        raise HTTPException(400, "Categorie de închidere invalidă")
    await db.work_orders.update_one({"_id": oid(wid)}, {"$set": upd})
    return await get_work_order(wid, user)


class StatusIn(BaseModel):
    status: str
    note: str = ""


@router.post("/work-orders/{wid}/status")
async def change_status(wid: str, body: StatusIn, user=Depends(require("workorders"))):
    w = await load_wo(wid)
    st = body.status
    if st not in WO_STATUSES or st == "facturata":
        raise HTTPException(400, "Status invalid (Facturată se setează automat la emiterea facturii)")
    if w["status"] in LOCKED:
        raise HTTPException(400, "Comanda este facturată sau închisă și nu mai poate fi modificată")
    if st == "finalizata" and not w.get("qc", {}).get("passed"):
        raise HTTPException(400, "Controlul de calitate trebuie promovat înainte de finalizare")
    rule = quote_closure_rule(w)
    if st == "finalizata" and not rule["allowed"]:
        raise HTTPException(400, "Devizul este în așteptare; aprobați sau respingeți-l înainte de finalizare")
    upd = {"status": st}
    if st == "finalizata":
        upd["finished_at"] = iso()
        upd["closure_quote_rule"] = rule
        await db.time_entries.update_many({"work_order_id": wid, "end": None}, {"$set": {"end": iso()}})
    if st == "inchisa":
        upd["closed_at"] = iso()
        upd["pre_closure_status"] = w["status"]
        upd["closure_quote_rule"] = {"allowed": True, "reason": "inchidere_nefacturata", "review": True}
    await db.work_orders.update_one({"_id": w["_id"]}, {"$set": upd, "$push": {
        "status_history": {"status": st, "at": iso(), "by": user["name"], "note": body.note}}})
    await audit(user, "status", "work_order", wid, st)
    return await get_work_order(wid, user)


class ClosureReviewIn(BaseModel):
    note: str = ""


@router.get("/closure-exceptions/work-orders")
async def closure_exceptions(user=Depends(require("settings"))):
    rows = await db.work_orders.find({"status": "inchisa", "closure_review": {"$exists": False}}).sort("closed_at", -1).to_list(2000)
    flagged = []
    for row in rows:
        row["closure_quote_rule"] = row.get("closure_quote_rule") or quote_closure_rule(row)
        flagged.append(row)
    return await enrich(flagged)


@router.post("/work-orders/{wid}/closure-review")
async def review_closure_exception(wid: str, body: ClosureReviewIn, user=Depends(require("settings"))):
    work_order = await load_wo(wid)
    if work_order["status"] != "inchisa" or work_order.get("invoice_id"):
        raise HTTPException(400, "Doar comenzile nefacturate închise pot fi aprobate")
    review = {"at": iso(), "by": user["name"], "note": body.note.strip(), "status": "aprobat"}
    await db.work_orders.update_one({"_id": work_order["_id"]}, {"$set": {"closure_review": review}})
    await audit(user, "approve", "work_order_closure", wid, "inchidere nefacturată")
    return await get_work_order(wid, user)


@router.post("/work-orders/{wid}/reopen")
async def reopen_work_order(wid: str, body: ClosureReviewIn, user=Depends(require("settings"))):
    work_order = await load_wo(wid)
    if work_order["status"] != "inchisa" or work_order.get("invoice_id"):
        raise HTTPException(400, "Doar comenzile nefacturate închise pot fi redeschise")
    previous = work_order.get("pre_closure_status")
    if not previous:
        history = [item for item in work_order.get("status_history", []) if item.get("status") != "inchisa"]
        previous = history[-1].get("status") if history else "noua"
    await db.work_orders.update_one({"_id": work_order["_id"]}, {
        "$set": {"status": previous, "reopened_at": iso(), "reopened_by": user["name"]},
        "$unset": {"closure_review": "", "closed_at": ""},
        "$push": {"status_history": {"status": previous, "at": iso(), "by": user["name"], "note": body.note.strip() or "Redeschis din verificare închideri"}},
    })
    await audit(user, "reopen", "work_order_closure", wid, previous)
    return await get_work_order(wid, user)


class LineIn(BaseModel):
    type: str
    description: str = ""
    product_id: str = ""
    qty: float = 1
    unit_price: Optional[float] = None
    discount: float = 0
    labor_category: str = ""
    norm_source: str = "Manual"
    mechanic_id: str = ""


async def build_line(body: LineIn):
    s = await get_settings()
    ln = {"id": secrets.token_hex(6), "type": body.type, "description": body.description, "qty": body.qty,
          "discount": body.discount, "vat_rate": s.get("vat_rate", 21), "product_id": body.product_id, "code": "",
          "unit": "buc", "labor_category": body.labor_category, "norm_source": body.norm_source, "mechanic_id": body.mechanic_id}
    if body.type in ("part", "consumable"):
        if body.product_id:
            p = await get_or_404("products", body.product_id)
            ln.update(code=p["code"], description=body.description or p["name"], unit=p.get("unit", "buc"),
                      unit_cost=p.get("avg_cost", 0), vat_rate=p.get("vat_rate", ln["vat_rate"]))
            ln["unit_price"] = body.unit_price if body.unit_price is not None else p["sale_price"]
        else:
            ln["unit_price"] = body.unit_price or 0
    elif body.type == "labor":
        rate = s.get("labor_rates", {}).get(body.labor_category or "mecanic_senior", 150)
        ln.update(unit="ore", labor_category=body.labor_category or "mecanic_senior")
        ln["unit_price"] = body.unit_price if body.unit_price is not None else rate
    else:
        raise HTTPException(400, "Tip linie invalid")
    if not ln["description"]:
        raise HTTPException(400, "Descriere obligatorie")
    return ln


@router.post("/work-orders/{wid}/lines")
async def add_line(wid: str, body: LineIn, user=Depends(require("workorders"))):
    w = await load_wo(wid)
    if w.get("is_warranty"):
        raise HTTPException(400, "Liniile comenzii de garanție sunt fixate la preț zero")
    if w["status"] in LOCKED:
        raise HTTPException(400, "Comanda facturată nu mai poate fi modificată")
    ln = await build_line(body)
    upd = {"$push": {"lines": ln}}
    if body.mechanic_id and body.mechanic_id not in w.get("mechanic_ids", []):
        upd["$addToSet"] = {"mechanic_ids": body.mechanic_id}
    await db.work_orders.update_one({"_id": w["_id"]}, upd)
    return await get_work_order(wid, user)


@router.delete("/work-orders/{wid}/lines/{lid}")
async def delete_line(wid: str, lid: str, user=Depends(require("workorders"))):
    w = await load_wo(wid)
    if w.get("is_warranty"):
        raise HTTPException(400, "Liniile comenzii de garanție sunt fixate la preț zero")
    if w["status"] in LOCKED:
        raise HTTPException(400, "Comanda facturată nu mai poate fi modificată")
    await db.work_orders.update_one({"_id": w["_id"]}, {"$pull": {"lines": {"id": lid}}})
    return await get_work_order(wid, user)


# ---------- Quotes (devize) ----------
class QuoteIn(BaseModel):
    valid_days: int = 7
    notes: str = ""


@router.post("/work-orders/{wid}/quotes")
async def create_quote(wid: str, body: QuoteIn, user=Depends(require("workorders"))):
    w = await load_wo(wid)
    if not w.get("lines"):
        raise HTTPException(400, "Adăugați piese/manoperă înainte de a genera devizul")
    lines = [dict(x) for x in w["lines"]]
    totals = calc_totals(lines)
    version = len(w.get("quotes", [])) + 1
    q = {"version": version, "number": f"DV-{w['number'][3:]}-v{version}", "lines": lines, "totals": totals,
         "status": "draft", "token": secrets.token_urlsafe(16), "notes": body.notes, "created_at": iso(),
         "created_by": user["name"], "valid_until": (now() + timedelta(days=body.valid_days)).date().isoformat(), "sent": []}
    if w.get("quotes"):
        await db.work_orders.update_one({"_id": w["_id"]}, {"$set": {"quotes.$[o].status": "superseded"}},
                                        array_filters=[{"o.status": {"$in": ["draft", "sent"]}}])
    await db.work_orders.update_one({"_id": w["_id"]}, {"$push": {"quotes": q}})
    if w["status"] in ("noua", "diagnosticare"):
        await db.work_orders.update_one({"_id": w["_id"]}, {"$set": {"status": "asteapta_oferta"}, "$push": {
            "status_history": {"status": "asteapta_oferta", "at": iso(), "by": user["name"], "note": f"Deviz v{version}"}}})
    await audit(user, "create", "quote", wid, q["number"])
    return await get_quotes(wid, user)


@router.get("/work-orders/{wid}/quotes")
async def get_quotes(wid: str, user=Depends(require("workorders"))):
    w = await db.work_orders.find_one({"_id": oid(wid)}, {"quotes": 1})
    return w.get("quotes", []) if w else []


class SendIn(BaseModel):
    channel: str
    link: str = ""


@router.post("/work-orders/{wid}/quotes/{version}/send")
async def send_quote(wid: str, version: int, body: SendIn, user=Depends(require("workorders"))):
    w = await load_wo(wid)
    c = await get_or_404("clients", w["client_id"])
    target = c.get("email") if body.channel == "email" else c.get("phone")
    if not target:
        raise HTTPException(400, "Clientul nu are date de contact pentru acest canal")
    # MOCKED: notification is recorded, not actually sent (no SMS/email/WhatsApp provider configured)
    await db.notifications.insert_one({"channel": body.channel, "to": target, "kind": "quote", "work_order_id": wid,
                                       "message": f"Devizul pentru {w['number']} este disponibil: {body.link}",
                                       "status": "simulated", "at": iso()})
    await db.work_orders.update_one({"_id": w["_id"], "quotes.version": version}, {
        "$set": {"quotes.$.status": "sent"}, "$push": {"quotes.$.sent": {"channel": body.channel, "to": target, "at": iso()}}})
    return {"ok": True, "to": target, "simulated": True}


class DecisionIn(BaseModel):
    approved: bool
    signature: str = ""
    name: str = ""
    reason: str = ""


async def apply_decision(w: dict, version: int, body: DecisionIn, via: str, by: str):
    q = next((x for x in w.get("quotes", []) if x["version"] == version), None)
    if not q:
        raise HTTPException(404, "Deviz inexistent")
    if q["status"] not in ("draft", "sent"):
        raise HTTPException(400, "Devizul nu mai poate fi aprobat/respins")
    if body.approved and not body.signature:
        raise HTTPException(400, "Semnătura este obligatorie pentru aprobare")
    st = "approved" if body.approved else "rejected"
    await db.work_orders.update_one({"_id": w["_id"], "quotes.version": version}, {"$set": {
        "quotes.$.status": st, "quotes.$.decision": {"signature": body.signature, "name": body.name or by,
                                                     "reason": body.reason, "via": via, "at": iso()}}})
    if body.approved and w["status"] in ("noua", "diagnosticare", "asteapta_oferta"):
        await db.work_orders.update_one({"_id": w["_id"]}, {"$set": {"status": "aprobata", "approved_quote": version}, "$push": {
            "status_history": {"status": "aprobata", "at": iso(), "by": by, "note": f"Deviz v{version} aprobat ({via})"}}})


@router.post("/work-orders/{wid}/quotes/{version}/decision")
async def quote_decision(wid: str, version: int, body: DecisionIn, user=Depends(require("workorders"))):
    await apply_decision(await load_wo(wid), version, body, "service", user["name"])
    return await get_quotes(wid, user)


@router.get("/public/quotes/{token}")
async def public_quote(token: str):
    w = await db.work_orders.find_one({"quotes.token": token}, {"quotes": 1, "number": 1, "client_id": 1, "vehicle_id": 1})
    if not w:
        raise HTTPException(404, "Deviz inexistent")
    q = next(x for x in w["quotes"] if x["token"] == token)
    c = await db.clients.find_one({"_id": oid(w["client_id"])})
    v = await db.vehicles.find_one({"_id": oid(w["vehicle_id"])})
    s = await get_settings()
    return {"company": s.get("name"), "work_order": w["number"], "client": c["name"],
            "vehicle": f"{v['make']} {v['model']} · {v['plate']}", "quote": {k: q[k] for k in q if k not in ("token",)}}


@router.post("/public/quotes/{token}/decision")
async def public_decision(token: str, body: DecisionIn):
    w = await db.work_orders.find_one({"quotes.token": token})
    if not w:
        raise HTTPException(404, "Deviz inexistent")
    q = next(x for x in w["quotes"] if x["token"] == token)
    await apply_decision(w, q["version"], body, "portal client", body.name or "Client")
    return {"ok": True}


# ---------- Quality control ----------
class QCIn(BaseModel):
    items: dict
    notes: str = ""
    mechanic_signature: str = ""
    chief_signature: str = ""


@router.put("/work-orders/{wid}/qc")
async def save_qc(wid: str, body: QCIn, user=Depends(require("workorders"))):
    w = await load_wo(wid)
    if w["status"] in LOCKED:
        raise HTTPException(400, "Controlul final este blocat după facturare sau închidere")
    complete = all(body.items.get(key) in ("C", "N", "NA") for key in QC_ITEMS)
    conforming = complete and all(body.items.get(key) in ("C", "NA") for key in QC_ITEMS)
    if body.chief_signature and user["role"] not in ("admin", "director", "sef_service"):
        raise HTTPException(403, "Inspecția finală este validată de șeful de service")
    passed = conforming and bool(body.mechanic_signature) and bool(body.chief_signature)
    qc = body.model_dump() | {
        "passed": passed,
        "at": iso(),
        "by": user["name"],
        "inspector_name": user["name"] if body.chief_signature else "",
    }
    await db.work_orders.update_one({"_id": w["_id"]}, {"$set": {"qc": qc}})
    return await get_work_order(wid, user)


class TimerIn(BaseModel):
    mechanic_id: str
    action: str


@router.post("/work-orders/{wid}/timer")
async def work_timer(wid: str, body: TimerIn, user=Depends(require("workorders"))):
    w = await load_wo(wid)
    await get_or_404("mechanics", body.mechanic_id)
    open_e = await db.time_entries.find_one({"mechanic_id": body.mechanic_id, "type": "work", "end": None})
    if body.action == "start":
        if w["status"] not in ("aprobata", "in_lucru", "diagnosticare"):
            raise HTTPException(400, "Lucrul poate începe doar pe comenzi aprobate sau în diagnosticare")
        if open_e:
            await db.time_entries.update_one({"_id": open_e["_id"]}, {"$set": {"end": iso()}})
        await db.time_entries.insert_one({"mechanic_id": body.mechanic_id, "type": "work", "work_order_id": wid,
                                          "work_order_number": w["number"], "start": iso(), "end": None})
        upd = {"$addToSet": {"mechanic_ids": body.mechanic_id}}
        if w["status"] == "aprobata":
            upd["$set"] = {"status": "in_lucru"}
            upd["$push"] = {"status_history": {"status": "in_lucru", "at": iso(), "by": user["name"], "note": "Start lucru"}}
        await db.work_orders.update_one({"_id": w["_id"]}, upd)
    else:
        await db.time_entries.update_many({"mechanic_id": body.mechanic_id, "work_order_id": wid, "end": None}, {"$set": {"end": iso()}})
    return await get_work_order(wid, user)


@router.get("/elevators")
async def elevators(user=Depends(require("workorders"))):
    s = await get_settings()
    busy = {w["elevator"]: w for w in await db.work_orders.find(
        {"status": {"$in": ["diagnosticare", "aprobata", "in_lucru", "asteapta_piese"]}, "elevator": {"$nin": ["", None]}},
        {"number": 1, "elevator": 1, "status": 1}).to_list(500)}
    return [{"name": e, "busy": e in busy, "work_order": busy[e]["number"] if e in busy else None,
             "work_order_id": str(busy[e]["_id"]) if e in busy else None} for e in s.get("elevators", [])]
