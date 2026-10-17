from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from core import db, now, require
from routes_service import mechanic_stats

router = APIRouter(prefix="/api")


def month_keys(n=6):
    d = now().replace(day=1)
    keys = []
    for _ in range(n):
        keys.append(d.strftime("%Y-%m"))
        d = (d - timedelta(days=1)).replace(day=1)
    return list(reversed(keys))


@router.get("/dashboard")
async def dashboard(user=Depends(require("dashboard"))):
    month = now().strftime("%Y-%m")
    wos = await db.work_orders.find({}, {"status": 1, "created_at": 1, "finished_at": 1, "number": 1, "elevator": 1}).to_list(20000)
    by_status = {}
    for w in wos:
        by_status[w["status"]] = by_status.get(w["status"], 0) + 1
    invoices = await db.invoices.find({"type": "fiscal"}, {"issue_date": 1, "totals": 1, "cogs": 1, "lines": 1, "paid_amount": 1}).to_list(20000)
    payments = await db.payments.find({}, {"date": 1, "amount": 1, "method": 1}).to_list(20000)
    keys = month_keys()
    series = {k: {"month": k, "revenue": 0.0, "cogs": 0.0, "profit": 0.0, "collected": 0.0, "labor": 0.0, "parts": 0.0} for k in keys}
    parts_rev = parts_cost = 0.0
    inv_month = {"count": 0, "gross": 0.0}
    for inv in invoices:
        k = inv["issue_date"][:7]
        bt = inv["totals"].get("by_type", {})
        if k in series:
            s = series[k]
            s["revenue"] += inv["totals"]["net"]
            s["cogs"] += inv.get("cogs", 0)
            s["labor"] += bt.get("labor", 0)
            s["parts"] += bt.get("part", 0) + bt.get("consumable", 0)
        if k == month:
            inv_month["count"] += 1
            inv_month["gross"] += inv["totals"]["gross"]
            parts_rev += bt.get("part", 0) + bt.get("consumable", 0)
            parts_cost += inv.get("cogs", 0)
    for p in payments:
        k = p["date"][:7]
        if k in series:
            series[k]["collected"] += p["amount"]
    for s in series.values():
        s["profit"] = s["revenue"] - s["cogs"]
        for f in ("revenue", "cogs", "profit", "collected", "labor", "parts"):
            s[f] = round(s[f], 2)
    cur = series[month]
    durations = []
    cutoff = (now() - timedelta(days=90)).isoformat()
    for w in wos:
        if w.get("finished_at") and w["finished_at"] >= cutoff:
            durations.append((datetime.fromisoformat(w["finished_at"]) - datetime.fromisoformat(w["created_at"])).total_seconds() / 3600)
    stats = await mechanic_stats(month)
    mechs = {str(m["_id"]): m["name"] for m in await db.mechanics.find().to_list(500)}
    mech_rows = [{"name": mechs.get(mid, "?"), **st} for mid, st in stats.items() if mid in mechs]
    prods = [p for p in mechs] and [p["productivity"] for p in mech_rows if p["attendance"]]
    settings = await db.settings.find_one({"_id": "company"}) or {}
    elevs = settings.get("elevators", [])
    busy = {w.get("elevator") for w in wos if w["status"] in ("diagnosticare", "aprobata", "in_lucru", "asteapta_piese") and w.get("elevator")}
    low_stock = await db.products.count_documents({"$expr": {"$lte": ["$stock_qty", "$min_stock"]}})
    return {
        "in_service": sum(v for k, v in by_status.items() if k not in ("facturata", "inchisa")),
        "waiting": sum(by_status.get(k, 0) for k in ("noua", "asteapta_oferta", "asteapta_piese")),
        "in_progress": sum(by_status.get(k, 0) for k in ("diagnosticare", "aprobata", "in_lucru")),
        "finished": by_status.get("finalizata", 0),
        "invoices_month": {"count": inv_month["count"], "gross": round(inv_month["gross"], 2)},
        "collected_month": cur["collected"],
        "revenue_month": cur["revenue"],
        "profit_month": cur["profit"],
        "parts_margin": round((parts_rev - parts_cost) / parts_rev * 100, 1) if parts_rev else 0,
        "mechanic_productivity": round(sum(prods) / len(prods), 1) if prods else 0,
        "elevator_occupancy": {"busy": len(busy & set(elevs)), "total": len(elevs)},
        "avg_repair_hours": round(sum(durations) / len(durations), 1) if durations else 0,
        "low_stock": low_stock,
        "receivables": round(sum(i["totals"]["gross"] - i.get("paid_amount", 0) for i in invoices), 2),
        "by_status": by_status,
        "series": list(series.values()),
        "mechanics": sorted(mech_rows, key=lambda r: -r["productivity"]),
    }
