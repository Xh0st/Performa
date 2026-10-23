import re
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from core import db, ser, oid, iso, require, audit, get_or_404, get_settings
from vehicle_catalog import MAKES, decode_vin
from cui_lookup import lookup_cui
from pagination import fetch_page, page_response
from account_statement_pdf import build_account_statement_pdf
from client_finance import account_statement, client_credit_position

router = APIRouter(prefix="/api")


class ClientIn(BaseModel):
    type: str = "pf"
    name: str
    cnp: str = ""
    cui: str = ""
    reg_com: str = ""
    representative: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    city: str = ""
    county: str = ""
    is_fleet: bool = False
    budget_limit: float = 0
    payment_terms_days: Optional[int] = None
    credit_limit: Optional[float] = 0
    gdpr_consent: bool = False
    notes: str = ""


class VehicleIn(BaseModel):
    client_id: str
    vin: str
    plate: str
    make: str
    model: str
    year: Optional[int] = None
    engine: str = ""
    power_kw: Optional[int] = None
    euro: str = ""
    fuel: str = "benzina"
    mileage: int = 0
    color: str = ""
    itp_expiry: str = ""
    rca_expiry: str = ""
    casco_expiry: str = ""
    rovinieta_expiry: str = ""


class CuiLookupIn(BaseModel):
    cui: str


def validate_cnp(cnp: str) -> bool:
    if not re.fullmatch(r"\d{13}", cnp):
        return False
    key = "279146358279"
    s = sum(int(cnp[i]) * int(key[i]) for i in range(12)) % 11
    return (1 if s == 10 else s) == int(cnp[12])


def validate_client(b: ClientIn):
    if b.type not in ("pf", "pj"):
        raise HTTPException(400, "Tip client invalid")
    if b.type == "pf" and b.cnp and not validate_cnp(b.cnp):
        raise HTTPException(400, "CNP invalid")
    if b.type == "pj" and not b.cui:
        raise HTTPException(400, "CUI obligatoriu pentru persoane juridice")
    if b.type == "pf":
        if b.payment_terms_days not in (None, 0) or b.credit_limit not in (None, 0):
            raise HTTPException(400, "Persoanele fizice nu pot avea termen de plată sau limită de credit")
        b.payment_terms_days = None
        b.credit_limit = None
    if b.type == "pj" and b.payment_terms_days is not None:
        if b.payment_terms_days < 1 or b.payment_terms_days > 365:
            raise HTTPException(400, "Termenul de plată trebuie să fie între 1 și 365 zile")
    if b.type == "pj" and b.credit_limit is None:
        b.credit_limit = 0
    if b.type == "pj" and b.credit_limit is not None and b.credit_limit < 0:
        raise HTTPException(400, "Limita de credit nu poate fi negativă")


def search_filter(q: str, fields):
    rx = {"$regex": re.escape(q), "$options": "i"}
    return {"$or": [{f: rx} for f in fields]}


@router.post("/cui/lookup")
async def cui_lookup(body: CuiLookupIn, user=Depends(require("crm"))):
    result = await lookup_cui(body.cui)
    await db.audit_logs.insert_one({"action": "cui_lookup", "entity": "cui", "detail": result["cui"], "at": iso(), "user_id": user["id"]})
    return result


@router.get("/clients")
async def list_clients(
    q: str = "",
    type: str = "",
    page: int = 0,
    page_size: int = 20,
    user=Depends(require("crm")),
):
    flt = search_filter(q, ["name", "cnp", "cui", "phone", "email"]) if q else {}
    if type:
        flt["type"] = type
    if page:
        clients, total, current_page, size = await fetch_page(
            db.clients,
            flt,
            [("name", 1)],
            page,
            page_size,
        )
    else:
        clients = await db.clients.find(flt).sort("name", 1).to_list(1000)
    client_ids = [str(item["_id"]) for item in clients]
    counts = {}
    async for v in db.vehicles.aggregate([
        {"$match": {"client_id": {"$in": client_ids}}},
        {"$group": {"_id": "$client_id", "n": {"$sum": 1}}},
    ]):
        counts[v["_id"]] = v["n"]
    out = []
    for c in clients:
        d = ser(c)
        d["vehicle_count"] = counts.get(d["id"], 0)
        out.append(d)
    if page:
        return page_response(out, total, current_page, size)
    return out


@router.post("/clients")
async def create_client(body: ClientIn, user=Depends(require("crm"))):
    validate_client(body)
    doc = body.model_dump() | {"created_at": iso()}
    r = await db.clients.insert_one(doc)
    await audit(user, "create", "client", str(r.inserted_id), body.name)
    return ser(await db.clients.find_one({"_id": r.inserted_id}))


@router.get("/clients/{cid}")
async def get_client(cid: str, user=Depends(require("crm"))):
    c = ser(await get_or_404("clients", cid))
    if c.get("type") == "pj" and c.get("credit_limit") is None:
        c["credit_limit"] = 0
    c["vehicles"] = [ser(v) for v in await db.vehicles.find({"client_id": cid}).to_list(500)]
    c["work_order_count"] = await db.work_orders.count_documents({"client_id": cid})
    c["invoice_count"] = await db.invoices.count_documents({"client_id": cid, "type": "fiscal"})
    c["financial_summary"] = await client_credit_position(cid)
    return c


async def client_work_order_rows(client_id: str, query: str, page: int, page_size: int) -> dict:
    flt = {"client_id": client_id}
    if query.strip():
        rx = {"$regex": re.escape(query.strip()), "$options": "i"}
        vehicle_ids = [
            str(item["_id"])
            async for item in db.vehicles.find(
                {
                    "client_id": client_id,
                    "$or": [{"plate": rx}, {"vin": rx}, {"make": rx}, {"model": rx}],
                },
                {"_id": 1},
            )
        ]
        flt["$or"] = [
            {"number": rx},
            {"complaint": rx},
            {"vehicle_id": {"$in": vehicle_ids}},
        ]
    projection = {"reception.photos": 0, "reception.signature": 0, "quotes": 0}
    rows, total, current_page, size = await fetch_page(
        db.work_orders,
        flt,
        [("created_at", -1)],
        page,
        page_size,
        projection,
    )
    vehicle_ids = [oid(item["vehicle_id"]) for item in rows if item.get("vehicle_id")]
    vehicles = {
        str(item["_id"]): item
        for item in await db.vehicles.find({"_id": {"$in": vehicle_ids}}).to_list(500)
    }
    items = []
    for row in rows:
        item = ser(row)
        vehicle = vehicles.get(item.get("vehicle_id"), {})
        item["vehicle_label"] = " · ".join(
            value for value in [vehicle.get("plate"), vehicle.get("make"), vehicle.get("model")] if value
        )
        items.append(item)
    return page_response(items, total, current_page, size)


@router.get("/clients/{cid}/work-orders")
async def client_work_orders(
    cid: str,
    q: str = "",
    page: int = 1,
    page_size: int = 20,
    user=Depends(require("crm")),
):
    await get_or_404("clients", cid)
    return await client_work_order_rows(cid, q, page, page_size)


@router.get("/clients/{cid}/invoices")
async def client_invoices(
    cid: str,
    q: str = "",
    page: int = 1,
    page_size: int = 20,
    user=Depends(require("crm")),
):
    await get_or_404("clients", cid)
    flt = {"client_id": cid}
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        flt["$or"] = [{"series": rx}, {"number": rx}, {"vehicle": rx}, {"work_order_number": rx}]
    rows, total, current_page, size = await fetch_page(
        db.invoices,
        flt,
        [("issue_date", -1), ("created_at", -1)],
        page,
        page_size,
        {"efactura.xml": 0},
    )
    return page_response([ser(item) for item in rows], total, current_page, size)


async def client_statement(cid: str, date_from: str, date_to: str, page: int, page_size: int) -> tuple[dict, dict]:
    client = ser(await get_or_404("clients", cid))
    try:
        statement = await account_statement(cid, date_from, date_to, page, page_size)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return client, statement


@router.get("/clients/{cid}/account-statement")
async def client_account_statement(
    cid: str,
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    page_size: int = 20,
    user=Depends(require("crm")),
):
    _, statement = await client_statement(cid, date_from, date_to, page, page_size)
    statement.pop("all_items", None)
    return statement


@router.get("/clients/{cid}/account-statement.pdf")
async def client_account_statement_pdf(
    cid: str,
    date_from: str = "",
    date_to: str = "",
    user=Depends(require("crm")),
):
    client, statement = await client_statement(cid, date_from, date_to, 1, 20)
    settings = await get_settings()
    premium = settings.get("subscription_plan") in {"FULL", "ENTERPRISE"}
    content = build_account_statement_pdf(
        client,
        statement,
        include_footer=not premium,
        custom_logo_data_url=settings.get("custom_logo_data_url", "") if premium else "",
    )
    filename = f"fisa_cont_{cid}_{date_from or 'toate'}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.put("/clients/{cid}")
async def update_client(cid: str, body: ClientIn, user=Depends(require("crm"))):
    validate_client(body)
    await db.clients.update_one({"_id": oid(cid)}, {"$set": body.model_dump()})
    await audit(user, "update", "client", cid, body.name)
    return ser(await get_or_404("clients", cid))


@router.delete("/clients/{cid}")
async def delete_client(cid: str, user=Depends(require("crm"))):
    await get_or_404("clients", cid)
    if await db.work_orders.find_one({"client_id": cid}):
        raise HTTPException(400, "Clientul are comenzi de lucru și nu poate fi șters")
    await db.clients.delete_one({"_id": oid(cid)})
    await db.vehicles.delete_many({"client_id": cid})
    await audit(user, "delete", "client", cid)
    return {"ok": True}


async def attach_owner(vs):
    ids = list({v["client_id"] for v in vs if v.get("client_id")})
    owners = {str(c["_id"]): c["name"] for c in await db.clients.find({"_id": {"$in": [oid(i) for i in ids]}}).to_list(2000)}
    out = []
    for v in vs:
        d = ser(v)
        d["client_name"] = owners.get(v.get("client_id"), "")
        out.append(d)
    return out


@router.get("/vehicle-catalog")
async def vehicle_catalog(user=Depends(require("vehicles"))):
    return {"makes": MAKES}


@router.get("/vin/decode/{vin}")
async def vin_decode(vin: str, user=Depends(require("vehicles"))):
    out = await decode_vin(vin)
    out["exists"] = bool(await db.vehicles.find_one({"vin": out["vin"]}, {"_id": 1}))
    return out


@router.get("/vehicles")
async def list_vehicles(
    q: str = "",
    client_id: str = "",
    page: int = 0,
    page_size: int = 20,
    user=Depends(require("vehicles")),
):
    flt = search_filter(q, ["vin", "plate", "make", "model"]) if q else {}
    if client_id:
        flt["client_id"] = client_id
    if not page:
        return await attach_owner(await db.vehicles.find(flt).sort("plate", 1).to_list(2000))
    rows, total, current_page, size = await fetch_page(
        db.vehicles,
        flt,
        [("plate", 1)],
        page,
        page_size,
    )
    return page_response(await attach_owner(rows), total, current_page, size)


@router.post("/vehicles")
async def create_vehicle(body: VehicleIn, user=Depends(require("vehicles"))):
    vin = body.vin.strip().upper()
    if len(vin) != 17:
        raise HTTPException(400, "VIN trebuie să aibă 17 caractere")
    if await db.vehicles.find_one({"vin": vin}):
        raise HTTPException(400, "VIN deja existent")
    await get_or_404("clients", body.client_id)
    doc = body.model_dump() | {"vin": vin, "plate": body.plate.upper().strip(), "created_at": iso()}
    r = await db.vehicles.insert_one(doc)
    await audit(user, "create", "vehicle", str(r.inserted_id), vin)
    return ser(await db.vehicles.find_one({"_id": r.inserted_id}))


@router.get("/vehicles/{vid}")
async def get_vehicle(vid: str, user=Depends(require("vehicles"))):
    v = (await attach_owner([await get_or_404("vehicles", vid)]))[0]
    v["history"] = [ser(w) for w in await db.work_orders.find(
        {"vehicle_id": vid}, {"reception.photos": 0, "reception.signature": 0, "quotes": 0}).sort("created_at", -1).to_list(500)]
    return v


@router.put("/vehicles/{vid}")
async def update_vehicle(vid: str, body: VehicleIn, user=Depends(require("vehicles"))):
    doc = body.model_dump() | {"vin": body.vin.strip().upper(), "plate": body.plate.upper().strip()}
    await db.vehicles.update_one({"_id": oid(vid)}, {"$set": doc})
    await audit(user, "update", "vehicle", vid, doc["vin"])
    return ser(await get_or_404("vehicles", vid))


@router.get("/expirations")
async def expirations(days: int = 30, user=Depends(require("vehicles"))):
    from datetime import date, timedelta
    limit = (date.today() + timedelta(days=days)).isoformat()
    out = []
    for v in await attach_owner(await db.vehicles.find().to_list(5000)):
        for k in ("itp_expiry", "rca_expiry", "casco_expiry", "rovinieta_expiry"):
            if v.get(k) and v[k] <= limit:
                out.append({"vehicle_id": v["id"], "plate": v["plate"], "client_name": v["client_name"], "kind": k, "date": v[k]})
    return sorted(out, key=lambda x: x["date"])
