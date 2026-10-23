# e-Factura (ANAF) integration regression tests: config/OAuth URL, cron auth, outgoing submit/status (simulare + test-no-oauth),
# placeholder validation, inbox import errors. Inbox create-NIR/overwrite are verified via UI + test_efactura_inbox_verify.py.
import os
import time
import copy
import secrets
from urllib.parse import urlparse, parse_qs
import pytest
import requests
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
CRON = os.environ["WEBHOOK_CRON_SECRET"]
INV_A = "6ad3d750afe314ce5bd6dfa2"  # SRV 000068 (legacy in_processing)
INV_B = "6ad3e0ca352d37604d8ab2e4"  # SRV 000069 (legacy in_processing)
TEST_CLIENT_ID = "test-client-id"
TEST_CLIENT_SECRET = secrets.token_urlsafe(24)


def owner_credentials():
    credentials = open("/app/memory/test_credentials.md").read()
    line = next(line for line in credentials.splitlines() if "andrei.melek@gmail.com" in line)
    email, password = [value.strip() for value in line.lstrip("- ").split("/")[:2]]
    return email, password


@pytest.fixture(scope="module")
def s():
    ss = requests.Session()
    email, password = owner_credentials()
    r = ss.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        pytest.skip("login failed")
    ss.headers["Authorization"] = f"Bearer {r.json()['token']}"
    yield ss
    # cleanup: back to simulare, auto_send off, clear client id
    ss.put(f"{BASE}/efactura/config", json={"environment": "simulare", "client_id": "", "redirect_uri": "", "auto_send": False})


@pytest.fixture(scope="module")
def mdb():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def put_cfg(s, env, **kw):
    body = {"environment": env, "client_id": kw.get("client_id", ""), "client_secret": kw.get("client_secret"),
            "redirect_uri": kw.get("redirect_uri", ""), "auto_send": kw.get("auto_send", False)}
    return s.put(f"{BASE}/efactura/config", json=body)


# --- Cron endpoint auth
class TestCron:
    def test_no_auth_401(self):
        assert requests.post(f"{BASE}/cron/efactura/status").status_code == 401

    def test_wrong_secret_401(self):
        assert requests.post(f"{BASE}/cron/efactura/status", headers={"Authorization": "Bearer nope"}).status_code == 401

    def test_ok_200(self):
        r = requests.post(f"{BASE}/cron/efactura/tokens", headers={"Authorization": f"Bearer {CRON}"})
        assert r.status_code == 200 and r.json()["ok"] is True

    def test_invalid_job_400(self):
        r = requests.post(f"{BASE}/cron/efactura/foo", headers={"Authorization": f"Bearer {CRON}"})
        assert r.status_code == 400


# --- OAuth callback / config
class TestConfig:
    def test_callback_invalid_state_redirect(self):
        r = requests.get(f"{BASE}/efactura/oauth/callback?code=abc&state=bad", allow_redirects=False)
        assert r.status_code in (302, 307)
        assert r.headers["location"].endswith("/efactura?oauth=error")

    def test_invalid_env_400(self, s):
        assert put_cfg(s, "foo").status_code == 400

    def test_simulare_status(self, s):
        d = put_cfg(s, "simulare").json()
        assert d["status_text"].startswith("Mod simulare activ")
        assert d["api_base"] == "—"

    def test_test_env_and_secret_hidden(self, s):
        d = put_cfg(s, "test", client_id=TEST_CLIENT_ID, client_secret=TEST_CLIENT_SECRET).json()
        assert d["api_base"] == "https://api.anaf.ro/test/FCTEL/rest"
        assert d["status_text"].startswith("Neconectat - Test (ANAF Sandbox)")
        assert d["has_secret"] is True and "client_secret" not in d
        assert TEST_CLIENT_SECRET not in str(d)
        g = s.get(f"{BASE}/efactura/config").json()
        assert g["client_id"] == TEST_CLIENT_ID and g["has_secret"] is True

    def test_secret_kept_when_null(self, s):
        d = put_cfg(s, "test", client_id=TEST_CLIENT_ID).json()
        assert d["has_secret"] is True

    def test_prod_base(self, s):
        d = put_cfg(s, "prod", client_id=TEST_CLIENT_ID).json()
        assert d["api_base"] == "https://api.anaf.ro/prod/FCTEL/rest"
        assert "Producție" in d["status_text"]

    def test_oauth_start_url(self, s):
        put_cfg(s, "test", client_id=TEST_CLIENT_ID)
        r = s.post(f"{BASE}/efactura/oauth/start")
        assert r.status_code == 200
        u = urlparse(r.json()["url"])
        q = parse_qs(u.query)
        assert u.netloc == "logincert.anaf.ro" and u.path == "/anaf-oauth2/v1/authorize"
        assert q["client_id"] == [TEST_CLIENT_ID] and q["response_type"] == ["code"]
        assert q["redirect_uri"][0].endswith("/api/efactura/oauth/callback")
        assert len(q["state"][0]) > 20

    def test_refresh_without_token_400(self, s):
        assert s.post(f"{BASE}/efactura/oauth/refresh").status_code == 400

    def test_logs_contain_config_change(self, s):
        logs = s.get(f"{BASE}/efactura/logs").json()
        assert any(l["op"] == "config" and "prod" in l["message"] for l in logs)


# --- Outgoing invoice flow
class TestOutgoing:
    def test_test_env_without_oauth_error(self, s, mdb):
        mdb.invoices.update_one({"_id": ObjectId(INV_A)}, {"$set": {"efactura.status": "error"}})  # make re-runnable
        put_cfg(s, "test", client_id=TEST_CLIENT_ID)
        r = s.post(f"{BASE}/invoices/{INV_A}/efactura/submit")
        assert r.status_code == 200
        ef = r.json()["efactura"]
        assert ef["status"] == "error"
        assert any("SPV neautorizat" in e for e in ef["errors"])

    def test_validate_ok(self, s):
        r = s.post(f"{BASE}/invoices/{INV_A}/efactura/validate")
        assert r.status_code == 200 and r.json()["errors"] == []

    def test_simulare_submit_refresh(self, s, mdb):
        put_cfg(s, "simulare")
        mdb.invoices.update_one({"_id": ObjectId(INV_A)}, {"$set": {"efactura.status": "error"}})  # make re-runnable
        r = s.post(f"{BASE}/invoices/{INV_A}/efactura/submit").json()["efactura"]
        assert r["status"] == "pending" and r["upload_index"].isdigit() and r["env"] == "simulare"
        assert s.post(f"{BASE}/invoices/{INV_A}/efactura/submit").status_code == 400  # already sent
        r2 = s.post(f"{BASE}/invoices/{INV_A}/efactura/refresh").json()["efactura"]
        assert r2["status"] == "ok" and r2.get("download_id")

    def test_proforma_rejected(self, s):
        pf = next(i for i in s.get(f"{BASE}/invoices").json() if i["type"] == "proforma")
        assert s.post(f"{BASE}/invoices/{pf['id']}/efactura/submit").status_code == 400

    def test_cron_status_polls_pending(self, s, mdb):
        put_cfg(s, "simulare")
        doc = copy.deepcopy(mdb.invoices.find_one({"_id": ObjectId(INV_B)}))
        doc["_id"] = ObjectId()
        doc["number"] = "TEST_CRON"
        doc["efactura"] = {"status": "not_sent", "history": []}
        mdb.invoices.insert_one(doc)
        try:
            r = s.post(f"{BASE}/invoices/{doc['_id']}/efactura/submit").json()["efactura"]
            assert r["status"] == "pending"
            assert requests.post(f"{BASE}/cron/efactura/status", headers={"Authorization": f"Bearer {CRON}"}).status_code == 200
            time.sleep(3)
            assert s.get(f"{BASE}/invoices/{doc['_id']}").json()["efactura"]["status"] == "ok"
        finally:
            mdb.invoices.delete_one({"_id": doc["_id"]})

    def test_placeholder_seller_invalid(self, s, mdb):
        src = mdb.invoices.find_one({"_id": ObjectId(INV_A)})
        doc = copy.deepcopy(src)
        doc["_id"] = ObjectId()
        doc["number"] = "TEST_PH"
        doc["seller"]["name"] = "[DENUMIRE FIRMA]"
        doc["seller"]["address"] = "[ADRESA]"
        doc["efactura"] = {"status": "not_sent", "history": []}
        mdb.invoices.insert_one(doc)
        try:
            v = s.post(f"{BASE}/invoices/{doc['_id']}/efactura/validate").json()
            assert any("Denumire emitent" in e for e in v["errors"])
            r = s.post(f"{BASE}/invoices/{doc['_id']}/efactura/submit").json()["efactura"]
            assert r["status"] == "invalid" and r["errors"]
        finally:
            mdb.invoices.delete_one({"_id": doc["_id"]})


# --- Inbox import validation
class TestInboxImport:
    def test_invalid_xml_400(self, s):
        r = s.post(f"{BASE}/efactura/inbox/upload", json={"filename": "bad.xml", "content": "<Invoice><x>"})
        assert r.status_code == 400 and "XML invalid" in r.json()["detail"]

    def test_non_ubl_400(self, s):
        r = s.post(f"{BASE}/efactura/inbox/upload", json={"filename": "bad.xml", "content": "<foo/>"})
        assert r.status_code == 400

    def test_sync_in_simulare_400(self, s):
        put_cfg(s, "simulare")
        assert s.post(f"{BASE}/efactura/inbox/sync").status_code == 400
