# Snapshot helper for inbox verification (stock, moves, NIR, suppliers)
import requests, json, sys
B = "https://auto-service-pro-49.preview.emergentagent.com/api"
s = requests.Session()
s.post(f"{B}/auth/login", json={"email": "andrei.melek@gmail.com", "password": "Admin2026!"})
prods = {p["code"]: p for p in s.get(f"{B}/products").json()}
for c in ("BU-HC-040", "SKF-VKPC81230", "FU-OL-001", "FU-AE-002"):
    p = prods.get(c)
    if p:
        moves = s.get(f"{B}/products/{p['id']}/moves").json()
        mv = moves if isinstance(moves, list) else moves.get("moves", [])
        print(c, "stock", p["stock_qty"], "avg", p.get("avg_cost"), "moves NIR-2026-00001:",
              [(m.get("kind"), m.get("qty"), m.get("unit_cost")) for m in mv if m.get("ref") == "NIR-2026-00001"], "total moves", len(mv))
    else:
        print(c, "MISSING")
print("suppliers:", [x["name"] for x in s.get(f"{B}/suppliers").json()])
for n in s.get(f"{B}/nirs").json()[:4]:
    print("nir", n["number"], n.get("invoice_no"), n.get("efactura_linked"), n.get("total"), [(l["code"], l["qty"], l["unit_cost"]) for l in n["lines"]][:3])
for m in s.get(f"{B}/efactura/inbox").json():
    print("inbox", m["id"], m["parsed"]["series_number"], m["status"], m.get("nir_number"), m.get("changes"))
