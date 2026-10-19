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
from tenant_context import GLOBAL_COLLECTIONS, OPERATIONAL_COLLECTIONS, current_scope, set_scope

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
raw_db = client[os.environ["DB_NAME"]]
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
FULL_ONLY_MODULES = {"planning", "stock"}
FULL_ONLY_PREFIXES = (
    "/api/appointments",
    "/api/products",
    "/api/suppliers",
    "/api/nirs",
    "/api/supplier-returns",
    "/api/efactura",
    "/api/rar-autopass",
)
PLAN_LIMITS = {
    "BASIC": {"branches": 1, "storage_mb": 500, "work_orders_monthly": 500},
    "FULL": {"branches": 5, "storage_mb": 10 * 1024, "work_orders_monthly": 5000},
    "ENTERPRISE": {"branches": 999, "storage_mb": 50 * 1024, "work_orders_monthly": None},
}
DEFAULT_COMPANY_SETTINGS = {
    "vat_rate": 21,
    "payment_terms_days": 30,
    "labor_rates": {},
    "elevators": [],
    "invoice_series": "F",
    "proforma_series": "P",
}


class TenantCollection:
    def __init__(self, collection, name: str):
        self.collection = collection
        self.name = name

    def _scope_filter(self, query: dict | None = None) -> dict:
        if self.name in GLOBAL_COLLECTIONS:
            return query or {}
        scope = current_scope()
        if not scope:
            raise HTTPException(503, "Context tenant lipsă")
        if scope.get("platform_role") == "SUPERADMIN" and scope.get("system_scope"):
            return query or {}
        tenant_filter = {"tenant_id": scope["tenant_id"], "branch_id": scope["branch_id"]}
        if not query:
            return tenant_filter
        return {"$and": [tenant_filter, query]}

    def _stamp(self, document: dict) -> dict:
        if self.name in GLOBAL_COLLECTIONS:
            return document
        scope = current_scope()
        if not scope:
            raise HTTPException(503, "Context tenant lipsă")
        stamped = dict(document)
        stamped["tenant_id"] = scope["tenant_id"]
        stamped["branch_id"] = scope["branch_id"]
        return stamped

    async def insert_one(self, document, *args, **kwargs):
        return await self.collection.insert_one(self._stamp(document), *args, **kwargs)

    async def insert_many(self, documents, *args, **kwargs):
        return await self.collection.insert_many([self._stamp(item) for item in documents], *args, **kwargs)

    def find(self, query=None, *args, **kwargs):
        return self.collection.find(self._scope_filter(query), *args, **kwargs)

    async def find_one(self, query=None, *args, **kwargs):
        return await self.collection.find_one(self._scope_filter(query), *args, **kwargs)

    async def count_documents(self, query=None, *args, **kwargs):
        return await self.collection.count_documents(self._scope_filter(query), *args, **kwargs)

    async def distinct(self, key, query=None, *args, **kwargs):
        return await self.collection.distinct(key, self._scope_filter(query), *args, **kwargs)

    async def update_one(self, query, update, *args, **kwargs):
        scoped_query = self._scope_filter(query)
        update = self._sanitize_update(update)
        if kwargs.get("upsert") and self.name not in GLOBAL_COLLECTIONS:
            scope = current_scope()
            update = dict(update)
            update["$setOnInsert"] = {
                **update.get("$setOnInsert", {}),
                "tenant_id": scope["tenant_id"],
                "branch_id": scope["branch_id"],
            }
        return await self.collection.update_one(scoped_query, update, *args, **kwargs)

    async def update_many(self, query, update, *args, **kwargs):
        update = self._sanitize_update(update)
        return await self.collection.update_many(self._scope_filter(query), update, *args, **kwargs)

    async def delete_one(self, query, *args, **kwargs):
        return await self.collection.delete_one(self._scope_filter(query), *args, **kwargs)

    async def delete_many(self, query, *args, **kwargs):
        return await self.collection.delete_many(self._scope_filter(query), *args, **kwargs)

    async def find_one_and_update(self, query, update, *args, **kwargs):
        scoped_query = self._scope_filter(query)
        update = self._sanitize_update(update)
        if kwargs.get("upsert") and self.name not in GLOBAL_COLLECTIONS:
            scope = current_scope()
            update = dict(update)
            update["$setOnInsert"] = {
                **update.get("$setOnInsert", {}),
                "tenant_id": scope["tenant_id"],
                "branch_id": scope["branch_id"],
            }
        return await self.collection.find_one_and_update(scoped_query, update, *args, **kwargs)

    def aggregate(self, pipeline, *args, **kwargs):
        if self.name in GLOBAL_COLLECTIONS:
            return self.collection.aggregate(pipeline, *args, **kwargs)
        return self.collection.aggregate([{"$match": self._scope_filter()}] + list(pipeline), *args, **kwargs)

    def __getattr__(self, name):
        if name in {"create_index", "drop_index", "index_information", "list_indexes"}:
            return getattr(self.collection, name)
        raise AttributeError(f"Metoda Mongo ne-scoped este interzisă: {name}")

    def _sanitize_update(self, update: dict) -> dict:
        if isinstance(update, list):
            raise HTTPException(400, "Update pipeline nepermis în context tenant")
        if self.name in GLOBAL_COLLECTIONS:
            return update
        safe = dict(update)
        for operator, values in safe.items():
            if not operator.startswith("$") or not isinstance(values, dict):
                continue
            safe[operator] = {
                key: value for key, value in values.items()
                if key not in {"tenant_id", "branch_id"}
                and not (operator == "$rename" and value in {"tenant_id", "branch_id"})
            }
        return safe


class TenantDatabase:
    def __getitem__(self, name):
        return TenantCollection(raw_db[name], name)

    def __getattr__(self, name):
        return TenantCollection(raw_db[name], name)


db = TenantDatabase()


def now():
    return datetime.now(timezone.utc)


def iso():
    return now().isoformat()


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p: str, h: str) -> bool:
    return bcrypt.checkpw(p.encode(), h.encode())


def make_token(user_id: str, kind: str, minutes: int, tenant_id: str = "", branch_id: str = "") -> str:
    payload = {"sub": user_id, "type": kind, "tenant_id": tenant_id, "branch_id": branch_id, "exp": now() + timedelta(minutes=minutes)}
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


def permissions_for(role: str, plan: str = "BASIC"):
    return [
        module
        for module, roles in MODULE_ROLES.items()
        if role in roles and (plan != "BASIC" or module not in FULL_ONLY_MODULES)
    ]


def requires_full_plan(path: str) -> bool:
    return path.startswith(FULL_ONLY_PREFIXES) or "/efactura/" in path


async def tenant_plan(tenant_id: str) -> str:
    tenant = await raw_db.tenants.find_one({"_id": tenant_id}, {"subscription_plan": 1})
    plan = (tenant or {}).get("subscription_plan", "BASIC")
    return plan if plan in PLAN_LIMITS else "BASIC"


def plan_limits(plan: str) -> dict:
    return PLAN_LIMITS[plan if plan in PLAN_LIMITS else "BASIC"]


async def enforce_work_order_quota() -> None:
    scope = current_scope()
    if not scope:
        return
    limit = plan_limits(await tenant_plan(scope["tenant_id"]))["work_orders_monthly"]
    if limit is None:
        return
    month = now().strftime("%Y-%m")
    count = await raw_db.work_orders.count_documents({
        "tenant_id": scope["tenant_id"],
        "created_at": {"$regex": f"^{month}"},
    })
    if count >= limit:
        raise HTTPException(403, f"Planul permite maximum {limit} comenzi de lucru pe lună")


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
    user = await raw_db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user or not user.get("active", True):
        raise HTTPException(401, "User not found")
    u = ser(user)
    u["platform_role"] = user.get("platform_role")
    u["tenant_id"] = user.get("tenant_id", "")
    u["active_branch_id"] = payload.get("branch_id") or user.get("active_branch_id", "")
    if u["tenant_id"]:
        u["branches"] = [
            {"id": item["_id"], "name": item["branch_name"]}
            for item in await raw_db.branches.find({
                "tenant_id": u["tenant_id"],
                "status": "ACTIVE",
                "_id": {"$in": user.get("assigned_branch_ids", [])},
            }).to_list(100)
        ]
    if u["tenant_id"] and u["active_branch_id"]:
        tenant = await raw_db.tenants.find_one({"_id": u["tenant_id"]})
        branch = await raw_db.branches.find_one({"_id": u["active_branch_id"], "tenant_id": u["tenant_id"]})
        if not tenant or tenant.get("status") != "ACTIVE":
            raise HTTPException(403, "Tenant suspendat sau expirat")
        if not branch or branch.get("status") != "ACTIVE":
            raise HTTPException(403, "Punctul de lucru este inactiv")
        if payload.get("tenant_id") != u["tenant_id"]:
            raise HTTPException(401, "Context tenant invalid")
        if u["active_branch_id"] not in user.get("assigned_branch_ids", []):
            raise HTTPException(403, "Acces interzis la punctul de lucru")
        set_scope({
            "tenant_id": u["tenant_id"],
            "branch_id": u["active_branch_id"],
            "platform_role": user.get("platform_role"),
        })
        u["subscription_plan"] = tenant.get("subscription_plan", "BASIC")
        if u["subscription_plan"] == "BASIC" and requires_full_plan(request.url.path):
            raise HTTPException(403, "Această funcție este disponibilă doar în planurile FULL sau ENTERPRISE")
    allowed_initial_password_paths = {
        "/api/auth/change-initial-password",
        "/api/auth/logout",
        "/api/auth/me",
    }
    if user.get("must_change_password") and request.url.path not in allowed_initial_password_paths:
        raise HTTPException(403, "Schimbați parola inițială pentru a continua")
    u["permissions"] = permissions_for(u["role"], u.get("subscription_plan", "BASIC"))
    return u


def require(module: str):
    async def dep(user: dict = Depends(get_current_user)):
        if user["role"] not in MODULE_ROLES[module]:
            raise HTTPException(403, "Acces interzis pentru acest modul")
        return user
    return dep


def require_superadmin():
    async def dep(user: dict = Depends(get_current_user)):
        if user.get("platform_role") != "SUPERADMIN":
            raise HTTPException(403, "Acces rezervat Superadmin")
        return user
    return dep


async def next_seq(name: str) -> int:
    scope = current_scope()
    if not scope:
        raise HTTPException(503, "Context tenant lipsă")
    key = f"{scope['tenant_id']}:{scope['branch_id']}:{name}"
    r = await raw_db.counters.find_one_and_update(
        {"_id": key},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    return r["seq"]


async def audit(user: dict, action: str, entity: str, entity_id: str = "", details: str = ""):
    await db.audit_logs.insert_one({"user_id": user.get("id"), "user_email": user.get("email"), "action": action,
                                    "entity": entity, "entity_id": entity_id, "details": details, "at": iso()})


async def get_settings() -> dict:
    s = await db.settings.find_one({"kind": "company"})
    settings = DEFAULT_COMPANY_SETTINGS | {k: v for k, v in (s or {}).items() if k != "_id"}
    scope = current_scope()
    if scope:
        settings["subscription_plan"] = await tenant_plan(scope["tenant_id"])
        settings["plan_limits"] = plan_limits(settings["subscription_plan"])
    return settings


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
