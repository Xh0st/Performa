# Cleanup for iter34 UI test data (TEST_UI34 payouts) + leftover check for TEST_ fixtures from iter34.
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
moves = list(db.cash_movements.find({"beneficiary": {"$regex": "^TEST_(UI34|B34|RACE34)"}}, {"_id": 1, "doc_number": 1, "kind": 1}))
print("UI/test movements:", [(m["kind"], m["doc_number"]) for m in moves])
db.audit_logs.delete_many({"entity_id": {"$in": [str(m["_id"]) for m in moves]}})
db.cash_movements.delete_many({"_id": {"$in": [m["_id"] for m in moves]}})
print("left movements:", db.cash_movements.count_documents({"beneficiary": {"$regex": "^TEST_(UI34|B34|RACE34)"}}))
print("left clients:", db.clients.count_documents({"name": {"$regex": "^TEST_PF34"}}))
print("left invoices:", db.invoices.count_documents({"series": "TSTQ"}))
print("left raw payments:", db.payments.count_documents({"client_id": "TEST_raw"}))
