# Iteration 24: appointments ignore client-sent advisor/status; advisor = logged user (POST, PUT); mechanic dropdown single id persists; WO advisor
import os
import re

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
_txt = open("/app/memory/test_credentials.md").read()
PW = re.search(r"andrei\.melek@gmail\.com / (\S+)", _txt).group(1)
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def login(email, pw):
    x = requests.Session()
    r = x.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    x.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return x


@pytest.fixture(scope="module")
def s():
    return login("andrei.melek@gmail.com", PW)


@pytest.fixture(scope="module")
def me(s):
    return s.get(f"{BASE}/auth/me").json()


@pytest.fixture(scope="module")
def cv(s):
    c = s.post(f"{BASE}/clients", json={"name": "TEMP I24 Client", "phone": "0700000241"}).json()
    v = s.post(f"{BASE}/vehicles", json={"client_id": c["id"], "vin": "TMPI24VIN00000000", "plate": "TMP24I", "make": "Test",
                                        "model": "I24", "mileage": 1}).json()
    yield c["id"], v["id"]
    appts = [str(a["_id"]) for a in db.appointments.find({"client_id": c["id"]})]
    db.appointments.delete_many({"client_id": c["id"]})
    db.notifications.delete_many({"appointment_id": {"$in": appts}})
    wos = [str(w["_id"]) for w in db.work_orders.find({"client_id": c["id"]})]
    db.work_orders.delete_many({"client_id": c["id"]})
    db.audit_logs.delete_many({"entity_id": {"$in": appts + wos + [c["id"], v["id"]]}})
    db.vehicles.delete_one({"_id": ObjectId(v["id"])})
    db.clients.delete_one({"_id": ObjectId(c["id"])})


def body(cv, h, **kw):
    return {"client_id": cv[0], "vehicle_id": cv[1], "title": "TEMP I24 appt",
            "starts_at": f"2031-05-06T{h:02d}:00:00Z", "ends_at": f"2031-05-06T{h + 1:02d}:00:00Z", **kw}


def test_post_ignores_client_advisor_and_status(s, me, cv):
    r = s.post(f"{BASE}/appointments", json=body(cv, 8, advisor="HACKER Advisor", status="finalizat", work_order_id="x"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["advisor"] == me["name"] and d["advisor"] != "HACKER Advisor"
    assert d["status"] == "programat" and d["work_order_id"] == ""
    doc = db.appointments.find_one({"_id": ObjectId(d["id"])})
    assert doc["advisor"] == me["name"]


def test_put_overrides_advisor_with_logged_user(s, me, cv):
    aid = s.post(f"{BASE}/appointments", json=body(cv, 10)).json()["id"]
    db.appointments.update_one({"_id": ObjectId(aid)}, {"$set": {"advisor": "OLD Advisor"}})
    r = s.put(f"{BASE}/appointments/{aid}", json=body(cv, 10, advisor="HACKER Advisor", status="anulat", title="TEMP I24 edited"))
    assert r.status_code == 200, r.text
    assert r.json()["advisor"] == me["name"] and r.json()["status"] == "programat"
    g = [a for a in s.get(f"{BASE}/appointments", params={"start": "2031-05-06T00:00:00Z", "end": "2031-05-07T00:00:00Z"}).json() if a["id"] == aid][0]
    assert g["advisor"] == me["name"] and g["title"] == "TEMP I24 edited"


def test_mechanic_single_persisted_and_wo_advisor(s, me, cv):
    mechs = s.get(f"{BASE}/mechanics").json()
    if not mechs:
        pytest.skip("no mechanics")
    mid = mechs[0]["id"]
    aid = s.post(f"{BASE}/appointments", json=body(cv, 13, mechanic_ids=[mid])).json()["id"]
    assert db.appointments.find_one({"_id": ObjectId(aid)})["mechanic_ids"] == [mid]
    r = s.post(f"{BASE}/appointments/{aid}/status", json={"status": "in_lucru"})
    assert r.status_code == 200, r.text
    wo = s.get(f"{BASE}/work-orders/{r.json()['work_order_id']}").json()
    assert wo["advisor"] == me["name"] and wo["mechanic_ids"] == [mid]


def test_other_user_put_becomes_advisor(s, cv):
    dpw = re.search(r"password for all: (\S+?)\)?$", _txt, re.M)
    if not dpw:
        pytest.skip("demo pw not found")
    try:
        other = login("receptie@serviceauto.ro", dpw.group(1).rstrip(")"))
    except AssertionError:
        pytest.skip("receptie login failed")
    other_me = other.get(f"{BASE}/auth/me").json()
    aid = s.post(f"{BASE}/appointments", json=body(cv, 16)).json()["id"]
    r = other.put(f"{BASE}/appointments/{aid}", json=body(cv, 16, advisor="X"))
    if r.status_code in (403, 404):
        pytest.skip(f"receptie cannot access owner tenant appointment: {r.status_code}")
    assert r.status_code == 200, r.text
    assert r.json()["advisor"] == other_me["name"]
