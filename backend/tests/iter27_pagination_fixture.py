# Iter27 pagination fixture: counts list sizes, creates TEMP clients/vehicles/products, teardown via API + DB
import os, sys, json, requests, asyncio
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
EMAIL, PW = "andrei.melek@gmail.com", "Admin2026!"
STATE = "/tmp/iter27_pag.json"


def login():
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PW})
    r.raise_for_status()
    return s


def counts(s):
    out = {}
    for p in ["clients", "vehicles", "invoices", "work-orders", "products", "nirs", "supplier-returns"]:
        r = s.get(f"{BASE}/{p}")
        out[p] = (r.status_code, len(r.json()) if r.ok and isinstance(r.json(), list) else r.text[:100])
    return out


def setup():
    s = login()
    print("BEFORE", counts(s))
    st = {"clients": [], "products": []}
    for i in range(45):
        r = s.post(f"{BASE}/clients", json={"type": "pf", "name": f"TEMP Pag Client {i:02d}", "phone": f"07000000{i:02d}", "city": "TEMP"})
        if not r.ok:
            print("client fail", r.status_code, r.text[:200]); break
        cid = r.json()["id"]; st["clients"].append(cid)
        vin = f"TEMPPAG{i:010d}"[:17].ljust(17, "0")
        rv = s.post(f"{BASE}/vehicles", json={"client_id": cid, "vin": vin, "plate": f"TMP{i:02d}PAG", "make": "TEMP", "model": "Pag"})
        if not rv.ok:
            print("vehicle fail", rv.status_code, rv.text[:200])
    for i in range(25):
        r = s.post(f"{BASE}/products", json={"code": f"TEMPPAG{i:02d}", "name": f"TEMP Pag Product {i:02d}", "unit": "buc", "sale_price": 1, "vat_rate": 21})
        if not r.ok:
            print("product fail", r.status_code, r.text[:200]); break
        st["products"].append(r.json()["id"])
    json.dump(st, open(STATE, "w"))
    print("AFTER", counts(s))


def teardown():
    s = login()
    st = json.load(open(STATE)) if os.path.exists(STATE) else {"clients": []}
    for cid in st["clients"]:
        s.delete(f"{BASE}/clients/{cid}")
    from motor.motor_asyncio import AsyncIOMotorClient

    async def db_clean():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        names = await c.list_database_names()
        tot = {}
        for dbn in names:
            if dbn in ("admin", "local", "config"):
                continue
            d = c[dbn]
            for coll, flt in [("clients", {"name": {"$regex": "^TEMP Pag"}}), ("vehicles", {"vin": {"$regex": "^TEMPPAG"}}),
                              ("products", {"code": {"$regex": "^TEMPPAG"}})]:
                r = await d[coll].delete_many(flt)
                if r.deleted_count:
                    tot[f"{dbn}.{coll}"] = r.deleted_count
        print("DB cleanup", tot)
    asyncio.run(db_clean())
    print("FINAL", counts(s))


if __name__ == "__main__":
    {"setup": setup, "teardown": teardown, "counts": lambda: print(counts(login()))}[sys.argv[1]]()
