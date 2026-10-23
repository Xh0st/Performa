import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    credentials = open("/app/memory/test_credentials.md").read()
    line = next(item for item in credentials.splitlines() if "andrei.melek@gmail.com" in item)
    email, password = [value.strip() for value in line.lstrip("- ").split("/")[:2]]
    r = ses.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        pytest.skip("login failed")
    return ses


@pytest.mark.parametrize(
    "path",
    [
        "clients",
        "vehicles",
        "invoices",
        "work-orders",
        "products",
        "nirs",
        "supplier-returns",
    ],
)
def test_list_supports_server_pagination(s, path):
    response = s.get(f"{BASE}/{path}", params={"page": 1, "page_size": 20})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert len(data["items"]) <= 20
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total_pages"] >= 1
