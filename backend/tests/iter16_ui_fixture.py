# UI fixture for iter16 (settings/logo): create FULL+BASIC TEMP tenants with sparse settings, or cleanup. Usage: python iter16_ui_fixture.py create|delete|check
import asyncio
import base64
import os
import re
import sys
import json
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
sys.path.insert(0, "/app/backend")
from tenant_context import OPERATIONAL_COLLECTIONS  # noqa: E402

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
PW = re.search(r"andrei\.melek@gmail\.com / (\S+)", open("/app/memory/test_credentials.md").read()).group(1)
INIT, NEW = "TempInit2026!", "TempNew2026!x"
STATE = "/tmp/iter16_state.json"


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = "Bearer " + r.json()["token"]
    return s


async def db_cleanup(tids):
    d = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    for tid in tids:
        for col in OPERATIONAL_COLLECTIONS | {"cron_errors", "settings", "audit_logs"}:
            await d[col].delete_many({"tenant_id": tid})
        await d.users.delete_many({"tenant_id": tid})
        await d.branches.delete_many({"tenant_id": tid})
        await d.counters.delete_many({"_id": {"$regex": f"^{re.escape(tid)}:"}})
        await d.tenants.delete_one({"_id": tid})
    await d.users.delete_many({"email": {"$regex": "^temp_ui16_"}})
    await d.login_attempts.delete_many({"identifier": {"$regex": "temp_ui16_"}})
    left = {
        "tenants": await d.tenants.count_documents({"company_name": {"$regex": "^TEMP-ui16"}}),
        "users": await d.users.count_documents({"email": {"$regex": "^temp_ui16_"}}),
        "settings": await d.settings.count_documents({"tenant_id": {"$in": tids}}),
    }
    print("leftover:", left)


async def settings_doc(tid):
    d = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    doc = await d.settings.find_one({"tenant_id": tid, "kind": "company"}) or {}
    doc.pop("_id", None)
    if doc.get("custom_logo_data_url"):
        doc["custom_logo_data_url"] = f"<{len(doc['custom_logo_data_url'])} chars>"
    return doc


if sys.argv[1] == "create":
    o = login("andrei.melek@gmail.com", PW)
    st = {}
    for plan in ("FULL", "BASIC"):
        name = f"TEMP-ui16-{plan} SRL"
        email = f"temp_ui16_{plan.lower()}@example.com"
        r = o.post(f"{BASE}/platform/tenants", json={"company_name": name, "cui": f"RO-TEMPUI16{plan}", "admin_email": email,
                                                     "initial_password": INIT, "subscription_plan": plan})
        assert r.status_code == 200, r.text
        tid = r.json()["id"]
        s = login(email, INIT)
        r = s.post(f"{BASE}/auth/change-initial-password", json={"current_password": INIT, "new_password": NEW})
        assert r.status_code == 200, r.text
        st[plan] = {"id": tid, "email": email, "name": name}
    json.dump(st, open(STATE, "w"))
    for plan, v in st.items():
        print(plan, v["id"], "settings keys:", sorted(asyncio.run(settings_doc(v["id"])).keys()))
elif sys.argv[1] == "check":
    st = json.load(open(STATE))
    for plan, v in st.items():
        print(plan, asyncio.run(settings_doc(v["id"])))
elif sys.argv[1] == "inject":
    # PUT /settings with forbidden fields
    st = json.load(open(STATE))
    s = login(st["FULL"]["email"], NEW)
    png = "data:image/png;base64," + base64.b64encode(b"x").decode()
    body = {"name": "TEMP inject", "kind": "evil", "plan_limits": {"branches": 999}, "subscription_plan": "ENTERPRISE",
            "tenant_id": "tenant-evil", "branch_id": "branch-evil", "custom_logo_data_url": png,
            "custom_logo_mime": "image/evil", "custom_subdomain": None}
    r = s.put(f"{BASE}/settings", json=body)
    print("inject status", r.status_code, "resp subdomain", repr(r.json().get("custom_subdomain")),
          "resp mime", r.json().get("custom_logo_mime"), "resp plan", r.json().get("subscription_plan"))
    print("doc", asyncio.run(settings_doc(st["FULL"]["id"])))
    b = login(st["BASIC"]["email"], NEW)
    r = b.put(f"{BASE}/settings/logo", json={"data_url": png})
    print("BASIC direct logo:", r.status_code, r.text[:120])
else:
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    o = login("andrei.melek@gmail.com", PW)
    for plan, v in st.items():
        r = o.request("DELETE", f"{BASE}/platform/tenants/{v['id']}", json={"confirmation": v["name"]})
        print("delete", plan, r.status_code)
    asyncio.run(db_cleanup([v["id"] for v in st.values()]))
