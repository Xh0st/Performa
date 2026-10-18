# UI fixture for closure review: python closure_ui_fixture.py setup|teardown (state in /tmp/closure_ui_state.json)
import sys
import json
import secrets
from datetime import datetime, timezone
from bson import ObjectId
from warranty_fixtures import mdb

STATE = "/tmp/closure_ui_state.json"


def iso():
    return datetime.now(timezone.utc).isoformat()


def setup():
    db, tag = mdb(), secrets.token_hex(3).upper()
    cid = db.clients.insert_one({"name": f"TEST_Client UI {tag}", "type": "pf", "phone": "0700000000", "created_at": iso()}).inserted_id
    vid = db.vehicles.insert_one({"client_id": str(cid), "vin": f"TESTUI{tag}".ljust(17, "0")[:17], "plate": f"TU{tag}", "make": "Test",
                                  "model": "Car", "mileage": 1000, "created_at": iso()}).inserted_id
    ids = {}
    for key, st, closed in (("A", "inchisa", True), ("B", "inchisa", True), ("C", "in_lucru", False)):
        doc = {"number": f"TEST-UI{tag}-{key}", "client_id": str(cid), "vehicle_id": str(vid), "status": st, "mileage_in": 1000,
               "complaint": "TEST", "lines": [], "quotes": [{"version": 1, "status": "approved", "number": "DV-T"}], "qc": {},
               "status_history": [{"status": "in_lucru", "at": iso(), "by": "TEST", "note": ""}], "created_at": iso(), "reception": {}, "mechanic_ids": []}
        if closed:
            doc |= {"pre_closure_status": "in_lucru", "closed_at": iso(),
                    "closure_quote_rule": {"allowed": True, "reason": "inchidere_nefacturata", "review": True}}
            doc["status_history"].append({"status": "inchisa", "at": iso(), "by": "TEST", "note": ""})
        ids[key] = str(db.work_orders.insert_one(doc).inserted_id)
    st = {"tag": tag, "cid": str(cid), "vid": str(vid), "ids": ids}
    json.dump(st, open(STATE, "w"))
    print(json.dumps(st))


def teardown():
    db, st = mdb(), json.load(open(STATE))
    ids = list(st["ids"].values())
    db.work_orders.delete_many({"vehicle_id": st["vid"]})
    db.audit_logs.delete_many({"entity_id": {"$in": ids}})
    db.vehicles.delete_one({"_id": ObjectId(st["vid"])})
    db.clients.delete_one({"_id": ObjectId(st["cid"])})
    print("residue", db.work_orders.count_documents({"number": {"$regex": st["tag"]}}))


if __name__ == "__main__":
    setup() if sys.argv[1] == "setup" else teardown()
