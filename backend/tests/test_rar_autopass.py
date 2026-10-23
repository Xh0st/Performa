# RAR AutoPass: config (RBAC, token never exposed, encrypted at rest), controlled 409 connection test, idempotent outbox.
# Run serially: pytest /app/backend/tests/test_rar_autopass.py -n 0  (saves/restores rar_autopass_config, cleans all TEST data)
import sys
import secrets
from pathlib import Path
import pytest
import requests
from bson import ObjectId

sys.path.insert(0, "/app/backend/tests")
from storno_fixtures import BASE, session, mdb, iso  # noqa: E402

TOKEN = f"test-rar-token-{secrets.token_urlsafe(24)}"


def demo_password():
    credentials = Path("/app/memory/test_credentials.md").read_text()
    prefix = "Demo users (password for all: "
    password_line = next((line for line in credentials.splitlines() if line.startswith(prefix)), "")
    password = password_line.removeprefix(prefix).split(")", 1)[0]
    if not password:
        pytest.skip("Lipsește parola utilizatorilor demo pentru testele RAR")
    return password


@pytest.fixture(scope="module")
def s():
    return session()


@pytest.fixture(scope="module", autouse=True)
def guard():
    db = mdb()
    start = iso()
    orig = db.rar_autopass_config.find_one({"_id": "primary"})
    ef = db.efactura_config.find_one({"_id": "main"}) or {}
    db.efactura_config.update_one({"_id": "main"}, {"$set": {"auto_send": False}})
    seq = (db.counters.find_one({"_id": "invoice"}) or {}).get("seq")
    state = {"start": start}
    yield state
    if orig:
        db.rar_autopass_config.replace_one({"_id": "primary"}, orig, upsert=True)
    else:
        db.rar_autopass_config.delete_one({"_id": "primary"})
    db.rar_autopass_logs.delete_many({"at": {"$gte": start}})
    db.audit_logs.delete_many({"entity": {"$in": ["rar_autopass", "rar_autopass_config"]}, "at": {"$gte": start}})
    db.efactura_config.update_one({"_id": "main"}, {"$set": {"auto_send": ef.get("auto_send", False)}})
    for key in ("wo",):
        if state.get(key):
            wid = state["wo"]
            inv_ids = [str(i["_id"]) for i in db.invoices.find({"work_order_id": wid})]
            db.invoices.delete_many({"work_order_id": wid})
            db.efactura_logs.delete_many({"invoice_id": {"$in": inv_ids}})
            db.rar_autopass_outbox.delete_many({"work_order_id": wid})
            db.audit_logs.delete_many({"entity_id": {"$in": inv_ids + [wid]}})
            db.work_orders.delete_one({"_id": ObjectId(wid)})
            db.vehicles.delete_one({"_id": ObjectId(state["veh"])})
            db.clients.delete_one({"_id": ObjectId(state["cli"])})
    if seq is not None:
        nums = [int(i["number"]) for i in db.invoices.find({"type": "fiscal"}, {"number": 1}) if str(i.get("number", "")).isdigit()]
        if max(nums or [0]) <= seq:
            db.counters.update_one({"_id": "invoice"}, {"$set": {"seq": seq}})


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": demo_password()})
    if r.status_code != 200:
        pytest.skip(f"{email} login failed")
    return {"Authorization": f"Bearer {r.json()['token']}"}


class TestConfig:
    def test_unauth(self):
        assert requests.get(f"{BASE}/rar-autopass/config").status_code == 401
        assert requests.post(f"{BASE}/rar-autopass/test-connection").status_code == 401

    @pytest.mark.parametrize("email", ["mecanic@serviceauto.ro", "receptie@serviceauto.ro"])
    def test_rbac(self, email):
        h = login(email)
        assert requests.get(f"{BASE}/rar-autopass/config", headers=h).status_code == 403
        assert requests.put(f"{BASE}/rar-autopass/config", headers=h, json={"authorization_code": "X", "service_cui": "X", "environment": "test"}).status_code == 403
        assert requests.post(f"{BASE}/rar-autopass/test-connection", headers=h).status_code == 403
        assert requests.get(f"{BASE}/rar-autopass/outbox", headers=h).status_code == 403

    def test_get_default(self, s):
        r = s.get(f"{BASE}/rar-autopass/config")
        assert r.status_code == 200
        d = r.json()
        assert d["branch_id"] == "primary" and d["external_transport_active"] is False
        assert "api_token" not in d and d["environment"] in ("test", "production")

    def test_invalid(self, s):
        assert s.put(f"{BASE}/rar-autopass/config", json={"authorization_code": "A", "service_cui": "RO1", "environment": "sandbox"}).status_code == 400
        assert s.put(f"{BASE}/rar-autopass/config", json={"authorization_code": "", "service_cui": "RO1", "environment": "test"}).status_code == 422

    def test_save_with_token_hidden_and_encrypted(self, s):
        r = s.put(f"{BASE}/rar-autopass/config", json={"branch_name": "TEST Punct", "authorization_code": "TEST-RAR-01", "service_cui": "ro123",
                                                         "environment": "production", "api_token": TOKEN})
        assert r.status_code == 200
        d = r.json()
        assert TOKEN not in r.text and "api_token" not in d
        assert d["has_api_token"] is True and d["authorization_code"] == "TEST-RAR-01" and d["service_cui"] == "RO123"
        assert d["environment"] == "production" and d["external_transport_active"] is False
        g = s.get(f"{BASE}/rar-autopass/config")
        assert TOKEN not in g.text and g.json()["has_api_token"] is True and g.json()["branch_name"] == "TEST Punct"
        raw = mdb().rar_autopass_config.find_one({"_id": "primary"})
        assert raw["api_token"] and TOKEN not in str(raw["api_token"])

    def test_save_without_token_keeps_token(self, s):
        r = s.put(f"{BASE}/rar-autopass/config", json={"authorization_code": "TEST-RAR-02", "service_cui": "RO123", "environment": "test"})
        assert r.status_code == 200 and r.json()["has_api_token"] is True and r.json()["environment"] == "test"

    def test_connection_409_logged(self, s):
        r = s.post(f"{BASE}/rar-autopass/test-connection")
        assert r.status_code == 409
        assert "contract" in r.json()["detail"].lower()
        logs = s.get(f"{BASE}/rar-autopass/logs").json()
        assert logs[0]["operation"] == "connection_test" and logs[0]["ok"] is False and TOKEN not in str(logs)


class TestOutbox:
    def test_invoice_then_close_idempotent(self, s, guard):
        db = mdb()
        tag = secrets.token_hex(3).upper()
        vin = ("TSTVIN" + tag + "000000000")[:17]
        cid = db.clients.insert_one({"name": f"TEST_RarClient {tag}", "type": "pf", "phone": "0700000000", "created_at": iso()}).inserted_id
        vid = db.vehicles.insert_one({"client_id": str(cid), "vin": vin, "plate": f"B{tag}", "make": "Test", "model": "Rar", "mileage": 1, "created_at": iso()}).inserted_id
        rec_at = "2026-01-10T08:00:00+00:00"
        lines = [{"id": "l1", "type": "labor", "description": "TEST Schimb ulei", "qty": 1, "unit_price": 100, "discount": 0, "vat_rate": 21,
                  "product_id": "", "code": "", "unit": "ore"}]
        wid = db.work_orders.insert_one({"number": f"TEST-RAR-{tag}", "client_id": str(cid), "vehicle_id": str(vid), "status": "finalizata",
                                         "mileage_in": 123456, "lines": lines, "quotes": [], "qc": {"passed": True}, "status_history": [],
                                         "finished_at": "2026-01-11T10:00:00+00:00", "created_at": iso(),
                                         "reception": {"at": rec_at, "odometer_photo": None}, "mechanic_ids": []}).inserted_id
        guard.update(wo=str(wid), veh=str(vid), cli=str(cid))
        inv = s.post(f"{BASE}/invoices/from-work-order/{wid}", json={"type": "fiscal"})
        assert inv.status_code == 200, inv.text
        inv = inv.json()
        items = list(db.rar_autopass_outbox.find({"work_order_id": str(wid)}))
        assert len(items) == 1
        o = items[0]
        assert o["state"] == "blocked" and o["trigger_events"] == ["invoice_issued"]
        assert "contract API RAR" in o["blocked_requirements"]
        p = o["payload"]
        assert p["branch_rar_authorization"] == "TEST-RAR-02"
        assert p["odometer_record"]["value"] == 123456 and p["odometer_record"]["reading_timestamp"] == rec_at
        assert "odometer_image_url" in p["odometer_record"] and p["odometer_record"]["odometer_image_url"] is None
        assert p["service_record"]["invoice_number"] == f"{inv['series']}{inv['number']}"
        assert "TEST Schimb ulei" in p["service_record"]["operations_summary"]
        guard["first_payload"] = p
        # close
        r = s.put(f"{BASE}/work-orders/{wid}/status", json={"status": "inchisa", "note": "TEST"})
        if r.status_code in (404, 405):
            r = s.post(f"{BASE}/work-orders/{wid}/status", json={"status": "inchisa", "note": "TEST"})
        assert r.status_code == 200, r.text
        items = list(db.rar_autopass_outbox.find({"work_order_id": str(wid)}))
        assert len(items) == 1
        assert set(items[0]["trigger_events"]) == {"invoice_issued", "work_order_closed"}
        assert items[0]["state"] == "blocked"
        ob = s.get(f"{BASE}/rar-autopass/outbox").json()
        mine = [x for x in ob if x["work_order_id"] == str(wid)]
        assert len(mine) == 1 and "payload" not in mine[0] and "idempotency_key" not in mine[0]

    def test_payload_vehicle_identity(self, guard):
        # VIN + plate must be in payload (vehicle_id is stored as string on WO/invoice)
        o = mdb().rar_autopass_outbox.find_one({"work_order_id": guard["wo"]})
        v = mdb().vehicles.find_one({"_id": ObjectId(guard["veh"])})
        assert o["payload"]["vehicle"]["vin"] == v["vin"], o["payload"]["vehicle"]
        assert o["payload"]["vehicle"]["plate_number"] == v["plate"]
        assert "VIN valid cu 17 caractere" not in o["blocked_requirements"]

    def test_completion_date(self, guard):
        o = mdb().rar_autopass_outbox.find_one({"work_order_id": guard["wo"]})
        # informative: finished_at is 2026-01-11
        print("completion_date first:", guard["first_payload"]["service_record"]["completion_date"],
              "after close:", o["payload"]["service_record"]["completion_date"])
        assert guard["first_payload"]["service_record"]["completion_date"] == "2026-01-11"
