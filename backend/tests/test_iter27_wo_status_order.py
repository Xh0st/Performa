# Iteration 27: WO status order (asteapta_piese before in_lucru) - read-only checks, no data mutation
import os
import sys
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

sys.path.insert(0, "/app/backend")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "andrei.melek@gmail.com", "password": "Admin2026!"})
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


# Core constant order
def test_core_wo_statuses_order():
    from core import WO_STATUSES
    assert WO_STATUSES.index("asteapta_piese") + 1 == WO_STATUSES.index("in_lucru")
    assert set(WO_STATUSES) == {"noua", "diagnosticare", "asteapta_oferta", "aprobata", "asteapta_piese",
                                "in_lucru", "finalizata", "facturata", "inchisa"}
    assert len(WO_STATUSES) == 9


# Work orders list still loads and statuses are all valid
def test_work_orders_list_statuses_valid(client):
    from core import WO_STATUSES
    r = client.get(f"{BASE_URL}/api/work-orders")
    assert r.status_code == 200
    data = r.json()
    rows = data if isinstance(data, list) else data.get("items", data.get("rows", []))
    assert isinstance(rows, list) and len(rows) > 0
    for w in rows:
        assert w["status"] in WO_STATUSES
    print({s: sum(1 for w in rows if w["status"] == s) for s in WO_STATUSES})


# Invalid status still rejected (no mutation)
def test_invalid_status_rejected(client):
    r = client.get(f"{BASE_URL}/api/work-orders")
    data = r.json()
    rows = data if isinstance(data, list) else data.get("items", data.get("rows", []))
    w = rows[0]
    r2 = client.post(f"{BASE_URL}/api/work-orders/{w['id']}/status", json={"status": "bogus_status"})
    assert r2.status_code == 400
    r3 = client.post(f"{BASE_URL}/api/work-orders/{w['id']}/status", json={"status": "facturata"})
    assert r3.status_code == 400
    after = client.get(f"{BASE_URL}/api/work-orders/{w['id']}").json()
    assert after["status"] == w["status"]


# Dashboard by_status still works
def test_dashboard_ok(client):
    r = client.get(f"{BASE_URL}/api/dashboard")
    assert r.status_code == 200
