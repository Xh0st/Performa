# UI fixture for iter15: create/delete TEMP tenant for reset-password UI test. Usage: python iter15_ui_fixture.py create|delete <id>
import os
import re
import sys
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
PW = re.search(r"andrei\.melek@gmail\.com / (\S+)", open("/app/memory/test_credentials.md").read()).group(1)
s = requests.Session()
s.headers["Authorization"] = "Bearer " + s.post(f"{BASE}/auth/login", json={"email": "andrei.melek@gmail.com", "password": PW}).json()["token"]
if sys.argv[1] == "create":
    r = s.post(f"{BASE}/platform/tenants", json={"company_name": "TEMP-ui15 SRL", "cui": "RO-TEMPUI15", "admin_email": "temp_ui15@example.com",
                                                 "initial_password": "TempInit2026!", "subscription_plan": "BASIC"})
    print(r.status_code, r.json().get("id"))
else:
    r = s.request("DELETE", f"{BASE}/platform/tenants/{sys.argv[2]}", json={"confirmation": "TEMP-ui15 SRL"})
    print(r.status_code, r.text)
