import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import audit, hash_password, iso, oid, raw_db, require_superadmin, ser
from tenant_context import OPERATIONAL_COLLECTIONS


router = APIRouter(prefix="/api")


class TenantIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=180)
    cui: str = Field(min_length=2, max_length=30)
    admin_email: str = Field(
        min_length=5,
        max_length=254,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
    )
    initial_password: str = Field(min_length=8, max_length=256)
    subscription_plan: str = "BASIC"


class DeleteTenantIn(BaseModel):
    confirmation: str = Field(min_length=2, max_length=180)


class BranchIn(BaseModel):
    branch_id: str = Field(min_length=3, max_length=80)
    branch_name: str = Field(min_length=2, max_length=180)
    address: str = ""
    rar_authorization_code: str = ""
    is_main_branch: bool = False


class TenantAdminIn(BaseModel):
    email: str
    name: str
    password: str = Field(min_length=8)
    branch_ids: list[str]


class BranchAssignmentIn(BaseModel):
    branch_ids: list[str]


class TenantQuotaIn(BaseModel):
    subscription_plan: str
    max_branches_allowed: int = Field(ge=1, le=999)
    status: str


@router.get("/platform/tenants")
async def list_tenants(user=Depends(require_superadmin())):
    return [ser(item) for item in await raw_db.tenants.find({}).sort("company_name", 1).to_list(1000)]


@router.post("/platform/tenants")
async def create_tenant(body: TenantIn, user=Depends(require_superadmin())):
    if body.subscription_plan not in {"BASIC", "FULL"}:
        raise HTTPException(400, "Planul poate fi BASIC sau FULL")
    tenant_id = f"tenant-{uuid4().hex[:16]}"
    company_cui = body.cui.strip().upper()
    if await raw_db.tenants.find_one({"cui": company_cui}):
        raise HTTPException(400, "CUI deja existent")
    admin_email = body.admin_email.strip().lower()
    if await raw_db.users.find_one({"email": admin_email}):
        raise HTTPException(400, "Email administrator deja existent")
    branch_limit = 1 if body.subscription_plan == "BASIC" else 5
    document = {
        "_id": tenant_id,
        "company_name": body.company_name.strip(),
        "cui": company_cui,
        "subscription_plan": body.subscription_plan,
        "max_branches_allowed": branch_limit,
        "status": "ACTIVE",
        "created_at": iso(),
    }
    try:
        await raw_db.tenants.insert_one(document)
        branch = {
            "_id": f"branch-{uuid4().hex[:16]}",
            "tenant_id": tenant_id,
            "branch_name": f"{document['company_name']} · Sediu principal",
            "address": "",
            "rar_authorization_code": "",
            "is_main_branch": True,
            "status": "ACTIVE",
            "created_at": iso(),
        }
        await raw_db.branches.insert_one(branch)
        await raw_db.users.insert_one({
            "email": admin_email,
            "name": "Administrator",
            "role": "admin",
            "tenant_role": "TENANT_ADMIN",
            "active": True,
            "password_hash": hash_password(body.initial_password),
            "must_change_password": True,
            "tenant_id": tenant_id,
            "assigned_branch_ids": [branch["_id"]],
            "active_branch_id": branch["_id"],
            "created_at": iso(),
        })
    except Exception:
        await raw_db.users.delete_many({"tenant_id": tenant_id})
        await raw_db.branches.delete_many({"tenant_id": tenant_id})
        await raw_db.tenants.delete_one({"_id": tenant_id})
        raise
    await audit(user, "create", "tenant", tenant_id, document["company_name"])
    return ser(document)


@router.put("/platform/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, body: TenantQuotaIn, user=Depends(require_superadmin())):
    if body.subscription_plan not in {"BASIC", "FULL"}:
        raise HTTPException(400, "Plan invalid")
    if body.status not in {"ACTIVE", "SUSPENDED", "EXPIRED"}:
        raise HTTPException(400, "Status invalid")
    if tenant_id == user.get("tenant_id") and body.status != "ACTIVE":
        raise HTTPException(400, "Nu puteți suspenda tenantul contextului Superadmin activ")
    result = await raw_db.tenants.update_one({"_id": tenant_id}, {"$set": body.model_dump()})
    if not result.matched_count:
        raise HTTPException(404, "Tenant inexistent")
    return ser(await raw_db.tenants.find_one({"_id": tenant_id}))


@router.delete("/platform/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: str,
    body: DeleteTenantIn,
    user=Depends(require_superadmin()),
):
    if tenant_id == user.get("tenant_id"):
        raise HTTPException(400, "Nu puteți șterge tenantul contextului Superadmin activ")
    tenant = await raw_db.tenants.find_one({"_id": tenant_id})
    if not tenant:
        raise HTTPException(404, "Tenant inexistent")
    if body.confirmation.strip() != tenant["company_name"]:
        raise HTTPException(400, "Confirmați ștergerea scriind exact numele companiei")
    await audit(user, "delete", "tenant", tenant_id, tenant["company_name"])
    for collection in OPERATIONAL_COLLECTIONS | {"cron_errors"}:
        await raw_db[collection].delete_many({"tenant_id": tenant_id})
    await raw_db.users.delete_many({"tenant_id": tenant_id})
    await raw_db.branches.delete_many({"tenant_id": tenant_id})
    await raw_db.counters.delete_many({"_id": {"$regex": f"^{re.escape(tenant_id)}:"}})
    await raw_db.tenants.delete_one({"_id": tenant_id})
    return {"ok": True}


@router.get("/platform/tenants/{tenant_id}/branches")
async def list_branches(tenant_id: str, user=Depends(require_superadmin())):
    return [ser(item) for item in await raw_db.branches.find({"tenant_id": tenant_id}).sort("branch_name", 1).to_list(1000)]


@router.post("/platform/tenants/{tenant_id}/branches")
async def create_branch(tenant_id: str, body: BranchIn, user=Depends(require_superadmin())):
    tenant = await raw_db.tenants.find_one({"_id": tenant_id, "status": "ACTIVE"})
    if not tenant:
        raise HTTPException(404, "Tenant inexistent")
    active_count = await raw_db.branches.count_documents({"tenant_id": tenant_id, "status": "ACTIVE"})
    if active_count >= tenant["max_branches_allowed"]:
        raise HTTPException(403, "Ați atins limita maximă de puncte de lucru permisă de abonament")
    if await raw_db.branches.find_one({"_id": body.branch_id}):
        raise HTTPException(400, "Punct de lucru existent")
    document = body.model_dump() | {"tenant_id": tenant_id, "status": "ACTIVE", "created_at": iso()}
    document["_id"] = body.branch_id
    await raw_db.branches.insert_one(document)
    return ser(document)


async def validate_branch_assignment(tenant_id: str, branch_ids: list[str]) -> None:
    branches = await raw_db.branches.find({"tenant_id": tenant_id, "_id": {"$in": branch_ids}, "status": "ACTIVE"}).to_list(1000)
    if not branch_ids or len(branches) != len(set(branch_ids)):
        raise HTTPException(400, "Sucursale invalide pentru acest tenant")


@router.post("/platform/tenants/{tenant_id}/admins")
async def create_tenant_admin(tenant_id: str, body: TenantAdminIn, user=Depends(require_superadmin())):
    if not await raw_db.tenants.find_one({"_id": tenant_id, "status": "ACTIVE"}):
        raise HTTPException(404, "Tenant inexistent")
    await validate_branch_assignment(tenant_id, body.branch_ids)
    if await raw_db.users.find_one({"email": body.email.strip().lower()}):
        raise HTTPException(400, "Email deja existent")
    document = {
        "email": body.email.strip().lower(), "name": body.name.strip(), "role": "admin",
        "tenant_role": "TENANT_ADMIN", "active": True, "password_hash": hash_password(body.password),
        "tenant_id": tenant_id, "assigned_branch_ids": body.branch_ids,
        "active_branch_id": body.branch_ids[0], "created_at": iso(),
    }
    result = await raw_db.users.insert_one(document)
    return ser(await raw_db.users.find_one({"_id": result.inserted_id}))


@router.put("/platform/users/{uid}/branches")
async def assign_user_branches(uid: str, body: BranchAssignmentIn, user=Depends(require_superadmin())):
    target = await raw_db.users.find_one({"_id": oid(uid)})
    if not target or not target.get("tenant_id"):
        raise HTTPException(404, "Utilizator inexistent")
    await validate_branch_assignment(target["tenant_id"], body.branch_ids)
    await raw_db.users.update_one({"_id": target["_id"]}, {"$set": {"assigned_branch_ids": body.branch_ids, "active_branch_id": body.branch_ids[0]}})
    return ser(await raw_db.users.find_one({"_id": target["_id"]}))