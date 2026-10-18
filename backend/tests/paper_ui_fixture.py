# UI fixture for paper approval test: python paper_ui_fixture.py setup|teardown (state in /tmp/paper_ui.json)
import sys
import json
import secrets
from bson import ObjectId
from warranty_fixtures import BASE, mdb, session, iso

STATE = "/tmp/paper_ui.json"
LINE = [{"id": "pu_lab", "type": "labor", "description": "TEST manopera", "qty": 1, "unit_price": 100, "discount": 0, "vat_rate": 21,
         "product_id": "", "code": "", "unit": "ore"}]


def setup():
    db, s = mdb(), session()
    tag = "PUI" + secrets.token_hex(3).upper()
    cid = db.clients.insert_one({"name": f"TEST_Client {tag}", "type": "pf", "phone": "0700000000", "created_at": iso()}).inserted_id
    vid = db.vehicles.insert_one({"client_id": str(cid), "vin": f"TEST{tag}".ljust(17, "0")[:17], "plate": f"TS{tag}",
                                  "make": "Test", "model": "Car", "mileage": 1000, "created_at": iso()}).inserted_id
    ids = {}
    for k in ("draft", "approved"):
        wid = str(db.work_orders.insert_one({"number": f"TEST-{tag}-{k}", "client_id": str(cid), "vehicle_id": str(vid), "status": "diagnosticare",
                                             "mileage_in": 1000, "complaint": "TEST", "lines": [dict(x) for x in LINE], "quotes": [], "qc": {},
                                             "status_history": [], "created_at": iso(), "reception": {}, "mechanic_ids": []}).inserted_id)
        s.post(f"{BASE}/work-orders/{wid}/quotes", json={"valid_days": 7}).raise_for_status()
        ids[k] = wid
    st = {"tag": tag, "client": str(cid), "vehicle": str(vid), "wos": ids}
    json.dump(st, open(STATE, "w"))
    print(json.dumps(st))


def teardown():
    db = mdb()
    st = json.load(open(STATE))
    wids = list(st["wos"].values())
    r = {"wo": db.work_orders.delete_many({"$or": [{"_id": {"$in": [ObjectId(w) for w in wids]}}, {"vehicle_id": st["vehicle"]}]}).deleted_count,
         "veh": db.vehicles.delete_one({"_id": ObjectId(st["vehicle"])}).deleted_count,
         "cli": db.clients.delete_one({"_id": ObjectId(st["client"])}).deleted_count,
         "audit": db.audit_logs.delete_many({"entity_id": {"$in": wids}}).deleted_count,
         "residue": db.work_orders.count_documents({"number": {"$regex": st["tag"]}}) + db.clients.count_documents({"name": {"$regex": st["tag"]}})}
    print(r)


if __name__ == "__main__":
    setup() if sys.argv[1] == "setup" else teardown()
