# Iteration 27: GET /invoices/{id} on an invoice without an efactura subdocument must return 200 (no KeyError).
import asyncio
import json
import os

import requests
from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
S = json.load(open("/tmp/iter25.json"))
fid = S["tenants"]["FULL"]["docs"]["fiscal"]
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
asyncio.run(db.invoices.update_one({"_id": ObjectId(fid)}, {"$unset": {"efactura": ""}}))
r = requests.get(f"{BASE}/invoices/{fid}", headers={"Authorization": f"Bearer {S['tenants']['FULL']['token']}"})
print(r.status_code, r.json().get("efactura"))
assert r.status_code == 200 and r.json()["efactura"]["has_receipt"] is False
print("PASS")
