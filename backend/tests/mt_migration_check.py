# Multi-tenant migration check: every operational collection doc must have tenant_id/branch_id (demo)
import asyncio
import os
import sys
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")
from tenant_context import OPERATIONAL_COLLECTIONS, GLOBAL_COLLECTIONS  # noqa: E402


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    names = await db.list_collection_names()
    print("Unclassified collections:", sorted(set(names) - OPERATIONAL_COLLECTIONS - GLOBAL_COLLECTIONS))
    bad = 0
    for c in sorted(OPERATIONAL_COLLECTIONS):
        total = await db[c].count_documents({})
        missing = await db[c].count_documents({"$or": [{"tenant_id": {"$exists": False}}, {"branch_id": {"$exists": False}},
                                                         {"tenant_id": ""}, {"branch_id": ""}, {"tenant_id": None}]})
        tenants = await db[c].distinct("tenant_id")
        branches = await db[c].distinct("branch_id")
        bad += missing
        print(f"{c:28} total={total:5} missing={missing} tenants={tenants} branches={branches}")
    print("USERS:")
    async for u in db.users.find({}, {"email": 1, "tenant_id": 1, "assigned_branch_ids": 1, "active_branch_id": 1, "platform_role": 1, "role": 1}):
        print("  ", u.get("email"), u.get("role"), u.get("platform_role"), u.get("tenant_id"), u.get("assigned_branch_ids"), u.get("active_branch_id"))
    print("TENANTS:", await db.tenants.find({}).to_list(100))
    print("BRANCHES:", await db.branches.find({}).to_list(100))
    print("Indexes vehicles:", list((await db.vehicles.index_information()).keys()))
    print("Indexes products:", list((await db.products.index_information()).keys()))
    print("TOTAL MISSING:", bad)

asyncio.run(main())
