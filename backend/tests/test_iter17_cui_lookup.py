# Iteration 17: ANAF V9 CUI lookup (normalization, mapping, VAT prefix, auth, tenant-scoped audit, 502, rate limit)
import os
import sys
import time
import asyncio
import pytest
import requests
import httpx
from fastapi import HTTPException
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
import cui_lookup as cl  # noqa: E402


def _base():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL="):
                url = line.split("=", 1)[1].strip()
    return url.rstrip("/") + "/api"


BASE = _base()
OWNER_EMAIL = "andrei.melek@gmail.com"
OWNER_PW = "Admin2026!"
REAL_VAT_CUI = "14399840"  # public company (VAT payer)


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s, r.json()


@pytest.fixture(scope="module")
def owner():
    return login(OWNER_EMAIL, OWNER_PW)


# --- Unit: normalization ---
@pytest.mark.parametrize("raw,exp", [("14399840", ("14399840", False)), ("RO14399840", ("14399840", True)),
                                     ("ro 14.399.840", ("14399840", True)), (" RO-14399840 ", ("14399840", True))])
def test_normalize_ok(raw, exp):
    assert cl.normalize_cui(raw) == exp


@pytest.mark.parametrize("raw", ["", "RO", "ABC123", "1", "12345678901", "RO12A45"])
def test_normalize_invalid(raw):
    with pytest.raises(HTTPException) as e:
        cl.normalize_cui(raw)
    assert e.value.status_code == 422


# --- Unit: mapping with mocked ANAF ---
class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=httpx.Request("POST", cl.ANAF_URL), response=httpx.Response(self.status_code))

    def json(self):
        return self._p


def _patch(monkeypatch, handler):
    class C:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None): return handler(json)
    monkeypatch.setattr(cl.httpx, "AsyncClient", C)


def _found(cui, vat):
    return {"found": [{"date_generale": {"cui": int(cui), "denumire": "TEST_FIRMA SRL", "adresa": "Str. Test 1",
                                         "nrRegCom": "J40/1/2020", "cod_CAEN": "4520", "forma_juridica": "SRL",
                                         "stare_inregistrare": "INREGISTRAT"},
                       "inregistrare_scop_Tva": {"scpTVA": vat}}], "notFound": []}


def test_mapping_vat_payer(monkeypatch):
    _patch(monkeypatch, lambda j: _Resp(_found(j[0]["cui"], True)))
    r = asyncio.run(cl.lookup_cui("12345678"))
    assert r["anaf_found"] and r["vat_payer"] and r["vat_number"] == "RO12345678"
    assert r["name"] == "TEST_FIRMA SRL" and r["address"] == "Str. Test 1" and r["reg_com"] == "J40/1/2020"


def test_mapping_non_vat(monkeypatch):
    _patch(monkeypatch, lambda j: _Resp(_found(j[0]["cui"], False)))
    r = asyncio.run(cl.lookup_cui("RO12345678"))
    assert r["anaf_found"] and r["vat_payer"] is False and r["vat_number"] is None and r["input_had_ro"] is True


def test_not_found(monkeypatch):
    _patch(monkeypatch, lambda j: _Resp({"found": [], "notFound": [j[0]["cui"]]}))
    r = asyncio.run(cl.lookup_cui("12345678"))
    assert r["anaf_found"] is False and "name" not in r and r["vat_number"] is None


def test_anaf_unavailable_502(monkeypatch):
    _patch(monkeypatch, lambda j: _Resp({}, 503))
    with pytest.raises(HTTPException) as e:
        asyncio.run(cl.lookup_cui("12345678"))
    assert e.value.status_code == 502


def test_anaf_timeout_502(monkeypatch):
    def h(j): raise httpx.ConnectTimeout("t")
    _patch(monkeypatch, h)
    with pytest.raises(HTTPException) as e:
        asyncio.run(cl.lookup_cui("12345678"))
    assert e.value.status_code == 502


def test_rate_limit_1rps(monkeypatch):
    calls = []
    _patch(monkeypatch, lambda j: (calls.append(time.monotonic()), _Resp(_found(j[0]["cui"], True)))[1])

    async def run():
        cl._lock = asyncio.Lock()
        cl._last_request = 0.0
        await asyncio.gather(*[cl.lookup_cui("12345678") for _ in range(3)])
    asyncio.run(run())
    assert len(calls) == 3
    assert calls[1] - calls[0] >= 0.95 and calls[2] - calls[1] >= 0.95


# --- Live API ---
def test_lookup_requires_auth():
    r = requests.post(f"{BASE}/cui/lookup", json={"cui": REAL_VAT_CUI})
    assert r.status_code == 401


def test_lookup_invalid_422(owner):
    s, _ = owner
    r = s.post(f"{BASE}/cui/lookup", json={"cui": "ABC"})
    assert r.status_code == 422


def test_lookup_live_vat_payer_and_audit(owner):
    s, data = owner
    variants = [REAL_VAT_CUI, "RO" + REAL_VAT_CUI, "RO 14.399.840"]
    for v in variants:
        r = s.post(f"{BASE}/cui/lookup", json={"cui": v})
        if r.status_code == 502:
            pytest.skip("ANAF unavailable")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["cui"] == REAL_VAT_CUI and d["anaf_found"] is True
        assert d["vat_payer"] is True and d["vat_number"] == "RO" + REAL_VAT_CUI
        assert d["name"] and d["address"] and d["reg_com"]
        assert d["input_had_ro"] is (v != REAL_VAT_CUI)
    m = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "test_database")]
    logs = list(m.audit_logs.find({"action": "cui_lookup"}).sort("at", -1).limit(3))
    assert len(logs) == 3
    for lg in logs:
        assert lg.get("tenant_id"), f"audit not tenant scoped: {lg}"
        txt = str(lg).lower()
        assert "token" not in txt and "password" not in txt and "bearer" not in txt


def test_lookup_live_not_found(owner):
    s, _ = owner
    # ANAF V9 answers HTTP 404 + {"found":[],"notFound":[cui]} for unknown CUI -> must be 200 anaf_found False, not 502
    r = s.post(f"{BASE}/cui/lookup", json={"cui": "99999999"})
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    d = r.json()
    assert d["anaf_found"] is False and "name" not in d and d["vat_number"] is None
