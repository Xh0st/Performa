# UI fixture for multi-tenant branch selector: `python mt_ui_fixture.py setup|cleanup`
import asyncio
import os
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")
from core import hash_password  # noqa: E402
from tenant_context import OPERATIONAL_COLLECTIONS  # noqa: E402

T, B1, B2 = "TEST-ui-tenant", "TEST-ui-branch-1", "TEST-ui-branch-2"
EMAIL = "test_ui_multi@example.com"
PW = "TestPass2026!"


async def main(cmd):
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    if cmd == "setup":
        now = datetime.now(timezone.utc).isoformat()
        await db.tenants.insert_one({"_id": T, "tenant_id": T, "company_name": "TEST UI Tenant", "subscription_plan": "PRO",
                                     "max_branches_allowed": 2, "status": "ACTIVE", "created_at": now})
        for b, n in ((B1, "TEST Sucursala Unu"), (B2, "TEST Sucursala Doi")):
            await db.branches.insert_one({"_id": b, "branch_id": b, "tenant_id": T, "branch_name": n, "status": "ACTIVE", "created_at": now})
            await db.clients.insert_one({"type": "pf", "name": f"TEST Client {n}", "tenant_id": T, "branch_id": b, "created_at": now,
                                         "phone": "", "email": "", "cnp": "", "cui": ""})
        await db.users.insert_one({"email": EMAIL, "name": "TEST UI Multi", "role": "admin", "active": True,
                                   "password_hash": hash_password(PW), "tenant_id": T,
                                   "assigned_branch_ids": [B1, B2], "active_branch_id": B1})
        print("setup ok")
    else:
        for c in OPERATIONAL_COLLECTIONS:
            await db[c].delete_many({"tenant_id": T})
        await db.users.delete_many({"email": EMAIL})
        await db.branches.delete_many({"tenant_id": T})
        await db.tenants.delete_many({"_id": {"$regex": "^TEST"}})
        await db.branches.delete_many({"_id": {"$regex": "^TEST"}})
        await db.login_attempts.delete_many({"identifier": {"$regex": "test_ui_multi"}})
        print("cleanup ok")

asyncio.run(main(sys.argv[1]))
