# Iter21 UI fixture: TEMP client/vehicle + 2 appointments (one converted to WO) for owner tenant. CLI: setup|teardown|check
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
STATE = "/tmp/iter21_ui.json"
PW = re.search(r"andrei\.melek@gmail\.com / (\S+)", open("/app/memory/test_credentials.md").read()).group(1)
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def sess():
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": "andrei.melek@gmail.com", "password": PW})
    r.raise_for_status()
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


def setup():
    s = sess()
    c = s.post(f"{BASE}/clients", json={"name": "TEMP UI21 Client", "phone": "0700000221"}).json()
    v = s.post(f"{BASE}/vehicles", json={"client_id": c["id"], "vin": "TMPUI21VIN0000000", "plate": "TMP21UI", "make": "Test",
                                        "model": "UI21", "mileage": 10}).json()
    d = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
    ids = []
    for i, t in enumerate(("TEMP UI21 Converted", "TEMP UI21 Plain")):
        st = d + timedelta(hours=2 * i)
        r = s.post(f"{BASE}/appointments", json={"client_id": c["id"], "vehicle_id": v["id"], "title": t,
                                                  "starts_at": st.isoformat().replace("+00:00", "Z"),
                                                  "ends_at": (st + timedelta(hours=1)).isoformat().replace("+00:00", "Z")})
        r.raise_for_status()
        ids.append(r.json()["id"])
    wo = s.post(f"{BASE}/appointments/{ids[0]}/status", json={"status": "in_lucru"}).json()["work_order_id"]
    st = {"client": c["id"], "vehicle": v["id"], "appts": ids, "wo": wo, "day": d.date().isoformat()}
    json.dump(st, open(STATE, "w"))
    print(json.dumps(st))


def check():
    st = json.load(open(STATE))
    print({"appts_left": [a for a in st["appts"] if db.appointments.find_one({"_id": ObjectId(a)})],
           "wo_exists": bool(db.work_orders.find_one({"_id": ObjectId(st["wo"])})),
           "notif_left": db.notifications.count_documents({"appointment_id": {"$in": st["appts"]}})})


def teardown():
    st = json.load(open(STATE))
    print({"appts": db.appointments.delete_many({"client_id": st["client"]}).deleted_count,
           "notifs": db.notifications.delete_many({"appointment_id": {"$in": st["appts"]}}).deleted_count,
           "wos": db.work_orders.delete_many({"client_id": st["client"]}).deleted_count,
           "veh": db.vehicles.delete_many({"_id": ObjectId(st["vehicle"])}).deleted_count,
           "cli": db.clients.delete_many({"_id": ObjectId(st["client"])}).deleted_count,
           "audit": db.audit_logs.delete_many({"entity_id": {"$in": st["appts"] + [st["wo"]]}}).deleted_count})


if __name__ == "__main__":
    {"setup": setup, "teardown": teardown, "check": check}[sys.argv[1]]()
