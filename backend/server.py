import os
import logging
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from core import db, client
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
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.vehicles.create_index("vin", unique=True)
    await db.products.create_index("code", unique=True)
    await db.work_orders.create_index("status")
    await db.work_orders.create_index("quotes.token")
    await db.time_entries.create_index([("mechanic_id", 1), ("start", -1)])
    await db.payments.create_index("date")
    await db.efactura_inbox.create_index("message_id", unique=True, partialFilterExpression={"message_id": {"$type": "string"}})
    await db.efactura_logs.create_index("at")
    await db.rar_autopass_outbox.create_index("idempotency_key", unique=True)
    await db.rar_autopass_outbox.create_index("work_order_id")
    await db.rar_autopass_logs.create_index("at")
    await seed_admin()
    await seed_demo()


@app.on_event("shutdown")
async def shutdown():
    client.close()
