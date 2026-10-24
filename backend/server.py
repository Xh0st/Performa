import os
import logging
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from core import db, raw_db, client
from tenancy import migrate_demo_tenant
from tenant_context import DEMO_BRANCH_ID, DEMO_TENANT_ID, set_scope
from seed import seed_admin, seed_demo
import routes_auth
import routes_crm
import routes_service
import routes_stock
import routes_finance
import routes_dashboard
import routes_ai
import routes_efactura
import routes_rar
import routes_planning
import routes_reports
import routes_warranty
import routes_tenants

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
app = FastAPI(title="ERP Service Auto România")

for r in (
    routes_auth,
    routes_crm,
    routes_service,
    routes_stock,
    routes_finance,
    routes_dashboard,
    routes_ai,
    routes_efactura,
    routes_rar,
    routes_planning,
    routes_reports,
    routes_warranty,
    routes_tenants,
):
    app.include_router(r.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ["FRONTEND_URL"].split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.on_event("startup")
async def startup():
    await migrate_demo_tenant()
    set_scope({"tenant_id": DEMO_TENANT_ID, "branch_id": DEMO_BRANCH_ID})
    await raw_db.users.create_index("email", unique=True)
    await raw_db.settings.update_many({"custom_subdomain": ""}, {"$unset": {"custom_subdomain": ""}})
    await raw_db.settings.create_index("custom_subdomain", unique=True, sparse=True)
    await db.login_attempts.create_index("identifier")
    for collection, index_name in [
        (raw_db.vehicles, "vin_1"),
        (raw_db.products, "code_1"),
        (raw_db.efactura_inbox, "message_id_1"),
        (raw_db.rar_autopass_outbox, "idempotency_key_1"),
    ]:
        try:
            await collection.drop_index(index_name)
        except Exception:
            pass
    await db.vehicles.create_index([("tenant_id", 1), ("branch_id", 1), ("vin", 1)], unique=True)
    await db.products.create_index([("tenant_id", 1), ("branch_id", 1), ("code", 1)], unique=True)
    await db.work_orders.create_index("status")
    await db.work_orders.create_index("quotes.token")
    await db.time_entries.create_index([("mechanic_id", 1), ("start", -1)])
    await db.payments.create_index("date")
    await raw_db.payments.create_index(
        [("tenant_id", 1), ("branch_id", 1), ("doc_type", 1), ("doc_number", 1), ("document_issue_date", 1)],
        name="daily_cash_document_number",
        unique=True,
        partialFilterExpression={"document_issue_date": {"$gt": ""}},
    )
    await raw_db.cash_movements.create_index(
        [("tenant_id", 1), ("branch_id", 1), ("kind", 1), ("doc_number", 1), ("document_issue_date", 1)],
        name="daily_payment_order_number",
        unique=True,
        partialFilterExpression={"document_issue_date": {"$gt": ""}},
    )
    await db.efactura_inbox.create_index([("tenant_id", 1), ("branch_id", 1), ("message_id", 1)], unique=True, partialFilterExpression={"message_id": {"$type": "string"}})
    await db.efactura_logs.create_index("at")
    await db.rar_autopass_outbox.create_index([("tenant_id", 1), ("branch_id", 1), ("idempotency_key", 1)], unique=True)
    await db.rar_autopass_outbox.create_index("work_order_id")
    await db.rar_autopass_logs.create_index("at")
    await db.warranty_certificates.create_index("invoice_id", unique=True)
    await db.warranty_certificates.create_index("vehicle_id")
    await db.warranty_claims.create_index("invoice_id")
    await seed_admin()
    await seed_demo()
    await migrate_demo_tenant()


@app.on_event("shutdown")
async def shutdown():
    client.close()
