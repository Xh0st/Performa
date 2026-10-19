from contextvars import ContextVar


tenant_scope: ContextVar[dict | None] = ContextVar("tenant_scope", default=None)


LEGACY_DEMO_TENANT_ID = "demo-tenant-001"
LEGACY_DEMO_BRANCH_ID = "demo-branch-001"
DEMO_TENANT_ID = "tenant-e93a5f22c8ba4a11"
DEMO_BRANCH_ID = "branch-e93a5f22c8ba4a11"
GLOBAL_COLLECTIONS = {
    "users",
    "tenants",
    "branches",
    "login_attempts",
    "counters",
    "cron_runs",
}
OPERATIONAL_COLLECTIONS = {
    "clients", "vehicles", "work_orders", "invoices", "payments", "products", "suppliers",
    "nirs", "stock_lots", "stock_moves", "supplier_returns", "mechanics", "time_entries",
    "appointments", "notifications", "warranty_certificates", "warranty_claims", "warranty_logs",
    "rar_autopass_config", "rar_autopass_outbox", "rar_autopass_logs", "efactura_config",
    "efactura_inbox", "efactura_files", "efactura_logs", "product_mappings", "ai_messages",
    "settings", "audit_logs",
}


def set_scope(scope: dict) -> None:
    tenant_scope.set(scope)


def clear_scope() -> None:
    tenant_scope.set(None)


def current_scope() -> dict | None:
    return tenant_scope.get()