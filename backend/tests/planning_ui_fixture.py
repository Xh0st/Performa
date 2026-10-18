# UI fixture for planning/QC/Anexa5 Playwright tests. CLI: python planning_ui_fixture.py setup|teardown  (state in /tmp/planning_ui.json)
import json
import sys
from datetime import datetime, timezone

from bson import ObjectId

sys.path.insert(0, "/app/backend/tests")
from storno_fixtures import mdb  # noqa: E402

STATE = "/tmp/planning_ui.json"


def setup():
    db = mdb()
    now = datetime.now(timezone.utc).isoformat()
    st = {"counters": {c: (db.counters.find_one({"_id": c}) or {}).get("seq") for c in ("work_order", "invoice")},
          "notif_before": [str(n["_id"]) for n in db.notifications.find({}, {"_id": 1})],
          "appt_before": [str(a["_id"]) for a in db.appointments.find({}, {"_id": 1})]}
    cid = db.clients.insert_one({"name": "TEST_UI Client", "type": "pf", "phone": "0700000009", "created_at": now}).inserted_id
    vid = db.vehicles.insert_one({"client_id": str(cid), "vin": "TESTUIVIN00000000", "plate": "TSTUI01", "make": "Test", "model": "UI",
                                  "mileage": 500, "created_at": now}).inserted_id
    lines = [{"id": "l_lab", "type": "labor", "description": "TEST Manopera", "qty": 1, "unit_price": 100, "discount": 0, "vat_rate": 21,
              "product_id": "", "code": "", "unit": "ore"}]
    wid = db.work_orders.insert_one({"number": "TEST-WO-UI-QC", "client_id": str(cid), "vehicle_id": str(vid), "status": "in_lucru",
                                     "mileage_in": 500, "lines": lines, "quotes": [], "qc": {}, "status_history": [], "created_at": now,
                                     "reception": {}, "mechanic_ids": []}).inserted_id
    st.update(client=str(cid), vehicle=str(vid), wo=str(wid))
    json.dump(st, open(STATE, "w"))
    print(json.dumps(st))


def teardown():
    db = mdb()
    st = json.load(open(STATE))
    wo_ids = [str(w["_id"]) for w in db.work_orders.find({"client_id": st["client"]}, {"_id": 1})]
    res = {
        "appointments": db.appointments.delete_many({"client_id": st["client"]}).deleted_count,
        "invoices": db.invoices.delete_many({"work_order_id": {"$in": wo_ids}}).deleted_count,
        "work_orders": db.work_orders.delete_many({"_id": {"$in": [ObjectId(w) for w in wo_ids]}}).deleted_count,
        "notifications": db.notifications.delete_many({"_id": {"$nin": [ObjectId(n) for n in st["notif_before"]]},
                                                       "kind": {"$in": ["appointment_confirmation", "appointment_reminder"]}}).deleted_count,
        "vehicles": db.vehicles.delete_many({"_id": ObjectId(st["vehicle"])}).deleted_count,
        "clients": db.clients.delete_many({"_id": ObjectId(st["client"])}).deleted_count,
        "audit": db.audit_logs.delete_many({"entity_id": {"$in": wo_ids}}).deleted_count,
    }
    for c, v in st["counters"].items():
        if v is not None:
            db.counters.update_one({"_id": c}, {"$set": {"seq": v}})
    print(res)


if __name__ == "__main__":
    setup() if sys.argv[1] == "setup" else teardown()
