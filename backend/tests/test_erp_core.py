# Regression tests for ERP Service Auto core: auth, RBAC, CRM, reception/WO flow, quotes, QC, invoices, e-Factura, payments, stock, users, settings, AI
import os
import random
import string
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = ("admin@serviceauto.ro", "Admin2026!")
DEMO_PW = "Demo2026!"
PIX = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
STATE = {}


def make_cnp():
    base = "1900101400" + "".join(random.choice(string.digits) for _ in range(2))
    key = "279146358279"
    s = sum(int(base[i]) * int(key[i]) for i in range(12)) % 11
    return base + str(1 if s == 10 else s)


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return login(*ADMIN)


# ---- Auth ----
class TestAuth:
    def test_login_ok_cookies(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]})
        assert r.status_code == 200
        d = r.json()
        assert d["user"]["role"] == "admin" and "token" in d and "password_hash" not in d["user"]
        sc = r.headers.get("set-cookie", "").lower()
        assert "access_token" in sc and "httponly" in sc

    def test_login_wrong(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN[0], "password": "nope"})
        assert r.status_code == 401

    def test_me_and_logout(self, admin):
        r = admin.get(f"{API}/auth/me")
        assert r.status_code == 200 and r.json()["email"] == ADMIN[0]
        assert requests.get(f"{API}/auth/me").status_code == 401

    def test_bruteforce_lockout(self):
        email = f"test_lock_{random.randint(1, 10**6)}@x.ro"
        codes = [requests.post(f"{API}/auth/login", json={"email": email, "password": "x"}).status_code for _ in range(6)]
        assert codes[:5] == [401] * 5 and codes[5] == 429

    def test_cors_credentials(self):
        r = requests.options(f"{API}/auth/login", headers={"Origin": BASE_URL, "Access-Control-Request-Method": "POST"})
        assert r.headers.get("access-control-allow-origin") == BASE_URL
        assert r.headers.get("access-control-allow-credentials") == "true"


# ---- RBAC ----
class TestRBAC:
    def test_mecanic_no_invoices(self):
        s = login("mecanic@serviceauto.ro", DEMO_PW)
        assert s.get(f"{API}/invoices").status_code == 403

    def test_contabil_no_users(self):
        s = login("contabil@serviceauto.ro", DEMO_PW)
        assert s.get(f"{API}/users").status_code == 403

    def test_casier_perms(self):
        s = login("casier@serviceauto.ro", DEMO_PW)
        perms = s.get(f"{API}/auth/me").json()["permissions"]
        assert "stock" not in perms and "reception" not in perms
        assert s.get(f"{API}/products").status_code == 403


# ---- Dashboard ----
def test_dashboard(admin):
    r = admin.get(f"{API}/dashboard")
    assert r.status_code == 200
    d = r.json()
    for k in ("in_service", "mechanic_productivity", "parts_margin", "series", "by_status"):
        assert k in d
    assert len(d["series"]) == 6


# ---- CRM ----
class TestCRM:
    def test_invalid_cnp(self, admin):
        r = admin.post(f"{API}/clients", json={"type": "pf", "name": "TEST_bad", "cnp": "1234567890123"})
        assert r.status_code == 400

    def test_pj_requires_cui(self, admin):
        r = admin.post(f"{API}/clients", json={"type": "pj", "name": "TEST_PJ"})
        assert r.status_code == 400

    def test_create_pf_and_vehicle(self, admin):
        r = admin.post(f"{API}/clients", json={"type": "pf", "name": "TEST_Client PF", "cnp": make_cnp(),
                                                "email": "test@x.ro", "phone": "0722000000"})
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        STATE["client_id"] = cid
        vin = "TESTVIN" + "".join(random.choice("ABCDEFGHJKLMNPRSTUVWXYZ0123456789") for _ in range(10))
        assert admin.post(f"{API}/vehicles", json={"client_id": cid, "vin": "SHORT", "plate": "B01TST", "make": "VW", "model": "Golf"}).status_code == 400
        r = admin.post(f"{API}/vehicles", json={"client_id": cid, "vin": vin, "plate": "b 01 tst", "make": "VW", "model": "Golf", "mileage": 1000})
        assert r.status_code == 200, r.text
        STATE["vehicle_id"] = r.json()["id"]
        assert admin.post(f"{API}/vehicles", json={"client_id": cid, "vin": vin, "plate": "B02TST", "make": "VW", "model": "Golf"}).status_code == 400
        c = admin.get(f"{API}/clients/{cid}").json()
        assert len(c["vehicles"]) == 1 and c["vehicles"][0]["vin"] == vin


# ---- Stock ----
class TestStock:
    def test_product_and_nir(self, admin):
        code = f"TEST_P{random.randint(1, 10**6)}"
        r = admin.post(f"{API}/products", json={"code": code, "name": "TEST_Filtru ulei", "sale_price": 100, "min_stock": 5})
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        STATE["product_id"] = pid
        sups = admin.get(f"{API}/suppliers").json()
        assert sups
        assert admin.post(f"{API}/nirs", json={"supplier_id": sups[0]["id"], "lines": [{"product_id": pid, "qty": 1, "unit_cost": 1}]}).status_code == 400
        r = admin.post(f"{API}/nirs", json={"supplier_id": sups[0]["id"], "invoice_no": "TEST-1",
                                             "lines": [{"product_id": pid, "qty": 10, "unit_cost": 40}]})
        assert r.status_code == 200, r.text
        STATE["nir_id"] = r.json()["id"]
        r = admin.post(f"{API}/nirs", json={"supplier_id": sups[0]["id"], "invoice_no": "TEST-2",
                                             "lines": [{"product_id": pid, "qty": 10, "unit_cost": 60}]})
        assert r.status_code == 200
        p = next(x for x in admin.get(f"{API}/products", params={"q": code}).json() if x["id"] == pid)
        assert p["stock_qty"] == 20 and abs(p["avg_cost"] - 50) < 0.01
        assert admin.get(f"{API}/nirs/{STATE['nir_id']}").status_code == 200
        low = admin.get(f"{API}/products", params={"low": "true"}).json()
        assert all(x["stock_qty"] <= x.get("min_stock", 0) for x in low)


# ---- Work order full flow ----
class TestWorkOrderFlow:
    def test_reception_validation(self, admin):
        body = {"client_id": STATE["client_id"], "vehicle_id": STATE["vehicle_id"], "mileage_in": 2000, "complaint": "TEST zgomot",
                "photos": {"front": PIX}, "signature": PIX}
        assert admin.post(f"{API}/work-orders", json=body).status_code == 400
        body["photos"] = {k: PIX for k in ("front", "back", "left", "right", "interior")}
        body["signature"] = ""
        assert admin.post(f"{API}/work-orders", json=body).status_code == 400

    def test_reception_create(self, admin):
        body = {"client_id": STATE["client_id"], "vehicle_id": STATE["vehicle_id"], "mileage_in": 2000, "complaint": "TEST zgomot",
                "photos": {k: PIX for k in ("front", "back", "left", "right", "interior")}, "signature": PIX}
        r = admin.post(f"{API}/work-orders", json=body)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["number"].startswith(f"CL-{time.gmtime().tm_year}-")
        STATE["wo_id"] = d["id"]

    def test_lines_and_totals(self, admin):
        wid = STATE["wo_id"]
        settings = admin.get(f"{API}/settings").json()
        rate = settings["labor_rates"]["mecanic_senior"]
        r = admin.post(f"{API}/work-orders/{wid}/lines", json={"type": "labor", "description": "TEST manopera", "qty": 2, "labor_category": "mecanic_senior"})
        assert r.status_code == 200, r.text
        r = admin.post(f"{API}/work-orders/{wid}/lines", json={"type": "part", "product_id": STATE["product_id"], "qty": 12})
        assert r.status_code == 200, r.text
        w = r.json()
        labor = next(x for x in w["lines"] if x["type"] == "labor")
        assert labor["unit_price"] == rate
        net = 2 * rate + 12 * 100
        assert abs(w["totals"]["net"] - net) < 0.01
        assert abs(w["totals"]["vat"] - round(net * 0.21, 2)) < 0.02

    def test_quote_create_send_approve(self, admin):
        wid = STATE["wo_id"]
        r = admin.post(f"{API}/work-orders/{wid}/quotes", json={})
        assert r.status_code == 200, r.text
        qs = r.json()
        assert qs[-1]["version"] == 1
        assert admin.get(f"{API}/work-orders/{wid}").json()["status"] == "asteapta_oferta"
        # v2 supersedes v1
        r = admin.post(f"{API}/work-orders/{wid}/quotes", json={})
        assert r.status_code == 200, r.text
        qs = r.json()
        assert qs[0]["status"] == "superseded" and qs[1]["status"] == "draft"
        STATE["token"] = qs[1]["token"]
        r = admin.post(f"{API}/work-orders/{wid}/quotes/2/send", json={"channel": "email", "link": "x"})
        assert r.status_code == 200 and r.json()["simulated"] is True
        assert admin.post(f"{API}/work-orders/{wid}/quotes/2/decision", json={"approved": True}).status_code == 400

    def test_public_quote_approve(self):
        t = STATE["token"]
        r = requests.get(f"{API}/public/quotes/{t}")
        assert r.status_code == 200 and "token" not in r.json()["quote"]
        r = requests.post(f"{API}/public/quotes/{t}/decision", json={"approved": True, "signature": PIX, "name": "TEST Client"})
        assert r.status_code == 200, r.text

    def test_timer_qc_finalize_invoice(self, admin):
        wid = STATE["wo_id"]
        assert admin.get(f"{API}/work-orders/{wid}").json()["status"] == "aprobata"
        mech = admin.get(f"{API}/mechanics").json()[0]
        r = admin.post(f"{API}/work-orders/{wid}/timer", json={"mechanic_id": mech["id"], "action": "start"})
        assert r.status_code == 200 and r.json()["status"] == "in_lucru"
        admin.post(f"{API}/work-orders/{wid}/timer", json={"mechanic_id": mech["id"], "action": "stop"})
        assert admin.post(f"{API}/work-orders/{wid}/status", json={"status": "finalizata"}).status_code == 400
        items = {k: "ok" for k in ["frane", "directie", "suspensie", "lumini", "niveluri", "anvelope", "test_drive"]}
        r = admin.put(f"{API}/work-orders/{wid}/qc", json={"items": items, "mechanic_signature": PIX, "chief_signature": PIX})
        assert r.status_code == 200 and r.json()["qc"]["passed"] is True
        r = admin.post(f"{API}/work-orders/{wid}/status", json={"status": "finalizata"})
        assert r.status_code == 200 and r.json()["status"] == "finalizata"
        r = admin.post(f"{API}/invoices/from-work-order/{wid}", json={"type": "fiscal"})
        assert r.status_code == 200, r.text
        inv = r.json()
        STATE["invoice_id"] = inv["id"]
        STATE["gross"] = inv["totals"]["gross"]
        # FIFO: 10@40 + 2@60 = 520
        assert abs(inv["cogs"] - 520) < 0.01
        assert admin.get(f"{API}/work-orders/{wid}").json()["status"] == "facturata"
        p = next(x for x in admin.get(f"{API}/products").json() if x["id"] == STATE["product_id"])
        assert p["stock_qty"] == 8
        assert admin.post(f"{API}/invoices/from-work-order/{wid}", json={"type": "fiscal"}).status_code == 400

    def test_efactura(self, admin):
        iid = STATE["invoice_id"]
        r = admin.get(f"{API}/invoices/{iid}/efactura/xml")
        assert r.status_code == 200 and "CIUS-RO" in r.text and "<Invoice" in r.text
        import xml.dom.minidom
        xml.dom.minidom.parseString(r.content)
        r = admin.post(f"{API}/invoices/{iid}/efactura/submit")
        assert r.status_code == 200 and r.json()["efactura"]["status"] == "in_processing"
        r = admin.post(f"{API}/invoices/{iid}/efactura/refresh")
        assert r.status_code == 200 and r.json()["efactura"]["status"] == "ok"

    def test_payments(self, admin):
        iid, gross = STATE["invoice_id"], STATE["gross"]
        r = admin.post(f"{API}/payments", json={"invoice_id": iid, "amount": 100, "method": "numerar"})
        assert r.status_code == 200 and r.json()["doc_number"].startswith("CH-")
        STATE["payment_id"] = r.json()["id"]
        assert admin.get(f"{API}/invoices/{iid}").json()["status"] == "partial"
        assert admin.post(f"{API}/payments", json={"invoice_id": iid, "amount": gross, "method": "numerar"}).status_code == 400
        r = admin.post(f"{API}/payments", json={"invoice_id": iid, "amount": round(gross - 100, 2), "method": "pos"})
        assert r.status_code == 200
        assert admin.get(f"{API}/invoices/{iid}").json()["status"] == "paid"
        cr = admin.get(f"{API}/cash-register").json()
        assert any(e["id"] == STATE["payment_id"] for e in cr["entries"])
        assert abs(cr["closing"] - cr["opening"] - cr["total_in"]) < 0.01

    def test_close_wo(self, admin):
        r = admin.post(f"{API}/work-orders/{STATE['wo_id']}/status", json={"status": "inchisa"})
        assert r.status_code == 200 and r.json()["status"] == "inchisa"


# ---- Mechanics clock ----
def test_clock(admin):
    m = admin.get(f"{API}/mechanics").json()[-1]
    if m["clocked_in"]:
        admin.post(f"{API}/mechanics/{m['id']}/clock", json={"action": "out"})
    assert admin.post(f"{API}/mechanics/{m['id']}/clock", json={"action": "in"}).status_code == 200
    assert admin.post(f"{API}/mechanics/{m['id']}/clock", json={"action": "in"}).status_code == 400
    assert admin.post(f"{API}/mechanics/{m['id']}/clock", json={"action": "out"}).status_code == 200


# ---- Users / audit / settings ----
def test_users_crud(admin):
    email = f"test_user_{random.randint(1, 10**6)}@x.ro"
    r = admin.post(f"{API}/users", json={"email": email, "name": "TEST U", "role": "mecanic", "password": "Testpass1!"})
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    r = admin.put(f"{API}/users/{uid}", json={"email": email, "name": "TEST U2", "role": "casier"})
    assert r.status_code == 200 and r.json()["role"] == "casier"
    assert admin.delete(f"{API}/users/{uid}").status_code == 200
    assert all(u["id"] != uid for u in admin.get(f"{API}/users").json())
    assert len(admin.get(f"{API}/audit").json()) > 0


def test_settings_update(admin):
    s = admin.get(f"{API}/settings").json()
    orig = s["labor_rates"]["mecanic_senior"]
    s["labor_rates"]["mecanic_senior"] = orig + 1
    r = admin.put(f"{API}/settings", json={"labor_rates": s["labor_rates"]})
    assert r.status_code == 200 and r.json()["labor_rates"]["mecanic_senior"] == orig + 1
    s["labor_rates"]["mecanic_senior"] = orig
    admin.put(f"{API}/settings", json={"labor_rates": s["labor_rates"]})


# ---- AI ----
def test_ai_stream(admin):
    r = admin.post(f"{API}/ai/stream", json={"mode": "obd", "message": "Ce inseamna P0300? raspuns scurt"}, stream=True, timeout=120)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    text = "".join(c.decode("utf-8", "ignore") for c in r.iter_content(None))
    assert len(text) > 30 and "Eroare AI" not in text, text[:300]
