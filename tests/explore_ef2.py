import requests
B = "https://auto-service-pro-49.preview.emergentagent.com/api"
s = requests.Session()
s.post(f"{B}/auth/login", json={"email": "andrei.melek@gmail.com", "password": "Admin2026!"})
from collections import Counter
invs = s.get(f"{B}/invoices").json()
print(Counter((i["type"], i.get("efactura", {}).get("status")) for i in invs))
for i in invs:
    if i["type"] == "fiscal" and i.get("efactura", {}).get("status") not in ("ok",):
        print(i["id"], i["series"], i["number"], i["efactura"].get("status"), i["efactura"].get("env"))
wos = s.get(f"{B}/work-orders").json()
print([(w["id"], w["number"], w["status"], len(w.get("lines", []))) for w in wos if w["status"] == "finalizata"])
logs = s.get(f"{B}/efactura/logs").json()
for l in logs[:10]:
    print("log", l["at"], l["op"], l["ok"], l["env"], l["message"][:100])
