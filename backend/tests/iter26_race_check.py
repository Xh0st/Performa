# Iteration 26: concurrent custom_subdomain save race (FULL vs ENTERPRISE). Requires iter25 fixture state.
import json
import os
import concurrent.futures as cf

import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
S = json.load(open("/tmp/iter25.json"))
sd = f"temp26race-{S['suf']}"


def put(plan):
    h = {"Authorization": f"Bearer {S['tenants'][plan]['token']}"}
    r = requests.put(f"{BASE}/settings", json={"custom_subdomain": sd}, headers=h)
    return plan, r.status_code, r.text[:120]


for i in range(5):
    with cf.ThreadPoolExecutor(2) as ex:
        res = list(ex.map(put, ["FULL", "ENTERPRISE"]))
    print(res)
    for p in ("FULL", "ENTERPRISE"):
        requests.put(f"{BASE}/settings", json={"custom_subdomain": ""},
                     headers={"Authorization": f"Bearer {S['tenants'][p]['token']}"})
