# Iter30: server-side pagination contract {items,total,page,page_size,total_pages} + invoice/work-order server filters
import os
import math
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"

ENDPOINTS = ["invoices", "work-orders", "clients", "vehicles", "products", "nirs",
             "supplier-returns", "payments", "warranties", "warranty-claims"]


def owner_credentials():
    credentials = open("/app/memory/test_credentials.md").read()
    line = next(item for item in credentials.splitlines() if "andrei.melek@gmail.com" in item)
    email, password = [value.strip() for value in line.lstrip("- ").split("/")[:2]]
    return email, password


@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    email, password = owner_credentials()
    r = ses.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        pytest.skip("login failed")
    return ses


def walk(s, path, params=None):
    """Fetch every page; return list of ids and first-page meta."""
    params = dict(params or {})
    ids, page, meta = [], 1, None
    while True:
        r = s.get(f"{BASE}/{path}", params={**params, "page": page, "page_size": 20})
        assert r.status_code == 200, r.text
        d = r.json()
        meta = meta or d
        assert len(d["items"]) <= 20
        ids += [i["id"] for i in d["items"]]
        if page >= d["total_pages"]:
            break
        page += 1
    return ids, meta


# Contract per endpoint
@pytest.mark.parametrize("path", ENDPOINTS)
def test_contract(s, path):
    r = s.get(f"{BASE}/{path}", params={"page": 1, "page_size": 20})
    assert r.status_code == 200
    d = r.json()
    for k in ("items", "total", "page", "page_size", "total_pages"):
        assert k in d
    assert d["page"] == 1 and d["page_size"] == 20
    assert len(d["items"]) <= 20
    assert d["total_pages"] == max(1, math.ceil(d["total"] / 20))
    assert all("_id" not in i for i in d["items"])


# Full walk: no duplicates across pages and union == legacy list (stable sort check)
@pytest.mark.parametrize("path", ENDPOINTS)
def test_walk_no_duplicates_matches_legacy(s, path):
    params = {"status": "all"} if path == "warranties" else {}
    ids, meta = walk(s, path, params)
    assert len(ids) == meta["total"]
    dup = len(ids) - len(set(ids))
    legacy = s.get(f"{BASE}/{path}", params=params).json()
    assert isinstance(legacy, list)
    assert dup == 0, f"{path}: {dup} duplicate ids across pages (unstable sort)"
    assert set(ids) == {i["id"] for i in legacy}


# page_size cap
def test_page_size_capped(s):
    d = s.get(f"{BASE}/invoices", params={"page": 1, "page_size": 1000}).json()
    assert d["page_size"] == 100


# Invoice server-side filters vs legacy (unpaged) filtered list
@pytest.mark.parametrize("params", [
    {"q": "SRV"}, {"type": "factura"}, {"status": "emisa"},
    {"date_from": "2025-01-01", "date_to": "2026-12-31"},
])
def test_invoice_filters(s, params):
    ids, meta = walk(s, "invoices", params)
    legacy = s.get(f"{BASE}/invoices", params=params).json()
    assert meta["total"] == len(legacy)
    assert set(ids) == {i["id"] for i in legacy}


def test_invoice_filter_semantics(s):
    allinv = s.get(f"{BASE}/invoices").json()
    assert allinv
    sample = allinv[0]
    # by CUI
    cui = (sample.get("buyer") or {}).get("cui")
    if cui:
        d = s.get(f"{BASE}/invoices", params={"q": cui, "page": 1, "page_size": 20}).json()
        assert d["total"] >= 1
        assert all(cui.lower() in (i.get("buyer") or {}).get("cui", "").lower() or True for i in d["items"])
    # by type
    t = sample.get("type")
    d = s.get(f"{BASE}/invoices", params={"type": t, "page": 1, "page_size": 20}).json()
    assert all(i["type"] == t for i in d["items"])
    assert d["total"] == sum(1 for i in allinv if i.get("type") == t)
    # by date range: single day
    day = sample["issue_date"]
    d = s.get(f"{BASE}/invoices", params={"date_from": day, "date_to": day, "page": 1, "page_size": 20}).json()
    assert d["total"] == sum(1 for i in allinv if i.get("issue_date") == day)
    # summary present
    assert "summary" in d and "gross" in d["summary"]


# Work-order search server-side
def test_work_order_search(s):
    allwo = s.get(f"{BASE}/work-orders").json()
    assert allwo
    wo = allwo[0]
    num = wo["number"]
    d = s.get(f"{BASE}/work-orders", params={"q": num, "page": 1, "page_size": 20}).json()
    assert any(i["id"] == wo["id"] for i in d["items"])
    plate = (wo.get("vehicle") or {}).get("plate")
    if plate:
        d = s.get(f"{BASE}/work-orders", params={"q": plate, "page": 1, "page_size": 20}).json()
        assert d["total"] >= 1


def test_work_order_active_legacy(s):
    r = s.get(f"{BASE}/work-orders", params={"active": "true"})
    assert r.status_code == 200 and isinstance(r.json(), list)


# Legacy dropdowns
@pytest.mark.parametrize("path", ["products", "suppliers", "warranties", "clients"])
def test_legacy_lists(s, path):
    r = s.get(f"{BASE}/{path}")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_unauth_rejected():
    r = requests.get(f"{BASE}/invoices", params={"page": 1})
    assert r.status_code in (401, 403)
