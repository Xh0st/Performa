# Iter28 invoice search fixture: inserts TEMP invoices directly in DB (same tenant/branch as existing), teardown removes them
import os, sys, asyncio, copy
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


async def main(cmd):
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    if cmd == "teardown":
        r = await db.invoices.delete_many({"series": "TMP"})
        print("deleted", r.deleted_count, "left", await db.invoices.count_documents({"series": "TMP"}))
        return
    tpl = await db.invoices.find_one({"type": "fiscal", "kind": {"$exists": False}}, sort=[("created_at", -1)])
    tpl.pop("_id")
    docs = []
    base = datetime.now(timezone.utc) + timedelta(days=1)
    # 25 fiscal TEMP: 0-9 unpaid, 10-19 paid, 20-24 partial; 5 proforma TEMP
    for i in range(30):
        d = copy.deepcopy(tpl)
        proforma = i >= 25
        d.update({
            "type": "proforma" if proforma else "fiscal",
            "series": "TMP", "number": f"9{i:05d}",
            "work_order_number": f"TEMP-WO-{i:03d}",
            "vehicle": f"TEMP Make · TMP{i:02d}XYZ · VIN TEMPVIN{i:010d}",
            "buyer": {**tpl["buyer"], "name": f"TEMP Search Client {i:02d}", "cui": f"RO7777{i:04d}"},
            "totals": {"net": 100.0, "vat": 21.0, "gross": 121.0, "by_type": {"labor": 100.0}},
            "created_at": (base + timedelta(seconds=i)).isoformat(),
        })
        st = "unpaid" if (i < 10 or proforma) else ("paid" if i < 20 else "partial")
        d["status"] = st
        d["paid_amount"] = 121.0 if st == "paid" else (50.0 if st == "partial" else 0.0)
        d.pop("storno_status", None); d.pop("credited_amount", None)
        docs.append(d)
    await db.invoices.insert_many(docs)
    print("inserted", len(docs))


asyncio.run(main(sys.argv[1]))
