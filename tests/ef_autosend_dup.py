# Auto-send on fiscal invoice issue + duplicate re-import edge cases (one-off; creates real invoice from WO CL-2026-00074)
import time, requests
B = "https://auto-service-pro-49.preview.emergentagent.com/api"
s = requests.Session()
s.post(f"{B}/auth/login", json={"email": "andrei.melek@gmail.com", "password": "Admin2026!"})
print("cfg", {k: v for k, v in s.get(f"{B}/efactura/config").json().items() if k in ("environment", "auto_send")})
r = s.post(f"{B}/invoices/from-work-order/6ad30affff3439dd9e54f0c6", json={"type": "fiscal"})
print("issue", r.status_code, r.text[:200] if r.status_code != 200 else "")
if r.status_code == 200:
    inv = r.json()
    print("invoice", inv["id"], inv["series"], inv["number"], "status at creation", inv["efactura"]["status"])
    time.sleep(3)
    ef = s.get(f"{B}/invoices/{inv['id']}").json()["efactura"]
    print("after 3s:", ef["status"], ef.get("upload_index"), ef.get("env"), ef.get("errors"))
# duplicate re-import
xml = open("/app/tests/efactura_duplicate_F-1000.xml").read()
print("reimport", s.post(f"{B}/efactura/inbox/upload", json={"filename": "dup2.xml", "content": xml}).status_code)
msgs = [m for m in s.get(f"{B}/efactura/inbox").json() if m["parsed"]["series_number"] == "F-1000"]
print("F-1000 inbox rows:", len(msgs), [m["status"] for m in msgs])
new = next(m for m in msgs if m["status"] == "parsed")
d = s.get(f"{B}/efactura/inbox/{new['id']}").json()
print("dup detected:", d["duplicate_nir"] and d["duplicate_nir"]["number"])
body = {"mappings": [{"idx": 0, "product_id": d["suggestions"]["0"]}, {"idx": 1, "product_id": d["suggestions"]["1"]}]}
c = s.post(f"{B}/efactura/inbox/{new['id']}/create-nir", json=body)
print("create-nir dup:", c.status_code, c.json().get("detail"))
l = s.post(f"{B}/efactura/inbox/{new['id']}/link/{d['duplicate_nir']['id']}", json=body)
print("link to already-linked NIR:", l.status_code, l.json().get("detail"))
print("NEW_MSG_ID", new["id"])
