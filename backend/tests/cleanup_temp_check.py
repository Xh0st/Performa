# Cleanup helper: removes TEMP-ui13 tenant and reports any leftover TEMP/TEST multi-tenant records
import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    await db.tenants.delete_many({"_id": "TEMP-ui13-tenant"})
    rx = {"$regex": "^(TEMP|TEST)"}
    out = {
        "tenants": await db.tenants.count_documents({"_id": rx}),
        "branches": await db.branches.count_documents({"$or": [{"_id": rx}, {"tenant_id": rx}]}),
        "users": await db.users.count_documents({"$or": [{"email": {"$regex": "^(temp|test)_"}}, {"tenant_id": rx}]}),
        "counters": await db.counters.count_documents({"_id": rx}),
        "clients": await db.clients.count_documents({"$or": [{"name": {"$regex": "^TEMP"}}, {"tenant_id": rx}]}),
        "payments": await db.payments.count_documents({"tenant_id": rx}),
        "efactura_config": await db.efactura_config.count_documents({"tenant_id": rx}),
        "efactura_logs": await db.efactura_logs.count_documents({"tenant_id": rx}),
        "cron_errors": await db.cron_errors.count_documents({"tenant_id": rx}),
    }
    print(out)


asyncio.run(main())
