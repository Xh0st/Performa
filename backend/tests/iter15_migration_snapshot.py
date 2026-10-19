# Iteration 15: verify legacy demo-tenant-001 migration to tenant-e93a5f22c8ba4a11 (SUPERADMIN) and snapshot untouched tenants
import asyncio
import hashlib
import json
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")
from tenant_context import OPERATIONAL_COLLECTIONS  # noqa: E402

OLD_T, OLD_B = "demo-tenant-001", "demo-branch-001"
NEW_T, NEW_B = "tenant-e93a5f22c8ba4a11", "branch-e93a5f22c8ba4a11"
PROTECTED = ["tenant-92e564e6004a450d", "tenant-8541282f554641b8"]


def h(obj):
    return hashlib.sha256(json.dumps(obj, default=str, sort_keys=True).encode()).hexdigest()[:16]


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    names = await db.list_collection_names()
    old_refs = {}
    for c in names:
        n = await db[c].count_documents({"$or": [
            {"tenant_id": OLD_T}, {"branch_id": OLD_B}, {"_id": OLD_T}, {"_id": OLD_B},
            {"active_branch_id": OLD_B}, {"assigned_branch_ids": OLD_B},
            {"migrated_from_tenant_id": {"$exists": False}, "tenant_id": {"$regex": "^demo-"}},
        ]})
        if n:
            old_refs[c] = n
    old_counters = await db.counters.count_documents({"_id": {"$regex": "demo-(tenant|branch)-001"}})
    t = await db.tenants.find_one({"_id": NEW_T})
    b = await db.branches.find_one({"_id": NEW_B})
    owner = await db.users.find_one({"email": "andrei.melek@gmail.com"})
    users_new = await db.users.count_documents({"tenant_id": NEW_T})
    users_bad_branch = await db.users.count_documents({"tenant_id": NEW_T, "active_branch_id": {"$ne": NEW_B}})
    new_counters = await db.counters.find({"_id": {"$regex": f"^{NEW_T}:"}}).to_list(100)
    op = {}
    for c in sorted(OPERATIONAL_COLLECTIONS):
        n = await db[c].count_documents({"tenant_id": NEW_T})
        bad = await db[c].count_documents({"tenant_id": NEW_T, "branch_id": {"$ne": NEW_B}})
        op[c] = (n, bad)
    snap = {}
    for pid in PROTECTED:
        pt = await db.tenants.find_one({"_id": pid})
        part = {"tenant": h(pt), "name": (pt or {}).get("company_name")}
        part["branches"] = h(await db.branches.find({"tenant_id": pid}).sort("_id", 1).to_list(100))
        part["users"] = h(await db.users.find({"tenant_id": pid}, {"last_login": 0}).sort("_id", 1).to_list(100))
        tot = 0
        for c in sorted(OPERATIONAL_COLLECTIONS):
            tot += await db[c].count_documents({"tenant_id": pid})
        part["op_docs"] = tot
        snap[pid] = part
    print("OLD_REFS:", old_refs, "old_counters:", old_counters)
    print("NEW_TENANT:", {k: t.get(k) for k in ("_id", "company_name", "status", "subscription_plan", "max_branches_allowed", "primary_admin_user_id", "migrated_from_tenant_id")} if t else None)
    print("NEW_BRANCH:", {k: b.get(k) for k in ("_id", "tenant_id", "branch_name", "is_main_branch", "status")} if b else None)
    print("OWNER:", owner.get("tenant_id"), owner.get("active_branch_id"), owner.get("assigned_branch_ids"), owner.get("platform_role"), owner.get("tenant_role"), str(owner["_id"]) == (t or {}).get("primary_admin_user_id"))
    print("USERS new:", users_new, "bad branch:", users_bad_branch)
    print("COUNTERS new:", [(c["_id"], c.get("seq")) for c in new_counters])
    print("OP (count, wrong_branch):", {k: v for k, v in op.items() if v[0]})
    print("PROTECTED:", json.dumps(snap))


asyncio.run(main())
