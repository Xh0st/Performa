from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

import os
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from fastapi import Request, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
JWT_ALG = "HS256"

ROLES = ["admin", "director", "sef_service", "consilier", "receptioner", "magazioner", "mecanic",
         "electrician", "tinichigiu", "vopsitor", "contabil", "casier", "manager_flota", "client"]
TECH = ["mecanic", "electrician", "tinichigiu", "vopsitor"]
MGMT = ["admin", "director", "sef_service"]

MODULE_ROLES = {
    "dashboard": MGMT + ["consilier", "contabil"],
    "crm": MGMT + ["consilier", "receptioner", "contabil", "casier", "manager_flota"],
    "vehicles": MGMT + ["consilier", "receptioner", "manager_flota"] + TECH,
    "reception": MGMT + ["consilier", "receptioner"],
    "workorders": MGMT + ["consilier", "receptioner", "magazioner", "manager_flota"] + TECH,
    "mechanics": MGMT + TECH,
    "stock": MGMT + ["magazioner", "contabil", "consilier"],
    "invoices": MGMT + ["contabil", "casier", "consilier"],
    "payments": MGMT + ["contabil", "casier"],
    "ai": MGMT + ["consilier", "receptioner"] + TECH,
    "planning": MGMT + ["consilier", "receptioner"],
    "reports": MGMT + ["contabil", "consilier"],
    "warranties": MGMT + ["consilier", "receptioner", "contabil", "magazioner"],
    "settings": ["admin", "director"],
    "users": ["admin"],
}

WO_STATUSES = ["noua", "diagnosticare", "asteapta_oferta", "aprobata", "in_lucru", "asteapta_piese",
               "finalizata", "facturata", "inchisa"]


def now():
    return datetime.now(timezone.utc)


def iso():
    return now().isoformat()


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p: str, h: str) -> bool:
    return bcrypt.checkpw(p.encode(), h.encode())


def make_token(user_id: str, kind: str, minutes: int) -> str:
    payload = {"sub": user_id, "type": kind, "exp": now() + timedelta(minutes=minutes)}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALG)


def ser(doc):
    if doc is None:
        return None
    d = {k: v for k, v in doc.items() if k not in ("_id", "password_hash")}
    d["id"] = str(doc["_id"])
    return d


def oid(s: str) -> ObjectId:
    if not s or not ObjectId.is_valid(s):
        raise HTTPException(404, "Not found")
    return ObjectId(s)


async def get_or_404(coll, id_: str) -> dict:
    """Internal helper: raw Mongo doc for server-side use; endpoints must wrap with ser()."""
    found = await db[coll].find_one({"_id": oid(id_)})
    if not found:
        raise HTTPException(404, "Not found")
    raw: dict = dict(found)
    return raw


def permissions_for(role: str):
    return [m for m, roles in MODULE_ROLES.items() if role in roles]


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(401, "Invalid token type")
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user or not user.get("active", True):
        raise HTTPException(401, "User not found")
    u = ser(user)
    u["permissions"] = permissions_for(u["role"])
    return u


def require(module: str):
    async def dep(user: dict = Depends(get_current_user)):
        if user["role"] not in MODULE_ROLES[module]:
            raise HTTPException(403, "Acces interzis pentru acest modul")
        return user
    return dep


async def next_seq(name: str) -> int:
    r = await db.counters.find_one_and_update({"_id": name}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
    return r["seq"]


async def audit(user: dict, action: str, entity: str, entity_id: str = "", details: str = ""):
    await db.audit_logs.insert_one({"user_id": user.get("id"), "user_email": user.get("email"), "action": action,
                                    "entity": entity, "entity_id": entity_id, "details": details, "at": iso()})


async def get_settings() -> dict:
    s = await db.settings.find_one({"_id": "company"})
    return {k: v for k, v in (s or {}).items() if k != "_id"}


def calc_totals(lines: list):
    net = vat = 0.0
    for ln in lines:
        ln_net = round(ln["qty"] * ln["unit_price"] * (1 - ln.get("discount", 0) / 100), 2)
        ln_vat = round(ln_net * ln.get("vat_rate", 21) / 100, 2)
        ln["net"], ln["vat"], ln["gross"] = ln_net, ln_vat, round(ln_net + ln_vat, 2)
        net += ln_net
        vat += ln_vat
    by_type = {}
    for ln in lines:
        by_type[ln["type"]] = round(by_type.get(ln["type"], 0) + ln["net"], 2)
    return {"net": round(net, 2), "vat": round(vat, 2), "gross": round(net + vat, 2), "by_type": by_type}
