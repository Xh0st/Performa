from datetime import date

from dateutil.relativedelta import relativedelta

from core import db, iso, next_seq


async def create_certificate(invoice: dict, work_order: dict, settings: dict) -> dict | None:
    if invoice.get("type") != "fiscal" or invoice.get("kind") == "credit_note":
        return None
    if await db.warranty_certificates.find_one({"invoice_id": str(invoice["_id"])}):
        return None
    issue_date = date.fromisoformat(invoice["issue_date"])
    product_ids = {line.get("product_id") for line in invoice.get("lines", []) if line.get("product_id")}
    products = {
        str(item["_id"]): item
        for item in await db.products.find({"_id": {"$in": [
            __import__("bson").ObjectId(product_id) for product_id in product_ids
        ]}}).to_list(1000)
    }
    lines = []
    for line in invoice.get("lines", []):
        if line.get("type") not in ("part", "consumable", "labor"):
            continue
        months = 3 if line["type"] == "labor" else products.get(line.get("product_id"), {}).get("warranty_months", 24)
        valid_to = issue_date + relativedelta(months=max(1, int(months)))
        lines.append({
            "source_line_id": line["id"],
            "label": "Manoperă" if line["type"] == "labor" else "Piesă",
            "description": line["description"],
            "product_id": line.get("product_id", ""),
            "qty": line.get("qty", 0),
            "warranty_months": max(1, int(months)),
            "valid_from": issue_date.isoformat(),
            "valid_to": valid_to.isoformat(),
        })
    if not lines:
        return None
    sequence = await next_seq("warranty_certificate")
    certificate = {
        "number": f"GAR-{issue_date.year}-{sequence:06d}",
        "invoice_id": str(invoice["_id"]),
        "invoice_ref": f"{invoice['series']}{invoice['number']}",
        "work_order_id": str(work_order["_id"]),
        "work_order_number": work_order["number"],
        "client_id": invoice["client_id"],
        "client_name": invoice["buyer"]["name"],
        "vehicle_label": invoice["vehicle"],
        "vehicle_id": work_order["vehicle_id"],
        "seller_name": settings.get("name", ""),
        "issued_date": issue_date.isoformat(),
        "lines": lines,
        "created_at": iso(),
    }
    result = await db.warranty_certificates.insert_one(certificate)
    certificate["_id"] = result.inserted_id
    return certificate