from core import iso, raw_db
from tenant_context import DEMO_BRANCH_ID, DEMO_TENANT_ID, OPERATIONAL_COLLECTIONS


async def migrate_demo_tenant() -> None:
    await raw_db.tenants.update_one(
        {"_id": DEMO_TENANT_ID},
        {"$setOnInsert": {
            "tenant_id": DEMO_TENANT_ID,
            "company_name": "Performa Auto Demo",
            "cui": "",
            "reg_com": "",
            "subscription_plan": "BASIC",
            "max_branches_allowed": 1,
            "status": "ACTIVE",
            "created_at": iso(),
        }},
        upsert=True,
    )
    await raw_db.branches.update_one(
        {"_id": DEMO_BRANCH_ID},
        {"$setOnInsert": {
            "branch_id": DEMO_BRANCH_ID,
            "tenant_id": DEMO_TENANT_ID,
            "branch_name": "Performa Auto Demo",
            "address": "",
            "rar_authorization_code": "",
            "is_main_branch": True,
            "status": "ACTIVE",
            "created_at": iso(),
        }},
        upsert=True,
    )
    for collection in OPERATIONAL_COLLECTIONS:
        await raw_db[collection].update_many(
            {"tenant_id": {"$exists": False}},
            {"$set": {"tenant_id": DEMO_TENANT_ID, "branch_id": DEMO_BRANCH_ID}},
        )
    await raw_db.users.update_many(
        {"tenant_id": {"$exists": False}},
        {"$set": {
            "tenant_id": DEMO_TENANT_ID,
            "assigned_branch_ids": [DEMO_BRANCH_ID],
            "active_branch_id": DEMO_BRANCH_ID,
        }},
    )
    owner = await raw_db.users.find_one({"email": "andrei.melek@gmail.com"})
    if owner:
        await raw_db.users.update_one(
            {"_id": owner["_id"]},
            {"$set": {"platform_role": "SUPERADMIN", "role": "admin"}},
        )