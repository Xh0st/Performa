# Iteration 23: appointment -> "Creare comandă" (status in_lucru) creates exactly one work order (idempotent + concurrent), delete keeps WO
import os
import re
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
PW = re.search(r"andrei\.melek@gmail\.com / (\S+)", open("/app/memory/test_credentials.md").read()).group(1)
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def s():
    x = requests.Session()
    r = x.post(f"{BASE}/auth/login", json={"email": "andrei.melek@gmail.com", "password": PW})
    assert r.status_code == 200, r.text
    x.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return x


@pytest.fixture(scope="module")
def cv(s):
    c = s.post(f"{BASE}/clients", json={"name": "TEMP I23 Client", "phone": "0700000231"}).json()
    v = s.post(f"{BASE}/vehicles", json={"client_id": c["id"], "vin": "TMPI23VIN00000000", "plate": "TMP23I", "make": "Test",
                                        "model": "I23", "mileage": 1}).json()
    yield c["id"], v["id"]
    appts = [str(a["_id"]) for a in db.appointments.find({"client_id": c["id"]})]
    db.appointments.delete_many({"client_id": c["id"]})
    db.notifications.delete_many({"appointment_id": {"$in": appts}})
    wos = [str(w["_id"]) for w in db.work_orders.find({"client_id": c["id"]})]
    db.work_orders.delete_many({"client_id": c["id"]})
    db.audit_logs.delete_many({"entity_id": {"$in": appts + wos + [c["id"], v["id"]]}})
    db.vehicles.delete_one({"_id": ObjectId(v["id"])})
    db.clients.delete_one({"_id": ObjectId(c["id"])})


def mk(s, cv, h, title):
    r = s.post(f"{BASE}/appointments", json={"client_id": cv[0], "vehicle_id": cv[1], "title": title,
                                             "starts_at": f"2031-04-02T{h:02d}:00:00Z", "ends_at": f"2031-04-02T{h + 1:02d}:00:00Z"})
    assert r.status_code == 200, r.text
    assert r.json()["work_order_id"] == ""
    return r.json()["id"]


def test_create_wo_idempotent(s, cv):
    aid = mk(s, cv, 8, "TEMP I23 idem")
    r1 = s.post(f"{BASE}/appointments/{aid}/status", json={"status": "in_lucru"})
    assert r1.status_code == 200, r1.text
    wo = r1.json()["work_order_id"]
    assert wo and r1.json()["status"] == "in_lucru"
    r2 = s.post(f"{BASE}/appointments/{aid}/status", json={"status": "in_lucru"})
    assert r2.status_code == 200 and r2.json()["work_order_id"] == wo
    assert db.work_orders.count_documents({"client_id": cv[0], "complaint": {"$exists": True}, "_id": ObjectId(wo)}) == 1
    lst = s.get(f"{BASE}/appointments", params={"start": "2031-04-01T00:00:00Z", "end": "2031-04-03T00:00:00Z"}).json()
    assert [a for a in lst if a["id"] == aid][0]["work_order_id"] == wo


def test_create_wo_concurrent_single(s, cv):
    aid = mk(s, cv, 11, "TEMP I23 conc")
    before = db.work_orders.count_documents({"client_id": cv[0]})
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(lambda _: s.post(f"{BASE}/appointments/{aid}/status", json={"status": "in_lucru"}), range(4)))
    ids = {r.json().get("work_order_id") for r in res if r.status_code == 200}
    assert len(ids) == 1, [r.text for r in res]
    assert db.work_orders.count_documents({"client_id": cv[0]}) == before + 1


def test_delete_converted_keeps_wo(s, cv):
    aid = mk(s, cv, 14, "TEMP I23 del")
    wo = s.post(f"{BASE}/appointments/{aid}/status", json={"status": "in_lucru"}).json()["work_order_id"]
    r = s.delete(f"{BASE}/appointments/{aid}")
    assert r.status_code == 200 and r.json() == {"ok": True, "work_order_preserved": True}
    assert s.get(f"{BASE}/work-orders/{wo}").status_code == 200
    assert db.appointments.find_one({"_id": ObjectId(aid)}) is None
