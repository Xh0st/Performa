# Iter29: cookie-based auth lifecycle (login/me/refresh/logout), CORS credentials, NIR + supplier return persistence, static checks on tests.
import os
import re
import pathlib
import secrets
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ORIGIN = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
TESTS = pathlib.Path(__file__).parent


def owner_creds():
    text = pathlib.Path("/app/memory/test_credentials.md").read_text()
    line = next(l for l in text.splitlines() if "andrei.melek@gmail.com" in l)
    email, pwd = [v.strip() for v in line.lstrip("- ").split("/")[:2]]
    return email, pwd


@pytest.fixture(scope="module")
def cs():
    s = requests.Session()
    email, pwd = owner_creds()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    return s


# --- Cookie auth lifecycle
class TestCookieAuth:
    def test_login_sets_httponly_cookies(self):
        email, pwd = owner_creds()
        r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pwd})
        assert r.status_code == 200
        sc = r.headers.get("set-cookie", "").lower()
        assert "access_token=" in sc and "refresh_token=" in sc
        assert sc.count("httponly") >= 2 and "secure" in sc and "samesite=none" in sc
        assert r.json()["user"]["email"] == email
        assert "token" not in r.json()

    def test_me_via_cookie_only(self, cs):
        assert "Authorization" not in cs.headers
        r = cs.get(f"{BASE}/auth/me")
        assert r.status_code == 200 and r.json()["email"] == owner_creds()[0]

    def test_refresh_via_cookie(self):
        s = requests.Session()
        email, pwd = owner_creds()
        s.post(f"{BASE}/auth/login", json={"email": email, "password": pwd})
        s.cookies.set("access_token", None)
        r = s.post(f"{BASE}/auth/refresh")
        assert r.status_code == 200
        assert s.get(f"{BASE}/auth/me").status_code == 200

    def test_refresh_without_cookie_401(self):
        assert requests.post(f"{BASE}/auth/refresh").status_code == 401

    def test_logout_then_me_401(self):
        s = requests.Session()
        email, pwd = owner_creds()
        s.post(f"{BASE}/auth/login", json={"email": email, "password": pwd})
        assert s.get(f"{BASE}/auth/me").status_code == 200
        r = s.post(f"{BASE}/auth/logout")
        assert r.status_code == 200
        assert s.get(f"{BASE}/auth/me").status_code == 401
        assert s.post(f"{BASE}/auth/refresh").status_code == 401

    def test_me_without_auth_401(self):
        assert requests.get(f"{BASE}/auth/me").status_code == 401

    def test_cors_credentials_explicit_origin(self):
        r = requests.options(f"{BASE}/auth/me", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"})
        assert r.headers.get("access-control-allow-origin") == ORIGIN
        assert r.headers.get("access-control-allow-credentials") == "true"
        r2 = requests.options(f"{BASE}/auth/me", headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "GET"})
        assert r2.headers.get("access-control-allow-origin") != "https://evil.example.com"


# --- NIR + supplier return via cookie session
class TestStockFlows:
    def test_nir_then_return(self, cs):
        tag = secrets.token_hex(3).upper()
        sup = cs.post(f"{BASE}/suppliers", json={"name": f"TEST_SUP_{tag}", "cui": "", "phone": "", "email": ""})
        assert sup.status_code in (200, 201), sup.text
        sid = sup.json()["id"]
        prod = cs.post(f"{BASE}/products", json={"code": f"TEST-{tag}", "name": f"TEST prod {tag}", "category": "piese", "unit": "buc",
                                                  "sale_price": 10, "min_stock": 0, "vat_rate": 21, "warranty_months": 0})
        assert prod.status_code in (200, 201), prod.text
        pid = prod.json()["id"]
        nir = cs.post(f"{BASE}/nirs", json={"supplier_id": sid, "invoice_no": f"F{tag}", "aviz_no": "", "date": "2026-01-10T00:00:00Z",
                                            "lines": [{"product_id": pid, "qty": 5, "unit_cost": 3, "lot": ""}]})
        assert nir.status_code in (200, 201), nir.text
        nid = nir.json()["id"]
        g = cs.get(f"{BASE}/nirs/{nid}")
        assert g.status_code == 200 and g.json()["lines"][0]["qty"] == 5
        # row_id extra field from UI must be stripped; verify server tolerates/ignores it either way
        assert "row_id" not in str(g.json()["lines"])
        ret = cs.post(f"{BASE}/supplier-returns", json={"supplier_id": sid, "nir_id": nid, "reason": "TEST defect", "date": "2026-01-11T00:00:00Z",
                                                        "lines": [{"product_id": pid, "qty": 2}]})
        assert ret.status_code in (200, 201), ret.text
        rid = ret.json()["id"]
        gr = cs.get(f"{BASE}/supplier-returns/{rid}")
        assert gr.status_code == 200
        p = next(x for x in cs.get(f"{BASE}/products").json() if x["id"] == pid)
        assert p["stock_qty"] == 3


# --- Static checks on test files
class TestStatic:
    def test_no_dynamic_imports(self):
        for f in ("test_tenancy.py", "test_storno_returns.py"):
            t = (TESTS / f).read_text()
            assert "__import__" not in t and "importlib" not in t, f

    def test_no_hardcoded_secrets(self):
        creds = pathlib.Path("/app/memory/test_credentials.md").read_text()
        pwds = set(re.findall(r"[A-Za-z]+20\d\d!", creds))
        env = pathlib.Path("/app/backend/.env").read_text()
        env_vals = [v.strip().strip('"') for k, v in (l.split("=", 1) for l in env.splitlines() if "=" in l) if len(v.strip().strip('"')) >= 12 and "@" not in v and "://" not in v and k.strip() not in ("DB_NAME",)]
        for f in ("test_rar_autopass.py", "test_efactura.py"):
            t = (TESTS / f).read_text()
            for p in pwds:
                assert p not in t, f"{f} contains password"
            for v in env_vals:
                assert v not in t, f"{f} contains env value"
