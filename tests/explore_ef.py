import requests, json
B = "https://auto-service-pro-49.preview.emergentagent.com/api"
s = requests.Session()
r = s.post(f"{B}/auth/login", json={"email": "andrei.melek@gmail.com", "password": "Admin2026!"})
print("login", r.status_code, list(r.json().keys()), r.cookies.keys())
print("cfg", json.dumps(s.get(f"{B}/efactura/config").json(), ensure_ascii=False)[:800])
inbox = s.get(f"{B}/efactura/inbox").json()
for m in inbox:
    print("inbox", m["id"], m["parsed"]["series_number"], m["status"], m.get("nir_number"))
nirs = s.get(f"{B}/nirs").json() if s.get(f"{B}/nirs").status_code == 200 else s.get(f"{B}/stock/nirs").json()
for n in (nirs if isinstance(nirs, list) else [])[:5]:
    print("nir", n.get("id"), n.get("number"), n.get("invoice_no"), n.get("supplier_id"), [(l["code"], l["qty"], l["unit_cost"]) for l in n["lines"]], n.get("efactura_linked"))
prods = s.get(f"{B}/products").json()
for p in prods:
    if p["code"] in ("FU-OL-001", "FU-AE-002", "BU-HC-040", "SKF-VKPC81230"):
        print("prod", p["id"], p["code"], p["stock_qty"], p.get("avg_cost"))
invs = s.get(f"{B}/invoices").json()
for i in invs[:8]:
    print("inv", i["id"], i["type"], i.get("series"), i.get("number"), i.get("efactura", {}).get("status"))
print("settings", {k: v for k, v in s.get(f"{B}/settings").json().items() if k in ("name", "cui", "address", "city", "county_code")})
