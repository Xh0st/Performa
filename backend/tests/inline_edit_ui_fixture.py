# UI fixture for iteration 9 inline line edit. CLI: python inline_edit_ui_fixture.py setup|teardown (state /tmp/inline_ui.json)
import sys
import json
from datetime import datetime, timezone
from bson import ObjectId
from warranty_fixtures import mdb

STATE = "/tmp/inline_ui.json"


def iso():
    return datetime.now(timezone.utc).isoformat()


def setup():
    db = mdb()
    cid = db.clients.insert_one({"name": "TEST_Client InlineUI", "type": "pf", "phone": "0700000001", "email": "t@example.com", "created_at": iso()}).inserted_id
    vid = db.vehicles.insert_one({"client_id": str(cid), "vin": "TESTINLINEUI00000", "plate": "TS99UIX", "make": "Test", "model": "Car",
                                  "mileage": 1000, "created_at": iso()}).inserted_id
    lines = [
        {"id": "ui_part", "type": "part", "description": "TEST piesa UI", "qty": 2, "unit_price": 100, "discount": 0, "vat_rate": 21,
         "product_id": "", "code": "P-UI", "unit": "buc", "source_warehouse": "Depozit Central"},
        {"id": "ui_lab", "type": "labor", "description": "TEST manopera UI", "qty": 1, "unit_price": 150, "discount": 0, "vat_rate": 21,
         "product_id": "", "code": "", "unit": "ore", "labor_category": "mecanic_senior", "norm_source": "Manual", "mechanic_id": ""},
    ]
    ids = {}
    for key, status in (("open", "diagnosticare"), ("final", "finalizata")):
        ids[key] = str(db.work_orders.insert_one({"number": f"TEST-INLINEUI-{key}", "client_id": str(cid), "vehicle_id": str(vid), "status": status,
                                                  "mileage_in": 1000, "complaint": "TEST", "lines": [dict(x) for x in lines], "quotes": [], "qc": {},
                                                  "status_history": [{"status": status, "at": iso(), "by": "TEST", "note": ""}],
                                                  "created_at": iso(), "reception": {}, "mechanic_ids": []}).inserted_id)
    json.dump({"cid": str(cid), "vid": str(vid), **ids}, open(STATE, "w"))
    print(json.dumps(ids))


def teardown():
    db = mdb()
    st = json.load(open(STATE))
    wids = [st["open"], st["final"]]
    db.work_orders.delete_many({"vehicle_id": st["vid"]})
    db.audit_logs.delete_many({"entity_id": {"$in": wids}})
    db.notifications.delete_many({"work_order_id": {"$in": wids}})
    db.time_entries.delete_many({"work_order_id": {"$in": wids}})
    db.vehicles.delete_one({"_id": ObjectId(st["vid"])})
    db.clients.delete_one({"_id": ObjectId(st["cid"])})
    print("teardown ok", db.work_orders.count_documents({"number": {"$regex": "INLINEUI"}}))


if __name__ == "__main__":
    {"setup": setup, "teardown": teardown}[sys.argv[1]]()
