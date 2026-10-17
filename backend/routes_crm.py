import re
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from core import db, ser, oid, iso, require, audit, get_or_404
from vehicle_catalog import MAKES, decode_vin

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


def search_filter(q: str, fields):
    rx = {"$regex": re.escape(q), "$options": "i"}
    return {"$or": [{f: rx} for f in fields]}


@router.get("/clients")
async def list_clients(q: str = "", user=Depends(require("crm"))):
    flt = search_filter(q, ["name", "cnp", "cui", "phone", "email"]) if q else {}
    clients = await db.clients.find(flt).sort("name", 1).to_list(1000)
    counts = {}
    async for v in db.vehicles.aggregate([{"$group": {"_id": "$client_id", "n": {"$sum": 1}}}]):
        counts[v["_id"]] = v["n"]
    out = []
    for c in clients:
        d = ser(c)
        d["vehicle_count"] = counts.get(d["id"], 0)
        out.append(d)
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
    c["vehicles"] = [ser(v) for v in await db.vehicles.find({"client_id": cid}).to_list(500)]
    c["work_orders"] = [ser(w) for w in await db.work_orders.find(
        {"client_id": cid}, {"reception.photos": 0, "reception.signature": 0, "quotes": 0}).sort("created_at", -1).to_list(500)]
    c["invoices"] = [ser(i) for i in await db.invoices.find({"client_id": cid}, {"efactura.xml": 0}).sort("issue_date", -1).to_list(500)]
    return c


@router.put("/clients/{cid}")
async def update_client(cid: str, body: ClientIn, user=Depends(require("crm"))):
    validate_client(body)
    await db.clients.update_one({"_id": oid(cid)}, {"$set": body.model_dump()})
    await audit(user, "update", "client", cid, body.name)
    return ser(await get_or_404("clients", cid))


@router.delete("/clients/{cid}")
async def delete_client(cid: str, user=Depends(require("crm"))):
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
async def list_vehicles(q: str = "", client_id: str = "", user=Depends(require("vehicles"))):
    flt = search_filter(q, ["vin", "plate", "make", "model"]) if q else {}
    if client_id:
        flt["client_id"] = client_id
    return await attach_owner(await db.vehicles.find(flt).sort("plate", 1).to_list(2000))


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
