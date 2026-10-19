# Iteration 27: stress race of concurrent custom_subdomain saves (FULL vs ENTERPRISE); expects only 200/400, never 500.
import concurrent.futures as cf
import json
import os
import threading

import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
S = json.load(open("/tmp/iter25.json"))
SESS = {p: requests.Session() for p in ("FULL", "ENTERPRISE")}
for p, s in SESS.items():
    s.headers["Authorization"] = f"Bearer {S['tenants'][p]['token']}"

counts = {}
for i in range(25):
    sd = f"temp27race-{S['suf']}-{i}"
    bar = threading.Barrier(4)

    def put(p):
        bar.wait()
        return SESS[p].put(f"{BASE}/settings", json={"custom_subdomain": sd}).status_code

    with cf.ThreadPoolExecutor(4) as ex:
        res = list(ex.map(put, ["FULL", "ENTERPRISE", "FULL", "ENTERPRISE"]))
    for c in res:
        counts[c] = counts.get(c, 0) + 1
    if 500 in res:
        print("500 in round", i, res)
    for s in SESS.values():
        s.put(f"{BASE}/settings", json={"custom_subdomain": ""})
print("status counts:", counts)
assert 500 not in counts
