# Iter28 fixture: reuses iter27 pagination fixture (45 clients/vehicles, 25 products) + 15 TEMP active work orders for kanban totals; DB teardown
import os, sys, json, asyncio, requests
sys.path.insert(0, os.path.dirname(__file__))
import iter27_pagination_fixture as f27
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

STATE = "/tmp/iter28_wo.json"
SIG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def setup():
    f27.setup()
    s = f27.login()
    st27 = json.load(open(f27.STATE))
    vehicles = {v["client_id"]: v["id"] for v in s.get(f"{f27.BASE}/vehicles").json()}
    seq_before = asyncio.run(get_seq())
    wos = []
    for cid in st27["clients"][:15]:
        r = s.post(f"{f27.BASE}/work-orders", json={"client_id": cid, "vehicle_id": vehicles[cid], "mileage_in": 1000,
                                                     "complaint": "TEMP ITER28 kanban", "signature": SIG, "photos": {}})
        if not r.ok:
            print("wo fail", r.status_code, r.text[:300]); break
        wos.append(r.json())
    json.dump({"wos": wos, "seq_before": seq_before}, open(STATE, "w"))
    print("WO created", len(wos), "active now", len(s.get(f"{f27.BASE}/work-orders?active=true").json()))


async def get_seq():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    d = c[os.environ["DB_NAME"]]
    docs = await d.counters.find({}).to_list(100)
    return {str(x.get("_id")): x.get("seq", x.get("value")) for x in docs}


async def restore_seq(st):
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    d = c[os.environ["DB_NAME"]]
    n = len(st.get("wos", []))
    for k, v in (st.get("seq_before") or {}).items():
        if k.endswith(":work_order"):
            cur = await d.counters.find_one({"_id": k})
            if cur and cur.get("seq") == v + n:
                await d.counters.update_one({"_id": k}, {"$set": {"seq": v}})
                print("restored counter", k, v)


def teardown():
    st = json.load(open(STATE)) if os.path.exists(STATE) else {"wos": []}

    async def clean():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        for dbn in await c.list_database_names():
            if dbn in ("admin", "local", "config"):
                continue
            d = c[dbn]
            r = await d.work_orders.delete_many({"complaint": "TEMP ITER28 kanban"})
            if r.deleted_count:
                ids = [w["id"] for w in st["wos"]]
                a = await d.audit_logs.delete_many({"entity": "work_order", "entity_id": {"$in": ids}})
                print("deleted audit", a.deleted_count)
                print("deleted WOs", dbn, r.deleted_count)
    asyncio.run(clean())
    asyncio.run(restore_seq(st))
    f27.teardown()


if __name__ == "__main__":
    {"setup": setup, "teardown": teardown}[sys.argv[1]]()
