from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from core import db, get_or_404, iso, next_seq, oid, require, ser
from warranty_pdf import build_certificate


router = APIRouter(prefix="/api")


class ClaimLine(BaseModel):
    source_line_id: str
    qty: float


class ClaimIn(BaseModel):
    invoice_id: str
    description: str
    lines: List[ClaimLine]


class ClaimUpdateIn(BaseModel):
    technical_result: str = "in_asteptare"
    supplier_return_status: str = "nu_este_cazul"
    supplier_return_id: str = ""
    resolution: str = "in_analiza"
    notes: str = ""


@router.get("/warranties")
async def list_warranties(status: str = "active", user=Depends(require("warranties"))):
    today = date.today().isoformat()
    rows = [ser(item) for item in await db.warranty_certificates.find().sort("created_at", -1).to_list(2000)]
    for row in rows:
        row["active_lines"] = [line for line in row["lines"] if line["valid_to"] >= today]
        row["status"] = "active" if row["active_lines"] else "expired"
    return [row for row in rows if not status or row["status"] == status]


@router.get("/warranties/invoices/{iid}")
async def certificate_by_invoice(iid: str, user=Depends(require("invoices"))):
    certificate = await db.warranty_certificates.find_one({"invoice_id": iid})
    if not certificate:
        raise HTTPException(404, "Certificatul de garanție nu există")
    return ser(certificate)


@router.get("/warranties/invoices/{iid}/certificate")
async def certificate_pdf(iid: str, user=Depends(require("invoices"))):
    certificate = await db.warranty_certificates.find_one({"invoice_id": iid})
    if not certificate:
        raise HTTPException(404, "Certificatul de garanție nu există")
    content = build_certificate(certificate)
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{certificate["number"]}.pdf"',
    })


@router.get("/warranty-claims")
async def list_claims(user=Depends(require("warranties"))):
    return [ser(item) for item in await db.warranty_claims.find().sort("created_at", -1).to_list(2000)]


@router.post("/warranty-claims")
async def create_claim(body: ClaimIn, user=Depends(require("warranties"))):
    if not body.description.strip() or not body.lines:
        raise HTTPException(400, "Descrierea și cel puțin o linie sunt obligatorii")
    certificate = await db.warranty_certificates.find_one({"invoice_id": body.invoice_id})
    if not certificate:
        raise HTTPException(400, "Factura nu are certificat de garanție")
    active = {line["source_line_id"]: line for line in certificate["lines"] if line["valid_to"] >= date.today().isoformat()}
    claim_lines = []
    for request_line in body.lines:
        source = active.get(request_line.source_line_id)
        if not source or request_line.qty <= 0 or request_line.qty > source["qty"] + 1e-6:
            raise HTTPException(400, "Linie neacoperită sau cantitate invalidă pentru garanție")
        claim_lines.append({**source, "qty": request_line.qty})
    invoice = await get_or_404("invoices", body.invoice_id)
    sequence = await next_seq("warranty_claim")
    claim_number = f"DG-{date.today().year}-{sequence:05d}"
    work_sequence = await next_seq("work_order")
    work_number = f"GAR-{date.today().year}-{work_sequence:05d}"
    work_order = {
        "number": work_number,
        "client_id": certificate["client_id"],
        "vehicle_id": certificate["vehicle_id"],
        "status": "noua",
        "mileage_in": invoice.get("mileage", 0) or 0,
        "complaint": f"Reclamație garanție {claim_number}: {body.description.strip()}",
        "diagnosis": "",
        "mechanic_ids": [],
        "elevator": "",
        "promised_date": "",
        "advisor": user["name"],
        "reception": {"fuel_level": "", "observations": "Dosar garanție", "accessories": [], "damages": [], "photos": {}, "signature": "", "at": iso(), "by": user["name"]},
        "lines": [{"id": f"warranty-{index}", "type": "labor" if line["label"] == "Manoperă" else "part", "description": line["description"], "qty": line["qty"], "unit_price": 0, "unit": "ore" if line["label"] == "Manoperă" else "buc", "discount": 0, "vat_rate": 0, "product_id": line.get("product_id", ""), "code": "", "warranty_source_line_id": line["source_line_id"]} for index, line in enumerate(claim_lines)],
        "quotes": [], "qc": {}, "is_warranty": True, "warranty_claim_number": claim_number, "created_at": iso(), "created_by": user["id"], "status_history": [{"status": "noua", "at": iso(), "by": user["name"], "note": "Creată din reclamație garanție"}],
    }
    result = await db.work_orders.insert_one(work_order)
    claim = {"number": claim_number, "certificate_id": str(certificate["_id"]), "invoice_id": body.invoice_id, "invoice_ref": certificate["invoice_ref"], "client_name": certificate["client_name"], "vehicle_label": certificate["vehicle_label"], "description": body.description.strip(), "lines": claim_lines, "work_order_id": str(result.inserted_id), "work_order_number": work_number, "technical_result": "in_asteptare", "supplier_return_status": "nu_este_cazul", "supplier_return_id": "", "resolution": "in_analiza", "notes": "", "created_by": user["name"], "created_at": iso(), "updated_at": iso()}
    created = await db.warranty_claims.insert_one(claim)
    return ser(await db.warranty_claims.find_one({"_id": created.inserted_id}))


@router.put("/warranty-claims/{cid}")
async def update_claim(cid: str, body: ClaimUpdateIn, user=Depends(require("warranties"))):
    if body.technical_result not in {"in_asteptare", "conform", "neconform"}:
        raise HTTPException(400, "Rezultat tehnic invalid")
    if body.supplier_return_status not in {"nu_este_cazul", "in_asteptare", "trimis", "acceptat", "respins"}:
        raise HTTPException(400, "Status retur furnizor invalid")
    if body.resolution not in {"in_analiza", "admis_inlocuit", "admis_rambursat", "respins"}:
        raise HTTPException(400, "Soluție invalidă")
    await get_or_404("warranty_claims", cid)
    update = body.model_dump() | {"updated_at": iso(), "updated_by": user["name"]}
    await db.warranty_claims.update_one({"_id": oid(cid)}, {"$set": update})
    return ser(await get_or_404("warranty_claims", cid))