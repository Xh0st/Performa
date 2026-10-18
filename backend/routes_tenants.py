from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import iso, raw_db, require_superadmin, ser


router = APIRouter(prefix="/api")


class TenantIn(BaseModel):
    tenant_id: str = Field(min_length=3, max_length=80)
    company_name: str = Field(min_length=2, max_length=180)
    cui: str = ""
    reg_com: str = ""
    subscription_plan: str = "BASIC"
    max_branches_allowed: int = Field(default=1, ge=1, le=999)


class BranchIn(BaseModel):
    branch_id: str = Field(min_length=3, max_length=80)
    branch_name: str = Field(min_length=2, max_length=180)
    address: str = ""
    rar_authorization_code: str = ""
    is_main_branch: bool = False


class TenantQuotaIn(BaseModel):
    subscription_plan: str
    max_branches_allowed: int = Field(ge=1, le=999)
    status: str


@router.get("/platform/tenants")
async def list_tenants(user=Depends(require_superadmin())):
    return [ser(item) for item in await raw_db.tenants.find({}).sort("company_name", 1).to_list(1000)]


@router.post("/platform/tenants")
async def create_tenant(body: TenantIn, user=Depends(require_superadmin())):
    if await raw_db.tenants.find_one({"_id": body.tenant_id}):
        raise HTTPException(400, "Tenant existent")
    document = body.model_dump() | {"status": "ACTIVE", "created_at": iso()}
    document["_id"] = body.tenant_id
    await raw_db.tenants.insert_one(document)
    return ser(document)


@router.put("/platform/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, body: TenantQuotaIn, user=Depends(require_superadmin())):
    if body.subscription_plan not in {"BASIC", "PRO", "ENTERPRISE"}:
        raise HTTPException(400, "Plan invalid")
    if body.status not in {"ACTIVE", "SUSPENDED", "EXPIRED"}:
        raise HTTPException(400, "Status invalid")
    result = await raw_db.tenants.update_one({"_id": tenant_id}, {"$set": body.model_dump()})
    if not result.matched_count:
        raise HTTPException(404, "Tenant inexistent")
    return ser(await raw_db.tenants.find_one({"_id": tenant_id}))


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