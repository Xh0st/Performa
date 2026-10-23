import os
import secrets
from datetime import timedelta
from core import db, now, hash_password, verify_password, next_seq, calc_totals
from routes_stock import receive_stock

SETTINGS = {
    "name": "[Denumire Service Auto] SRL", "cui": "RO[CUI]", "reg_com": "J[XX]/[nr]/[an]", "address": "[Adresă sediu]",
    "city": "[Oraș]", "county_code": "RO-B", "iban": "RO[IBAN]", "bank": "[Bancă]", "phone": "[Telefon]",
    "email": "[email@service.ro]", "capital": "[Capital social]", "rar_authorization": "[Nr. autorizație RAR]",
    "vat_rate": 21, "invoice_series": "SRV", "proforma_series": "PF", "payment_terms_days": 15, "currency": "RON",
    "labor_rates": {"mecanic_junior": 120, "mecanic_senior": 180, "electrician": 200, "tinichigiu": 170, "vopsitor": 170, "diagnoza": 220},
    "elevators": ["Elevator 1", "Elevator 2", "Elevator 3", "Elevator 4", "Banc diagnoză"],
    "warehouses": ["Depozit Central", "Magazie Atelier"],
}

DEMO_USERS = [("sef.service@serviceauto.ro", "Șef Service Demo", "sef_service"), ("receptie@serviceauto.ro", "Recepție Demo", "receptioner"),
              ("mecanic@serviceauto.ro", "Andrei Popescu", "mecanic"), ("contabil@serviceauto.ro", "Contabil Demo", "contabil"),
              ("casier@serviceauto.ro", "Casier Demo", "casier"), ("magazie@serviceauto.ro", "Magazioner Demo", "magazioner"),
              ("director@serviceauto.ro", "Director Demo", "director")]

MECHANICS = [("Andrei Popescu", "mecanic_senior", 55), ("Mihai Ionescu", "mecanic_junior", 35), ("Florin Dumitru", "electrician", 60),
             ("Cristian Stan", "tinichigiu", 50), ("Vasile Marin", "vopsitor", 50), ("Gabriel Toma", "diagnoza", 65)]

PRODUCTS = [("FU-OL-001", "Filtru ulei", "03N115562", "MANN W 712/95", "MANN", 28, 55, "A1-01"),
            ("FU-AE-002", "Filtru aer", "5Q0129620B", "BOSCH F026400287", "BOSCH", 45, 89, "A1-02"),
            ("FU-HA-003", "Filtru habitaclu carbon", "5Q0819653", "MANN CUK 26 009", "MANN", 52, 99, "A1-03"),
            ("FU-CB-004", "Filtru combustibil", "5Q0127177", "BOSCH F026402850", "BOSCH", 85, 159, "A1-04"),
            ("UL-5W30-5", "Ulei motor 5W30 5L", "G052195M4", "CASTROL EDGE 5W30", "CASTROL", 160, 279, "B2-01"),
            ("PL-FA-010", "Plăcuțe frână față", "5Q0698151", "TRW GDB1550", "TRW", 140, 260, "C1-01"),
            ("PL-SP-011", "Plăcuțe frână spate", "5Q0698451", "TRW GDB1955", "TRW", 110, 210, "C1-02"),
            ("DI-FA-012", "Disc frână față (buc)", "5Q0615301F", "BREMBO 09.A426.11", "BREMBO", 180, 320, "C1-03"),
            ("KD-DIS-020", "Kit distribuție cu pompă apă", "04L198119A", "INA 530055032", "INA", 690, 1190, "D1-01"),
            ("AM-FA-030", "Amortizor față", "5Q0413031", "SACHS 315 004", "SACHS", 290, 520, "D2-01"),
            ("BU-HC-040", "Bujie iridium", "04E905612C", "NGK ILKAR7B11", "NGK", 42, 79, "A2-01"),
            ("BT-70AH-050", "Baterie 70Ah", "000915105DE", "VARTA E39", "VARTA", 420, 690, "E1-01"),
            ("LA-H7-060", "Bec H7", "N10721802", "OSRAM 64210NL", "OSRAM", 18, 39, "A3-01"),
            ("LC-G13-070", "Antigel G13 1.5L", "G013A8JM1", "VAG G13", "VAG", 38, 69, "B2-02"),
            ("LF-DOT4-080", "Lichid frână DOT4 1L", "B000750M3", "ATE TYP200", "ATE", 35, 65, "B2-03"),
            ("KA-AMB-090", "Kit ambreiaj", "03L141016", "LUK 624 3478 33", "LUK", 980, 1650, "D1-02"),
            ("CU-AC-100", "Curea accesorii", "03L903137", "CONTITECH 6PK1153", "CONTITECH", 75, 139, "A2-02"),
            ("SE-ABS-110", "Senzor ABS", "WHT003856", "ATE 24.0711-6219.3", "ATE", 120, 230, "E1-02")]

SUPPLIERS = ["LKQ RO", "Autonet Import", "Inter Cars România", "Unix Auto", "ATP Exodus", "AD Auto Total"]

CLIENTS = [("pf", "Ion Georgescu", "Str. Lalelelor 12", "București", "RO-B"), ("pf", "Maria Constantinescu", "Bd. Unirii 45", "București", "RO-B"),
           ("pj", "Transport Rapid Demo SRL", "Str. Industriilor 3", "Ploiești", "RO-PH"), ("pf", "Alexandru Radu", "Str. Mihai Viteazu 8", "Brașov", "RO-BV"),
           ("pj", "Logistic Fleet Demo SA", "Calea Victoriei 120", "București", "RO-B"), ("pf", "Elena Dobre", "Str. Florilor 22", "Cluj-Napoca", "RO-CJ"),
           ("pf", "George Munteanu", "Aleea Teilor 5", "Iași", "RO-IS"), ("pj", "Construct Demo SRL", "Șos. Giurgiului 210", "București", "RO-B")]

VEHICLES = [("Volkswagen", "Golf VII", 2017, "1.6 TDI", 85, "6", "diesel"), ("Skoda", "Octavia III", 2019, "2.0 TDI", 110, "6", "diesel"),
            ("Dacia", "Logan II", 2020, "1.0 SCe", 54, "6", "benzina"), ("Ford", "Transit Custom", 2018, "2.0 EcoBlue", 96, "6", "diesel"),
            ("BMW", "Seria 3 G20", 2021, "320d", 140, "6", "diesel"), ("Renault", "Clio V", 2022, "1.0 TCe", 67, "6", "benzina"),
            ("Toyota", "Corolla", 2020, "1.8 Hybrid", 90, "6", "hibrid"), ("Mercedes-Benz", "Sprinter", 2019, "2.1 CDI", 105, "6", "diesel"),
            ("Audi", "A4 B9", 2018, "2.0 TFSI", 140, "6", "benzina"), ("Dacia", "Duster II", 2021, "1.5 dCi", 85, "6", "diesel"),
            ("Ford", "Focus IV", 2019, "1.5 EcoBlue", 88, "6", "diesel")]

JOBS = [("Revizie periodică", [("FU-OL-001", 1), ("UL-5W30-5", 1), ("FU-AE-002", 1), ("FU-HA-003", 1)], [("Schimb ulei și filtre", "mecanic_junior", 1.2)]),
        ("Zgomot la frânare", [("PL-FA-010", 1), ("DI-FA-012", 2)], [("Înlocuire discuri și plăcuțe față", "mecanic_senior", 1.8)]),
        ("Martor motor aprins", [("BU-HC-040", 4)], [("Diagnoză computerizată", "diagnoza", 0.5), ("Înlocuire bujii", "mecanic_senior", 0.8)]),
        ("Distribuție la termen", [("KD-DIS-020", 1), ("LC-G13-070", 2)], [("Înlocuire kit distribuție", "mecanic_senior", 3.5)]),
        ("Pornire greoaie", [("BT-70AH-050", 1)], [("Verificare sistem electric", "electrician", 0.7), ("Înlocuire baterie", "electrician", 0.3)]),
        ("Patinează ambreiajul", [("KA-AMB-090", 1)], [("Înlocuire kit ambreiaj", "mecanic_senior", 5.0)])]


def make_cnp(sex: int, yy: int, mm: int, dd: int, county: int) -> str:
    base = f"{sex}{yy:02d}{mm:02d}{dd:02d}{county:02d}{100 + secrets.randbelow(900)}"
    s = sum(int(base[i]) * int("279146358279"[i]) for i in range(12)) % 11
    return base + str(1 if s == 10 else s)


async def seed_admin():
    email, pwd = os.environ["ADMIN_EMAIL"].lower(), os.environ["ADMIN_PASSWORD"]
    u = await db.users.find_one({"email": email})
    if not u:
        await db.users.insert_one({"email": email, "name": "Administrator", "role": "admin", "active": True,
                                   "password_hash": hash_password(pwd), "created_at": now().isoformat()})
    elif not verify_password(pwd, u["password_hash"]):
        await db.users.update_one({"_id": u["_id"]}, {"$set": {"password_hash": hash_password(pwd)}})
    for e, n, r in DEMO_USERS:
        if not await db.users.find_one({"email": e}):
            await db.users.insert_one({"email": e, "name": n, "role": r, "active": True,
                                       "password_hash": hash_password(os.environ["DEMO_PASSWORD"]), "created_at": now().isoformat()})
    if not await db.settings.find_one({"_id": "company"}):
        await db.settings.insert_one({"_id": "company", **SETTINGS})


async def seed_demo():
    if await db.clients.count_documents({}) > 0:
        return
    t0 = now()
    mech_user = await db.users.find_one({"email": "mecanic@serviceauto.ro"})
    mids = []
    for i, (n, sp, cost) in enumerate(MECHANICS):
        r = await db.mechanics.insert_one({"name": n, "specialty": sp, "hourly_cost": cost, "phone": "", "active": True, "bonus_pct": 5,
                                           "user_id": str(mech_user["_id"]) if i == 0 else "", "created_at": t0.isoformat()})
        mids.append(str(r.inserted_id))
    sids = [str((await db.suppliers.insert_one({"name": s, "cui": "", "api_enabled": False, "created_at": t0.isoformat()})).inserted_id) for s in SUPPLIERS]
    pid = {}
    for code, name, oe, am, brand, cost, price, loc in PRODUCTS:
        r = await db.products.insert_one({"code": code, "name": name, "oe_code": oe, "aftermarket_code": am, "brand": brand, "category": "piese",
                                          "unit": "buc", "location": loc, "warehouse": "Depozit Central", "sale_price": price, "min_stock": 4,
                                          "vat_rate": 21, "warranty_months": 24, "stock_qty": 0, "avg_cost": 0, "created_at": t0.isoformat()})
        pid[code] = (str(r.inserted_id), name, cost, price)
    for n, chunk in enumerate([PRODUCTS[:9], PRODUCTS[9:]]):
        seq = await next_seq("nir")
        number, date = f"NIR-{t0.year}-{seq:05d}", (t0 - timedelta(days=150 - n * 40)).isoformat()
        lines = []
        for code, name, *_rest in chunk:
            p_id, _, cost, _ = pid[code]
            qty = secrets.choice([10, 12, 15, 20]) if cost < 500 else 5
            await receive_stock(p_id, qty, cost, number, date)
            lines.append({"product_id": p_id, "code": code, "name": name, "unit": "buc", "qty": qty, "unit_cost": cost,
                          "value": qty * cost, "vat": round(qty * cost * 0.21, 2), "lot": ""})
        await db.nirs.insert_one({"number": number, "supplier_id": sids[n], "supplier_name": SUPPLIERS[n], "invoice_no": f"F-{1000 + n}",
                                  "aviz_no": "", "date": date, "warehouse": "Depozit Central", "lines": lines,
                                  "total": round(sum(x["value"] for x in lines), 2), "total_vat": round(sum(x["vat"] for x in lines), 2),
                                  "created_by": "Seed", "created_at": date})
    s = SETTINGS
    cids, vids = [], []
    for i, (typ, name, addr, city, county) in enumerate(CLIENTS):
        doc = {"type": typ, "name": name, "cnp": make_cnp(1 + i % 2, 70 + i * 3, 1 + i, 10 + i, 40) if typ == "pf" else "",
               "cui": f"RO{10000000 + i * 1111}" if typ == "pj" else "", "reg_com": f"J40/{100 + i}/2015" if typ == "pj" else "",
               "representative": "Director Demo" if typ == "pj" else "", "phone": f"07{20000000 + i * 1357:08d}",
               "email": f"client{i + 1}@example.com", "address": addr, "city": city, "county": county, "is_fleet": typ == "pj",
               "budget_limit": 5000 if typ == "pj" else 0, "gdpr_consent": True, "notes": "", "created_at": (t0 - timedelta(days=200)).isoformat()}
        cids.append(str((await db.clients.insert_one(doc)).inserted_id))
    letters = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    for i, (make, model, year, eng, kw, euro, fuel) in enumerate(VEHICLES):
        owner = cids[i % len(cids)] if i < 8 else cids[[2, 4, 4][i - 8]]
        vin = "".join(secrets.choice(letters) for _ in range(17))
        doc = {"client_id": owner, "vin": vin, "plate": f"B {100 + i * 7} {secrets.choice(['ABC', 'XYZ', 'SRV', 'DMO'])}", "make": make,
               "model": model, "year": year, "engine": eng, "power_kw": kw, "euro": euro, "fuel": fuel, "mileage": 40000 + i * 17000,
               "color": "", "itp_expiry": (t0 + timedelta(days=-10 + secrets.randbelow(211))).date().isoformat(),
               "rca_expiry": (t0 + timedelta(days=5 + secrets.randbelow(296))).date().isoformat(), "casco_expiry": "",
               "rovinieta_expiry": (t0 + timedelta(days=-5 + secrets.randbelow(126))).date().isoformat(), "created_at": (t0 - timedelta(days=200)).isoformat()}
        vids.append((str((await db.vehicles.insert_one(doc)).inserted_id), owner, doc["mileage"]))

    async def make_wo(vidx, job, created, status):
        vid, cid, km = vids[vidx]
        complaint, parts, labors = job
        lines = []
        for code, q in parts:
            p_id, name, cost, price = pid[code]
            lines.append({"id": secrets.token_hex(5), "type": "part", "description": name, "qty": q, "unit_price": price, "discount": 0,
                          "vat_rate": 21, "product_id": p_id, "code": code, "unit": "buc", "unit_cost": cost, "labor_category": "", "norm_source": "", "mechanic_id": ""})
        cats = {sp: mids[i] for i, (_, sp, _) in enumerate(MECHANICS)}
        for desc, cat, hrs in labors:
            lines.append({"id": secrets.token_hex(5), "type": "labor", "description": desc, "qty": hrs, "unit_price": s["labor_rates"][cat],
                          "discount": 0, "vat_rate": 21, "product_id": "", "code": "", "unit": "ore", "labor_category": cat,
                          "norm_source": secrets.choice(["Autodata", "HaynesPro", "RAR"]), "mechanic_id": cats[cat]})
        seq = await next_seq("work_order")
        number = f"CL-{created.year}-{seq:05d}"
        done = status in ("finalizata", "facturata", "inchisa")
        finished = created + timedelta(hours=5 + secrets.randbelow(26))
        wo = {"number": number, "client_id": cid, "vehicle_id": vid, "status": status, "mileage_in": km, "complaint": complaint,
              "diagnosis": "Confirmat la verificare" if status != "noua" else "", "mechanic_ids": list({ln["mechanic_id"] for ln in lines if ln["mechanic_id"]}),
              "elevator": secrets.choice(s["elevators"][:4]) if status in ("diagnosticare", "in_lucru", "asteapta_piese", "aprobata") else "",
              "promised_date": (created + timedelta(days=2)).date().isoformat(), "advisor": "Recepție Demo",
              "reception": {"fuel_level": "1/2", "observations": "", "accessories": ["Roată rezervă", "Triunghi"], "damages": [],
                            "photos": {}, "signature": "", "at": created.isoformat(), "by": "Recepție Demo"},
              "lines": lines if status not in ("noua", "diagnosticare") else [], "quotes": [],
              "qc": {"items": {k: "ok" for k in ["frane", "directie", "suspensie", "lumini", "niveluri", "anvelope", "test_drive"]}, "passed": True,
                     "mechanic_signature": "", "chief_signature": "", "at": finished.isoformat(), "by": "Șef Service Demo"} if done else {},
              "created_at": created.isoformat(), "status_history": [{"status": "noua", "at": created.isoformat(), "by": "Recepție Demo", "note": "Recepție vehicul"}]}
        if done:
            wo["finished_at"] = finished.isoformat()
        r = await db.work_orders.insert_one(wo)
        wid = str(r.inserted_id)
        if status in ("facturata", "inchisa"):
            totals = calc_totals(lines)
            iseq = await next_seq("invoice")
            issue = finished.date()
            cl = await db.clients.find_one({"_id": r.inserted_id.__class__(cid)})
            vh = await db.vehicles.find_one({"_id": r.inserted_id.__class__(vid)})
            inv = {"type": "fiscal", "series": "SRV", "number": f"{iseq:06d}", "issue_date": issue.isoformat(),
                   "due_date": (issue + timedelta(days=15)).isoformat(), "currency": "RON", "work_order_id": wid, "work_order_number": number,
                   "client_id": cid, "vehicle": f"{vh['make']} {vh['model']} · {vh['plate']} · VIN {vh['vin']}", "mileage": km,
                   "seller": {k: s.get(k, "") for k in ("name", "cui", "reg_com", "address", "city", "county_code", "iban", "bank", "phone", "email", "capital", "subscription_plan", "custom_logo_data_url")},
                   "buyer": {"name": cl["name"], "cui": cl["cui"], "cnp": cl["cnp"], "reg_com": cl["reg_com"], "address": cl["address"],
                             "city": cl["city"], "county_code": cl["county"], "phone": cl["phone"], "email": cl["email"]},
                   "lines": lines, "totals": totals, "paid_amount": 0.0, "status": "unpaid",
                   "cogs": round(sum(ln["qty"] * ln.get("unit_cost", 0) for ln in lines if ln["type"] == "part"), 2),
                   "efactura": {"status": "ok", "upload_index": str(4000000000 + iseq), "history": [{"event": "Seed – validată (SIMULAT)", "at": finished.isoformat()}]},
                   "created_by": "Seed", "created_at": finished.isoformat()}
            ir = await db.invoices.insert_one(inv)
            await db.work_orders.update_one({"_id": r.inserted_id}, {"$set": {"invoice_id": str(ir.inserted_id), "invoiced_at": finished.isoformat()}})
            if secrets.randbelow(100) < 85:
                method = secrets.choice(["numerar", "pos", "transfer"])
                dt, pre = {"numerar": ("chitanta", "CH"), "pos": ("bon_pos", "POS"), "transfer": ("ordin_plata", "OP")}[method]
                pseq = await next_seq(f"pay_{dt}")
                pay_date = finished + timedelta(hours=2)
                if pay_date > t0:
                    pay_date = t0 - timedelta(minutes=5)
                await db.payments.insert_one({"invoice_id": str(ir.inserted_id), "invoice_ref": f"SRV{inv['number']}", "client_name": cl["name"],
                                              "amount": totals["gross"], "method": method, "doc_type": dt, "doc_number": f"{pre}-{pseq:06d}",
                                              "reference": "", "date": pay_date.isoformat(), "cashier": "Casier Demo"})
                await db.invoices.update_one({"_id": ir.inserted_id}, {"$set": {"paid_amount": totals["gross"], "status": "paid"}})

    for d in range(170, t0.day, -6):
        created = t0 - timedelta(days=d, hours=secrets.randbelow(6))
        await make_wo(secrets.randbelow(len(vids)), secrets.choice(JOBS), created, "inchisa" if d > 30 else "facturata")
    for d in range(t0.day - 1, 1, -1):
        for _ in range(3):
            created = t0 - timedelta(days=d, hours=30 + secrets.randbelow(11))
            if created.month == t0.month:
                await make_wo(secrets.randbelow(len(vids)), secrets.choice(JOBS), created, "facturata")
    current = [("noua", 0), ("diagnosticare", 2), ("asteapta_oferta", 1), ("aprobata", 3), ("in_lucru", 1), ("in_lucru", 3),
               ("asteapta_piese", 5), ("finalizata", 4), ("finalizata", 0)]
    for i, (st, j) in enumerate(current):
        await make_wo(i, JOBS[j], t0 - timedelta(hours=6 + i * 7), st)
    day = max(t0.replace(day=1), t0 - timedelta(days=9)).replace(hour=8, minute=0, second=0, microsecond=0)
    while day.date() < t0.date():
        if day.weekday() < 5:
            for mid in mids:
                await db.time_entries.insert_one({"mechanic_id": mid, "type": "attendance", "start": day.isoformat(), "end": (day + timedelta(hours=8)).isoformat()})
                await db.time_entries.insert_one({"mechanic_id": mid, "type": "work", "work_order_id": "", "work_order_number": "",
                                                  "start": (day + timedelta(minutes=30)).isoformat(),
                                                  "end": (day + timedelta(minutes=330 + secrets.randbelow(121))).isoformat()})
        day += timedelta(days=1)
