import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import db, raw_db, enforce_work_order_quota, get_or_404, get_settings, iso, now, oid, require, ser
from tenant_context import set_scope


router = APIRouter(prefix="/api")
ACTIVE = {"programat", "sosit", "in_lucru"}
STATUSES = ACTIVE | {"finalizat", "neprezentat", "anulat"}


class AppointmentIn(BaseModel):
    client_id: str
    vehicle_id: str
    starts_at: str
    ends_at: str
    elevator: str = ""
    mechanic_ids: List[str] = []
    advisor: str = ""
    title: str = Field(min_length=2, max_length=160)
    notes: str = ""


class AppointmentStatusIn(BaseModel):
    status: str


def normalized_datetime(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(400, "Data programării este invalidă") from exc
    if parsed.tzinfo is None:
        raise HTTPException(400, "Data programării trebuie să includă fusul orar")
    return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def valid_interval(starts_at: str, ends_at: str) -> tuple[str, str]:
    start = normalized_datetime(starts_at)
    end = normalized_datetime(ends_at)
    if start >= end:
        raise HTTPException(400, "Intervalul programării este invalid")
    return start, end


def normalized_appointment(body: AppointmentIn) -> AppointmentIn:
    start, end = valid_interval(body.starts_at, body.ends_at)
    return body.model_copy(update={"starts_at": start, "ends_at": end})


async def conflicts(body: AppointmentIn, skip_id: str = ""):
    flt = {
        "status": {"$in": list(ACTIVE)},
        "starts_at": {"$lt": body.ends_at},
        "ends_at": {"$gt": body.starts_at},
    }
    if skip_id:
        flt["_id"] = {"$ne": oid(skip_id)}
    rows = await db.appointments.find(flt).to_list(1000)
    if body.elevator and any(row.get("elevator") == body.elevator for row in rows):
        raise HTTPException(409, "Rampa/elevatorul este deja ocupat în acest interval")
    assigned = set(body.mechanic_ids)
    if assigned and any(assigned & set(row.get("mechanic_ids", [])) for row in rows):
        raise HTTPException(409, "Un mecanic selectat este deja programat în acest interval")


async def enrich(rows: list) -> list:
    cids = {row.get("client_id") for row in rows}
    vids = {row.get("vehicle_id") for row in rows}
    clients = {str(item["_id"]): item for item in await db.clients.find({"_id": {"$in": [
        oid(value) for value in cids if value
    ]}}).to_list(1000)}
    vehicles = {str(item["_id"]): item for item in await db.vehicles.find({"_id": {"$in": [
        oid(value) for value in vids if value
    ]}}).to_list(1000)}
    out = []
    for row in rows:
        item = ser(row)
        client = clients.get(row.get("client_id"), {})
        vehicle = vehicles.get(row.get("vehicle_id"), {})
        item["client_name"] = client.get("name", "")
        item["client_phone"] = client.get("phone", "")
        item["vehicle_label"] = f"{vehicle.get('plate', '')} · {vehicle.get('make', '')} {vehicle.get('model', '')}".strip()
        out.append(item)
    return out


@router.get("/appointments")
async def list_appointments(start: str, end: str, user=Depends(require("planning"))):
    start, end = valid_interval(start, end)
    rows = await db.appointments.find({"starts_at": {"$lt": end}, "ends_at": {"$gt": start}}).to_list(3000)
    return await enrich(rows)


@router.post("/appointments")
async def create_appointment(body: AppointmentIn, user=Depends(require("planning"))):
    body = normalized_appointment(body)
    client = await get_or_404("clients", body.client_id)
    vehicle = await get_or_404("vehicles", body.vehicle_id)
    if vehicle.get("client_id") != body.client_id:
        raise HTTPException(400, "Vehiculul nu aparține clientului selectat")
    await conflicts(body)
    doc = body.model_dump() | {
        "status": "programat",
        "work_order_id": "",
        "created_by": user["name"],
        "created_at": iso(),
        "updated_at": iso(),
    }
    result = await db.appointments.insert_one(doc)
    await db.notifications.insert_one({
        "kind": "appointment_confirmation",
        "appointment_id": str(result.inserted_id),
        "to": client.get("email") or client.get("phone", ""),
        "status": "simulated",
        "message": f"Programare confirmată: {body.starts_at}",
        "at": iso(),
    })
    return (await enrich([await db.appointments.find_one({"_id": result.inserted_id})]))[0]


@router.put("/appointments/{aid}")
async def update_appointment(aid: str, body: AppointmentIn, user=Depends(require("planning"))):
    body = normalized_appointment(body)
    appointment = await get_or_404("appointments", aid)
    if appointment["status"] in {"anulat", "finalizat"}:
        raise HTTPException(400, "Programarea finalizată sau anulată nu mai poate fi modificată")
    vehicle = await get_or_404("vehicles", body.vehicle_id)
    if vehicle.get("client_id") != body.client_id:
        raise HTTPException(400, "Vehiculul nu aparține clientului selectat")
    await conflicts(body, aid)
    await db.appointments.update_one({"_id": oid(aid)}, {"$set": body.model_dump() | {"updated_at": iso()}})
    return (await enrich([await get_or_404("appointments", aid)]))[0]


@router.delete("/appointments/{aid}")
async def delete_appointment(aid: str, user=Depends(require("planning"))):
    appointment = await get_or_404("appointments", aid)
    await db.notifications.delete_many({"appointment_id": aid})
    await db.appointments.delete_one({"_id": appointment["_id"]})
    await db.audit_logs.insert_one({
        "action": "delete_appointment",
        "entity": "appointment",
        "entity_id": aid,
        "detail": appointment.get("title", ""),
        "at": iso(),
        "user_id": user["id"],
    })
    return {"ok": True, "work_order_preserved": bool(appointment.get("work_order_id"))}


async def create_work_order_from_appointment(appointment: dict, user: dict) -> str:
    if appointment.get("work_order_id"):
        return appointment["work_order_id"]
    await enforce_work_order_quota()
    vehicle = await get_or_404("vehicles", appointment["vehicle_id"])
    from core import next_seq

    number = f"CL-{now().year}-{await next_seq('work_order'):05d}"
    doc = {
        "number": number,
        "client_id": appointment["client_id"],
        "vehicle_id": appointment["vehicle_id"],
        "status": "in_lucru",
        "mileage_in": int(vehicle.get("mileage", 0)),
        "complaint": appointment.get("title", "Programare service"),
        "diagnosis": "",
        "mechanic_ids": appointment.get("mechanic_ids", []),
        "elevator": appointment.get("elevator", ""),
        "promised_date": appointment["ends_at"][:10],
        "advisor": appointment.get("advisor") or user["name"],
        "reception": {
            "fuel_level": "",
            "observations": appointment.get("notes", ""),
            "accessories": [],
            "damages": [],
            "photos": {},
            "odometer_photo": None,
            "signature": "",
            "at": iso(),
            "by": user["name"],
        },
        "lines": [],
        "quotes": [],
        "qc": {},
        "created_at": iso(),
        "created_by": user["id"],
        "status_history": [{"status": "in_lucru", "at": iso(), "by": user["name"], "note": "Creat din programare"}],
    }
    result = await db.work_orders.insert_one(doc)
    work_order_id = str(result.inserted_id)
    claimed = await db.appointments.update_one(
        {"_id": appointment["_id"], "work_order_id": ""},
        {"$set": {"work_order_id": work_order_id}},
    )
    if claimed.modified_count:
        return work_order_id
    await db.work_orders.delete_one({"_id": result.inserted_id})
    current = await get_or_404("appointments", str(appointment["_id"]))
    return current["work_order_id"]


@router.post("/appointments/{aid}/status")
async def appointment_status(aid: str, body: AppointmentStatusIn, user=Depends(require("planning"))):
    if body.status not in STATUSES:
        raise HTTPException(400, "Status programare invalid")
    appointment = await get_or_404("appointments", aid)
    transitions = {
        "programat": {"sosit", "in_lucru", "neprezentat", "anulat"},
        "sosit": {"in_lucru", "anulat"},
        "in_lucru": {"finalizat", "anulat"},
        "finalizat": set(),
        "neprezentat": set(),
        "anulat": set(),
    }
    if body.status != appointment["status"] and body.status not in transitions[appointment["status"]]:
        raise HTTPException(400, "Tranziție status programare nepermisă")
    work_order_id = appointment.get("work_order_id", "")
    if body.status == "in_lucru":
        work_order_id = await create_work_order_from_appointment(appointment, user)
    await db.appointments.update_one({"_id": appointment["_id"]}, {"$set": {
        "status": body.status,
        "work_order_id": work_order_id,
        "updated_at": iso(),
    }})
    return (await enrich([await get_or_404("appointments", aid)]))[0]


@router.get("/appointments/capacity")
async def appointment_capacity(start: str, end: str, user=Depends(require("planning"))):
    start, end = valid_interval(start, end)
    settings = await get_settings()
    elevators = settings.get("elevators", [])
    rows = await db.appointments.find({
        "status": {"$in": list(ACTIVE)},
        "starts_at": {"$lt": end},
        "ends_at": {"$gt": start},
    }).to_list(3000)
    start_at = datetime.fromisoformat(start)
    end_at = datetime.fromisoformat(end)
    used_minutes = 0
    for row in rows:
        appointment_start = datetime.fromisoformat(row["starts_at"])
        appointment_end = datetime.fromisoformat(row["ends_at"])
        overlap = min(end_at, appointment_end) - max(start_at, appointment_start)
        used_minutes += max(0, round(overlap.total_seconds() / 60))
    days = max(1, (end_at.date() - start_at.date()).days)
    total_minutes = max(1, len(elevators) * 8 * 60 * days)
    return {"elevators": elevators, "count": len(rows), "occupancy": min(100, round(used_minutes / total_minutes * 100))}


async def send_reminders() -> None:
    lower = normalized_datetime((now() + timedelta(hours=23)).isoformat())
    upper = normalized_datetime((now() + timedelta(hours=25)).isoformat())
    rows = await db.appointments.find({"status": "programat", "starts_at": {"$gte": lower, "$lte": upper}}).to_list(1000)
    for appointment in rows:
        if await db.notifications.find_one({"kind": "appointment_reminder", "appointment_id": str(appointment["_id"])}):
            continue
        client = await db.clients.find_one({"_id": oid(appointment["client_id"])})
        await db.notifications.insert_one({
            "kind": "appointment_reminder",
            "appointment_id": str(appointment["_id"]),
            "to": (client or {}).get("email") or (client or {}).get("phone", ""),
            "status": "simulated",
            "message": f"Reminder programare în 24h: {appointment['starts_at']}",
            "at": iso(),
        })


async def send_reminders_all_tenants() -> None:
    branches = await raw_db.branches.find({"status": "ACTIVE"}).to_list(5000)
    for branch in branches:
        try:
            set_scope({"tenant_id": branch["tenant_id"], "branch_id": branch["_id"], "system_scope": True})
            await send_reminders()
        except Exception as error:  # noqa: BLE001
            await raw_db.cron_errors.insert_one({"job": "appointment-reminders", "tenant_id": branch["tenant_id"], "branch_id": branch["_id"], "error": str(error)[:1500], "at": iso()})


@router.post("/cron/appointments/reminders")
async def appointment_reminder_cron(request: Request, background: BackgroundTasks):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    auth = request.headers.get("Authorization", "")
    secret = os.environ["WEBHOOK_CRON_SECRET"]
    if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], secret):
        raise HTTPException(401, "Unauthorized")
    run_id = request.headers.get("X-Webhook-Id", "")
    if run_id and await db.cron_runs.find_one({"_id": run_id}):
        return {"ok": True, "duplicate": True}
    if run_id:
        await db.cron_runs.insert_one({"_id": run_id, "job": "appointment-reminders", "at": iso()})
    background.add_task(send_reminders_all_tenants)
    return {"ok": True}