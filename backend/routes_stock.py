import re
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from core import db, ser, oid, iso, require, audit, get_or_404, next_seq, now

router = APIRouter(prefix="/api")


class ProductIn(BaseModel):
    code: str
    name: str
    oe_code: str = ""
    aftermarket_code: str = ""
    brand: str = ""
    category: str = "piese"
    unit: str = "buc"
    location: str = ""
    warehouse: str = "Depozit Central"
    sale_price: float = 0
    min_stock: float = 0
    vat_rate: float = 21
    warranty_months: int = 24


class SupplierIn(BaseModel):
    name: str
    cui: str = ""
    reg_com: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    api_enabled: bool = False


class NirLine(BaseModel):
    product_id: str
    qty: float
    unit_cost: float
    lot: str = ""


class NirIn(BaseModel):
    supplier_id: str
    invoice_no: str = ""
    aviz_no: str = ""
    date: str = ""
    warehouse: str = "Depozit Central"
    lines: List[NirLine]


class ReturnLine(BaseModel):
    product_id: str
    qty: float


class ReturnIn(BaseModel):
    supplier_id: str
    nir_id: str = ""
    reason: str = ""
    date: str = ""
    lines: List[ReturnLine]


@router.get("/products")
async def list_products(q: str = "", low: bool = False, user=Depends(require("workorders"))):
    flt = {}
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        flt = {"$or": [{"code": rx}, {"name": rx}, {"oe_code": rx}, {"aftermarket_code": rx}, {"brand": rx}]}
    items = [ser(p) for p in await db.products.find(flt).sort("name", 1).to_list(5000)]
    return [p for p in items if p["stock_qty"] <= p.get("min_stock", 0)] if low else items


@router.post("/products")
async def create_product(body: ProductIn, user=Depends(require("stock"))):
    if await db.products.find_one({"code": body.code}):
        raise HTTPException(400, "Cod produs deja existent")
    r = await db.products.insert_one(body.model_dump() | {"stock_qty": 0, "avg_cost": 0, "created_at": iso()})
    await audit(user, "create", "product", str(r.inserted_id), body.code)
    return ser(await db.products.find_one({"_id": r.inserted_id}))


@router.put("/products/{pid}")
async def update_product(pid: str, body: ProductIn, user=Depends(require("stock"))):
    await db.products.update_one({"_id": oid(pid)}, {"$set": body.model_dump()})
    return ser(await get_or_404("products", pid))


@router.get("/products/{pid}/moves")
async def product_moves(pid: str, user=Depends(require("stock"))):
    await get_or_404("products", pid)
    return {"moves": [ser(m) for m in await db.stock_moves.find({"product_id": pid}).sort("at", -1).to_list(500)],
            "lots": [ser(lot) for lot in await db.stock_lots.find({"product_id": pid, "qty_remaining": {"$gt": 0}}).sort("date", 1).to_list(500)]}


@router.get("/suppliers")
async def list_suppliers(user=Depends(require("stock"))):
    return [ser(s) for s in await db.suppliers.find().sort("name", 1).to_list(500)]


@router.post("/suppliers")
async def create_supplier(body: SupplierIn, user=Depends(require("stock"))):
    r = await db.suppliers.insert_one(body.model_dump() | {"created_at": iso()})
    return ser(await db.suppliers.find_one({"_id": r.inserted_id}))


async def receive_stock(product_id: str, qty: float, unit_cost: float, ref: str, date: str, lot: str = ""):
    p = await get_or_404("products", product_id)
    old_q, old_c = max(p.get("stock_qty", 0), 0), p.get("avg_cost", 0)
    new_avg = round((old_q * old_c + qty * unit_cost) / (old_q + qty), 4) if old_q + qty else unit_cost
    await db.products.update_one({"_id": p["_id"]}, {"$inc": {"stock_qty": qty}, "$set": {"avg_cost": new_avg, "last_cost": unit_cost}})
    await db.stock_lots.insert_one({"product_id": product_id, "qty_in": qty, "qty_remaining": qty, "unit_cost": unit_cost,
                                    "date": date, "ref": ref, "lot": lot})
    await db.stock_moves.insert_one({"product_id": product_id, "kind": "in", "qty": qty, "unit_cost": unit_cost, "ref": ref, "at": date})


async def consume_fifo(product_id: str, qty: float, ref: str) -> float:
    p = await db.products.find_one({"_id": oid(product_id)})
    if not p:
        return 0.0
    remaining, cost = qty, 0.0
    async for lot in db.stock_lots.find({"product_id": product_id, "qty_remaining": {"$gt": 0}}).sort("date", 1):
        if remaining <= 0:
            break
        take = min(remaining, lot["qty_remaining"])
        await db.stock_lots.update_one({"_id": lot["_id"]}, {"$inc": {"qty_remaining": -take}})
        cost += take * lot["unit_cost"]
        remaining -= take
    if remaining > 0:
        cost += remaining * p.get("avg_cost", 0)
    await db.products.update_one({"_id": p["_id"]}, {"$inc": {"stock_qty": -qty}})
    await db.stock_moves.insert_one({"product_id": product_id, "kind": "out", "qty": qty, "unit_cost": round(cost / qty, 4) if qty else 0,
                                     "ref": ref, "at": iso()})
    return round(cost, 2)


async def consume_for_return(product_id: str, qty: float, ref: str, nir_number: str = "") -> float:
    lot = await db.stock_lots.find_one({"product_id": product_id, "ref": nir_number, "qty_remaining": {"$gt": 0}}) if nir_number else None
    take = min(qty, lot["qty_remaining"]) if lot else 0
    cost = 0.0
    if take > 0:
        await db.stock_lots.update_one({"_id": lot["_id"]}, {"$inc": {"qty_remaining": -take}})
        await db.products.update_one({"_id": oid(product_id)}, {"$inc": {"stock_qty": -take}})
        await db.stock_moves.insert_one({"product_id": product_id, "kind": "out", "qty": take, "unit_cost": lot["unit_cost"], "ref": ref, "at": iso()})
        cost = take * lot["unit_cost"]
    if qty - take > 0:
        cost += await consume_fifo(product_id, round(qty - take, 4), ref)
    return round(cost, 2)


async def returned_by_nir(nid: str) -> dict:
    out = {}
    async for r in db.supplier_returns.find({"nir_id": nid}, {"lines": 1}):
        for ln in r["lines"]:
            out[ln["product_id"]] = round(out.get(ln["product_id"], 0) + ln["qty"], 4)
    return out


@router.get("/nirs")
async def list_nirs(user=Depends(require("stock"))):
    return [ser(n) for n in await db.nirs.find().sort("date", -1).to_list(1000)]


@router.get("/nirs/{nid}")
async def get_nir(nid: str, user=Depends(require("stock"))):
    n = ser(await get_or_404("nirs", nid))
    returned = await returned_by_nir(nid)
    for ln in n["lines"]:
        ln["returned_qty"] = returned.get(ln["product_id"], 0)
    return n


@router.get("/supplier-returns")
async def list_returns(user=Depends(require("stock"))):
    return [ser(r) for r in await db.supplier_returns.find().sort("created_at", -1).to_list(1000)]


@router.get("/supplier-returns/{rid}")
async def get_return(rid: str, user=Depends(require("stock"))):
    return ser(await get_or_404("supplier_returns", rid))


@router.post("/supplier-returns")
async def create_return(body: ReturnIn, user=Depends(require("stock"))):
    sup = await get_or_404("suppliers", body.supplier_id)
    if not body.reason.strip():
        raise HTTPException(400, "Motivul returului este obligatoriu")
    qty_by = {}
    for ln in body.lines:
        if ln.qty <= 0:
            raise HTTPException(400, "Cantitate invalidă")
        qty_by[ln.product_id] = round(qty_by.get(ln.product_id, 0) + ln.qty, 4)
    if not qty_by:
        raise HTTPException(400, "Returul nu are linii")
    nir, nir_lines = None, {}
    if body.nir_id:
        nir = await get_or_404("nirs", body.nir_id)
        if nir["supplier_id"] != body.supplier_id:
            raise HTTPException(400, "NIR-ul selectat nu aparține furnizorului")
        returned = await returned_by_nir(body.nir_id)
        for ln in nir["lines"]:
            e = nir_lines.setdefault(ln["product_id"], {"qty": 0.0, "unit_cost": ln["unit_cost"]})
            e["qty"] += ln["qty"]
    products = {}
    for pid, qty in qty_by.items():
        p = await get_or_404("products", pid)
        products[pid] = p
        if qty > p.get("stock_qty", 0) + 1e-6:
            raise HTTPException(400, f"{p['code']}: stoc insuficient ({p.get('stock_qty', 0)} disponibil)")
        if nir:
            if pid not in nir_lines:
                raise HTTPException(400, f"{p['code']} nu se află pe NIR {nir['number']}")
            avail = round(nir_lines[pid]["qty"] - returned.get(pid, 0), 4)
            if qty > avail + 1e-6:
                raise HTTPException(400, f"{p['code']}: cantitate maximă returnabilă din NIR {avail}")
    seq = await next_seq("supplier_return")
    number = f"RET-{now().year}-{seq:05d}"
    lines = []
    for pid, qty in qty_by.items():
        p = products[pid]
        cost = await consume_for_return(pid, qty, number, nir["number"] if nir else "")
        unit_cost = nir_lines[pid]["unit_cost"] if nir else round(cost / qty, 4)
        val = round(qty * unit_cost, 2)
        lines.append({"product_id": pid, "code": p["code"], "name": p["name"], "unit": p.get("unit", "buc"), "qty": qty, "unit_cost": unit_cost,
                      "value": val, "vat": round(val * p.get("vat_rate", 21) / 100, 2), "stock_cost": cost})
    doc = {"number": number, "supplier_id": body.supplier_id, "supplier_name": sup["name"], "supplier_cui": sup.get("cui", ""),
           "nir_id": body.nir_id, "nir_number": nir["number"] if nir else "", "nir_invoice_no": nir.get("invoice_no", "") if nir else "",
           "reason": body.reason.strip(), "date": body.date or iso(), "lines": lines, "total": round(sum(x["value"] for x in lines), 2),
           "total_vat": round(sum(x["vat"] for x in lines), 2), "created_by": user["name"], "created_at": iso()}
    r = await db.supplier_returns.insert_one(doc)
    await audit(user, "create", "supplier_return", str(r.inserted_id), number)
    return ser(await db.supplier_returns.find_one({"_id": r.inserted_id}))


@router.post("/nirs")
async def create_nir(body: NirIn, user=Depends(require("stock"))):
    if not body.lines:
        raise HTTPException(400, "NIR fără linii")
    if not body.invoice_no and not body.aviz_no:
        raise HTTPException(400, "Introduceți numărul facturii sau al avizului")
    sup = await get_or_404("suppliers", body.supplier_id)
    seq = await next_seq("nir")
    number = f"NIR-{now().year}-{seq:05d}"
    date = body.date or iso()
    lines, total = [], 0.0
    for ln in body.lines:
        if ln.qty <= 0:
            raise HTTPException(400, "Cantitate invalidă")
        p = await get_or_404("products", ln.product_id)
        val = round(ln.qty * ln.unit_cost, 2)
        lines.append({"product_id": ln.product_id, "code": p["code"], "name": p["name"], "unit": p.get("unit", "buc"),
                      "qty": ln.qty, "unit_cost": ln.unit_cost, "value": val, "vat": round(val * p.get("vat_rate", 21) / 100, 2), "lot": ln.lot})
        total += val
    for ln in body.lines:
        await receive_stock(ln.product_id, ln.qty, ln.unit_cost, number, date, ln.lot)
    doc = {"number": number, "supplier_id": body.supplier_id, "supplier_name": sup["name"], "invoice_no": body.invoice_no,
           "aviz_no": body.aviz_no, "date": date, "warehouse": body.warehouse, "lines": lines, "total": round(total, 2),
           "total_vat": round(sum(x["vat"] for x in lines), 2), "created_by": user["name"], "created_at": iso()}
    r = await db.nirs.insert_one(doc)
    await audit(user, "create", "nir", str(r.inserted_id), number)
    return ser(await db.nirs.find_one({"_id": r.inserted_id}))
