from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from anexa5 import build_csv, build_pdf, build_xlsx
from core import db, require
from rar_autopass import get_config


router = APIRouter(prefix="/api")
QC_KEYS = [
    "noxe", "frane", "geometrie", "faruri_geamuri_parbrize",
    "parametri_reglaje", "etanșeitate", "proba_drum",
]
OLD_KEYS = {
    "noxe": "niveluri",
    "frane": "frane",
    "geometrie": "directie",
    "faruri_geamuri_parbrize": "lumini",
    "parametri_reglaje": "suspensie",
    "etanșeitate": "niveluri",
    "proba_drum": "test_drive",
}
CODE_MAP = {"ok": "C", "nok": "N", "na": "NA"}


def code_for(items: dict, key: str) -> str:
    value = items.get(key) or items.get(OLD_KEYS[key], "NA")
    return CODE_MAP.get(value, value if value in ("C", "N", "NA") else "NA")


async def anexa_rows(start: str, end: str, inspector: str = "") -> list:
    if not start or not end:
        raise HTTPException(400, "Selectați data de început și data de sfârșit")
    if start > end:
        raise HTTPException(400, "Intervalul de date este invalid")
    docs = await db.work_orders.find({
        "qc.at": {"$gte": f"{start}T00:00:00", "$lte": f"{end}T23:59:59.999999+00:00"},
    }).sort("qc.at", 1).to_list(5000)
    client_ids = {item.get("client_id") for item in docs}
    vehicle_ids = {item.get("vehicle_id") for item in docs}
    clients = {str(item["_id"]): item for item in await db.clients.find({"_id": {"$in": [
        ObjectId(value) for value in client_ids if value
    ]}}).to_list(5000)}
    vehicles = {str(item["_id"]): item for item in await db.vehicles.find({"_id": {"$in": [
        ObjectId(value) for value in vehicle_ids if value
    ]}}).to_list(5000)}
    cfg = await get_config()
    rows = []
    for index, work_order in enumerate(docs, 1):
        qc = work_order.get("qc", {})
        name = qc.get("inspector_name") or qc.get("by", "")
        if inspector and name != inspector:
            continue
        client = clients.get(work_order.get("client_id"), {})
        vehicle = vehicles.get(work_order.get("vehicle_id"), {})
        items = qc.get("items", {})
        row = {
            "nr": len(rows) + 1,
            "order": work_order.get("number", ""),
            "date": str(qc.get("at", ""))[:10],
            "vehicle": vehicle.get("plate") or vehicle.get("vin", ""),
            "noxe": code_for(items, "noxe"),
            "frane": code_for(items, "frane"),
            "geometrie": code_for(items, "geometrie"),
            "faruri": code_for(items, "faruri_geamuri_parbrize"),
            "parametri": code_for(items, "parametri_reglaje"),
            "etanseitate": code_for(items, "etanșeitate"),
            "proba": code_for(items, "proba_drum"),
            "presenter": client.get("representative") or client.get("name", ""),
            "inspector": f"{cfg['branch_name']} · {name} · semnătură înregistrată",
        }
        row["columns"] = [
            "nr", "order", "date", "vehicle", "noxe", "frane", "geometrie", "faruri",
            "parametri", "etanseitate", "proba", "presenter", "inspector",
        ]
        rows.append(row)
    return rows


@router.get("/reports/final-inspections")
async def final_inspections(start: str, end: str, inspector: str = "", user=Depends(require("reports"))):
    cfg = await get_config()
    return {"branch": cfg["branch_name"], "rows": await anexa_rows(start, end, inspector)}


@router.get("/reports/final-inspections/inspectors")
async def inspection_inspectors(user=Depends(require("reports"))):
    rows = await db.work_orders.aggregate([
        {"$match": {"qc.at": {"$exists": True}}},
        {"$project": {"name": {"$ifNull": ["$qc.inspector_name", "$qc.by"]}}},
        {"$match": {"name": {"$ne": ""}}},
        {"$group": {"_id": "$name"}},
    ]).to_list(1000)
    return sorted(row["_id"] for row in rows if row.get("_id"))


@router.get("/reports/final-inspections/{kind}")
async def export_final_inspections(kind: str, start: str, end: str, inspector: str = "", user=Depends(require("reports"))):
    rows = await anexa_rows(start, end, inspector)
    branch = (await get_config())["branch_name"]
    if kind == "pdf":
        content = build_pdf(rows, start, end, branch)
        media_type = "application/pdf"
    if kind == "csv":
        content = build_csv(rows)
        media_type = "text/csv; charset=utf-8"
    if kind == "xlsx":
        content = build_xlsx(rows)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if kind not in {"pdf", "csv", "xlsx"}:
        raise HTTPException(404, "Format export invalid")
    filename = f"anexa5_{start}_{end}.{kind}"
    return Response(content, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
    })