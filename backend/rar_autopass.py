import hashlib

from anaf_service import enc
from core import db, iso


CONFIG_ID = "primary"
DEFAULT_BRANCH = "Punct de lucru principal"
ENV_LABELS = {
    "test": "Test / Sandbox",
    "production": "Producție",
}


async def get_config() -> dict:
    doc = await db.rar_autopass_config.find_one({"_id": CONFIG_ID})
    cfg = {key: value for key, value in (doc or {}).items() if key != "_id"}
    cfg.setdefault("branch_name", DEFAULT_BRANCH)
    cfg.setdefault("authorization_code", "")
    cfg.setdefault("service_cui", "")
    cfg.setdefault("environment", "test")
    cfg.setdefault("api_contract_configured", False)
    cfg.setdefault("created_at", "")
    cfg.setdefault("updated_at", "")
    return cfg


def public_config(cfg: dict, company: dict) -> dict:
    configured = bool(cfg.get("authorization_code") and cfg.get("service_cui"))
    has_token = bool(cfg.get("api_token"))
    contract_ready = bool(cfg.get("api_contract_configured"))
    if not configured:
        status_text = "Configurați codul de autorizație RAR și CUI-ul service-ului"
    elif not contract_ready:
        status_text = "Coada RAR este pregătită; contractul API oficial nu este configurat"
    elif not has_token:
        status_text = "Contractul API este configurat, dar lipsește tokenul de acces"
    else:
        status_text = "Configurația este completă; activarea transmiterii necesită validare manuală"
    return {
        "branch_id": CONFIG_ID,
        "branch_name": cfg.get("branch_name", DEFAULT_BRANCH),
        "authorization_code": cfg.get("authorization_code", ""),
        "service_cui": cfg.get("service_cui") or company.get("cui", ""),
        "environment": cfg.get("environment", "test"),
        "has_api_token": has_token,
        "api_contract_configured": contract_ready,
        "external_transport_active": False,
        "status_text": status_text,
        "updated_at": cfg.get("updated_at", ""),
    }


async def save_config(values: dict) -> dict:
    update = {
        "branch_name": values["branch_name"].strip() or DEFAULT_BRANCH,
        "authorization_code": values["authorization_code"].strip(),
        "service_cui": values["service_cui"].strip().upper(),
        "environment": values["environment"],
        "updated_at": iso(),
    }
    if values.get("api_token"):
        update["api_token"] = enc(values["api_token"].strip())
    await db.rar_autopass_config.update_one(
        {"_id": CONFIG_ID},
        {"$set": update, "$setOnInsert": {"created_at": iso()}},
        upsert=True,
    )
    return await get_config()


def operations_summary(lines: list) -> str:
    entries = []
    for line in lines:
        description = str(line.get("description", "")).strip()
        if not description:
            continue
        qty = line.get("qty", 0)
        unit = line.get("unit", "")
        entries.append(f"{description} ({qty} {unit})".strip())
    return "; ".join(entries)[:1500]


async def queue_submission(work_order: dict, invoice: dict, trigger: str) -> None:
    vehicle = await db.vehicles.find_one({"_id": invoice.get("vehicle_id")})
    if not vehicle:
        vehicle = await db.vehicles.find_one({"_id": work_order.get("vehicle_id")})
    cfg = await get_config()
    vin = str((vehicle or {}).get("vin", "")).strip().upper()
    mileage = work_order.get("mileage_in")
    requirements = []
    if len(vin) != 17:
        requirements.append("VIN valid cu 17 caractere")
    if not isinstance(mileage, int) or mileage < 0:
        requirements.append("kilometraj de intrare valid")
    if not cfg.get("authorization_code"):
        requirements.append("cod autorizație RAR")
    if not cfg.get("service_cui"):
        requirements.append("CUI service")
    if not cfg.get("api_contract_configured"):
        requirements.append("contract API RAR")
    if not cfg.get("api_token"):
        requirements.append("token de acces RAR")

    invoice_ref = f"{invoice.get('series', '')}{invoice.get('number', '')}"
    completion = work_order.get("closed_at") or work_order.get("invoiced_at") or iso()
    payload = {
        "branch_rar_authorization": cfg.get("authorization_code", ""),
        "vehicle": {
            "vin": vin,
            "plate_number": (vehicle or {}).get("plate", ""),
        },
        "odometer_record": {
            "value": mileage,
            "unit": "KM",
            "reading_timestamp": work_order.get("reception", {}).get("at", ""),
            "odometer_image_url": work_order.get("reception", {}).get("odometer_photo"),
        },
        "service_record": {
            "work_order_id": str(work_order["_id"]),
            "invoice_number": invoice_ref,
            "completion_date": str(completion)[:10],
            "operations_summary": operations_summary(work_order.get("lines", [])),
        },
    }
    work_order_id = str(work_order["_id"])
    invoice_id = str(invoice["_id"])
    idempotency_key = hashlib.sha256(
        f"{work_order_id}:{invoice_id}".encode()
    ).hexdigest()
    state = "blocked" if requirements else "queued"
    update = {
        "work_order_id": work_order_id,
        "work_order_number": work_order.get("number", ""),
        "invoice_id": invoice_id,
        "invoice_number": invoice_ref,
        "branch_id": CONFIG_ID,
        "environment": cfg.get("environment", "test"),
        "payload": payload,
        "state": state,
        "blocked_requirements": requirements,
        "updated_at": iso(),
    }
    await db.rar_autopass_outbox.update_one(
        {"idempotency_key": idempotency_key},
        {
            "$set": update,
            "$setOnInsert": {
                "idempotency_key": idempotency_key,
                "attempts": 0,
                "created_at": iso(),
            },
            "$addToSet": {"trigger_events": trigger},
        },
        upsert=True,
    )


async def work_order_status(work_order_id: str) -> dict | None:
    item = await db.rar_autopass_outbox.find_one(
        {"work_order_id": work_order_id},
        {"_id": 0, "payload": 0, "idempotency_key": 0},
    )
    return item