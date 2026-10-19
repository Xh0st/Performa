import os

from core import iso, raw_db
from tenant_context import (
    DEMO_BRANCH_ID,
    DEMO_TENANT_ID,
    LEGACY_DEMO_BRANCH_ID,
    LEGACY_DEMO_TENANT_ID,
    OPERATIONAL_COLLECTIONS,
)


async def migrate_legacy_demo_tenant() -> None:
    legacy_tenant = await raw_db.tenants.find_one({"_id": LEGACY_DEMO_TENANT_ID})
    if not legacy_tenant:
        return
    target_tenant = dict(legacy_tenant)
    target_tenant["_id"] = DEMO_TENANT_ID
    target_tenant["tenant_id"] = DEMO_TENANT_ID
    target_tenant["company_name"] = "SUPERADMIN"
    target_tenant["migrated_from_tenant_id"] = LEGACY_DEMO_TENANT_ID
    target_tenant["migrated_at"] = iso()
    await raw_db.tenants.replace_one({"_id": DEMO_TENANT_ID}, target_tenant, upsert=True)

    legacy_branch = await raw_db.branches.find_one({"_id": LEGACY_DEMO_BRANCH_ID})
    if legacy_branch:
        target_branch = dict(legacy_branch)
        target_branch["_id"] = DEMO_BRANCH_ID
        target_branch["branch_id"] = DEMO_BRANCH_ID
        target_branch["tenant_id"] = DEMO_TENANT_ID
        target_branch["branch_name"] = "SUPERADMIN · Sediu principal"
        target_branch["is_main_branch"] = True
        await raw_db.branches.replace_one({"_id": DEMO_BRANCH_ID}, target_branch, upsert=True)

    for collection in OPERATIONAL_COLLECTIONS | {"cron_errors", "cron_runs"}:
        await raw_db[collection].update_many(
            {"tenant_id": LEGACY_DEMO_TENANT_ID},
            {"$set": {"tenant_id": DEMO_TENANT_ID, "branch_id": DEMO_BRANCH_ID}},
        )

    users = await raw_db.users.find({"tenant_id": LEGACY_DEMO_TENANT_ID}).to_list(1000)
    for item in users:
        assigned_branch_ids = [
            DEMO_BRANCH_ID if branch_id == LEGACY_DEMO_BRANCH_ID else branch_id
            for branch_id in item.get("assigned_branch_ids", [])
        ]
        await raw_db.users.update_one(
            {"_id": item["_id"]},
            {
                "$set": {
                    "tenant_id": DEMO_TENANT_ID,
                    "active_branch_id": DEMO_BRANCH_ID,
                    "assigned_branch_ids": assigned_branch_ids or [DEMO_BRANCH_ID],
                }
            },
        )

    counters = await raw_db.counters.find({"_id": {"$regex": f"^{LEGACY_DEMO_TENANT_ID}:"}}).to_list(1000)
    for counter in counters:
        suffix = counter["_id"].split(":", 2)[-1]
        target_counter_id = f"{DEMO_TENANT_ID}:{DEMO_BRANCH_ID}:{suffix}"
        await raw_db.counters.update_one(
            {"_id": target_counter_id},
            {"$max": {"seq": counter.get("seq", 0)}},
            upsert=True,
        )
    await raw_db.counters.delete_many({"_id": {"$regex": f"^{LEGACY_DEMO_TENANT_ID}:"}})
    await raw_db.branches.delete_one({"_id": LEGACY_DEMO_BRANCH_ID})
    await raw_db.tenants.delete_one({"_id": LEGACY_DEMO_TENANT_ID})


async def migrate_demo_tenant() -> None:
    await migrate_legacy_demo_tenant()
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
    await raw_db.settings.update_many({"kind": {"$exists": False}}, {"$set": {"kind": "company"}})
    await raw_db.rar_autopass_config.update_many({"kind": {"$exists": False}}, {"$set": {"kind": "rar_autopass"}})
    await raw_db.efactura_config.update_many({"kind": {"$exists": False}}, {"$set": {"kind": "efactura"}})
    for counter in await raw_db.counters.find({"_id": {"$not": {"$regex": ":"}}}).to_list(1000):
        scoped_key = f"{DEMO_TENANT_ID}:{DEMO_BRANCH_ID}:{counter['_id']}"
        await raw_db.counters.update_one({"_id": scoped_key}, {"$setOnInsert": {"seq": counter.get("seq", 0)}}, upsert=True)
    await raw_db.users.update_many(
        {"tenant_id": {"$exists": False}},
        {"$set": {
            "tenant_id": DEMO_TENANT_ID,
            "assigned_branch_ids": [DEMO_BRANCH_ID],
            "active_branch_id": DEMO_BRANCH_ID,
        }},
    )
    owner = await raw_db.users.find_one({"email": os.environ["ADMIN_EMAIL"].lower()})
    if owner:
        await raw_db.users.update_one(
            {"_id": owner["_id"]},
            {
                "$set": {
                    "platform_role": "SUPERADMIN",
                    "tenant_role": "TENANT_ADMIN",
                    "role": "admin",
                }
            },
        )
        await raw_db.tenants.update_one(
            {"_id": DEMO_TENANT_ID},
            {"$set": {"primary_admin_user_id": str(owner["_id"])}},
        )