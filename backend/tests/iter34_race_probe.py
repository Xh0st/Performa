# Probe: concurrent same-number DP payouts -> expect exactly 1x200, rest 400 (not 500). Cleans up.
import os, secrets
from concurrent.futures import ThreadPoolExecutor
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env"); load_dotenv("/app/backend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
line = [l for l in open("/app/memory/test_credentials.md").read().splitlines() if "andrei.melek" in l][0]
em, pw = [x.strip() for x in line.lstrip("- ").split("/")[:2]]
s = requests.Session()
assert s.post(f"{BASE}/auth/login", json={"email": em, "password": pw.split()[0]}).status_code == 200
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
before = {m["_id"] for m in db.cash_movements.find({}, {"_id": 1})}
num = str(900000 + secrets.randbelow(90000))
cookies = s.cookies.get_dict()


def go(_):
    r = requests.post(f"{BASE}/cash-register/payouts", cookies=cookies,
                      json={"kind": "payment_order", "beneficiary": "TEST_RACE34", "amount": 0.01, "document_number": num})
    return r.status_code


with ThreadPoolExecutor(8) as ex:
    codes = list(ex.map(go, range(8)))
print("codes", sorted(codes))
new = [m["_id"] for m in db.cash_movements.find({}, {"_id": 1}) if m["_id"] not in before]
print("created", len(new))
db.cash_movements.delete_many({"_id": {"$in": new}})
db.audit_logs.delete_many({"entity_id": {"$in": [str(i) for i in new]}})
