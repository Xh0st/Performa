# Iter27 pagination: documents that list APIs return full arrays (pagination is client-side only, PAGE_SIZE=20)
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    r = ses.post(f"{BASE}/auth/login", json={"email": "andrei.melek@gmail.com", "password": "Admin2026!"})
    if r.status_code != 200:
        pytest.skip("login failed")
    return ses


@pytest.mark.parametrize("path", ["invoices", "work-orders", "products"])
def test_list_returns_full_array_over_20(s, path):
    r = s.get(f"{BASE}/{path}")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # Seed data has >20 rows -> API sends everything, no server-side limit
    assert len(data) > 20


@pytest.mark.parametrize("path", ["clients", "vehicles", "invoices", "work-orders", "products", "nirs", "supplier-returns"])
def test_list_ignores_limit_param(s, path):
    full = s.get(f"{BASE}/{path}").json()
    limited = s.get(f"{BASE}/{path}", params={"limit": 20, "skip": 0, "page": 1}).json()
    assert isinstance(limited, list)
    assert len(limited) == len(full)  # no server-side pagination support
