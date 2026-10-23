from datetime import date

from core import db
from pagination import normalize_pagination, page_response


def invoice_balance(invoice: dict) -> float:
    gross = abs(float(invoice.get("totals", {}).get("gross", 0)))
    paid = float(invoice.get("paid_amount", 0))
    credited = float(invoice.get("credited_amount", 0))
    return round(max(0, gross - paid - credited), 2)


async def client_credit_position(client_id: str) -> dict:
    invoices = await db.invoices.find(
        {
            "client_id": client_id,
            "type": "fiscal",
            "kind": {"$ne": "credit_note"},
        },
        {"totals": 1, "paid_amount": 1, "credited_amount": 1},
    ).to_list(5000)
    invoiced_total = round(
        sum(abs(item.get("totals", {}).get("gross", 0)) for item in invoices),
        2,
    )
    outstanding = round(sum(invoice_balance(item) for item in invoices), 2)
    return {"invoiced_total": invoiced_total, "outstanding": outstanding}


def _movement_date(value: str) -> str:
    return (value or "")[:10]


def _invoice_movement(invoice: dict) -> dict:
    reference = f"{invoice.get('series', '')}{invoice.get('number', '')}"
    is_credit_note = invoice.get("kind") == "credit_note"
    amount = abs(float(invoice.get("totals", {}).get("gross", 0)))
    return {
        "date": _movement_date(invoice.get("issue_date", "")),
        "at": invoice.get("created_at", ""),
        "kind": "credit_note" if is_credit_note else "invoice",
        "reference": reference,
        "description": (
            invoice.get("storno_reason", "Factură fiscală")
            if is_credit_note
            else "Factură fiscală"
        ),
        "debit": 0 if is_credit_note else amount,
        "credit": amount if is_credit_note else 0,
        "entity_id": str(invoice["_id"]),
    }


def _payment_movement(payment: dict) -> dict:
    return {
        "date": _movement_date(payment.get("date", "")),
        "at": payment.get("date", ""),
        "kind": "payment",
        "reference": payment.get("doc_number", "Încasare"),
        "description": f"Încasare {payment.get('invoice_ref', '')}".strip(),
        "debit": 0,
        "credit": abs(float(payment.get("amount", 0))),
        "entity_id": str(payment["_id"]),
    }


def _validate_day(value: str, label: str) -> str:
    if not value:
        return ""
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} trebuie să fie în format YYYY-MM-DD") from exc
    return value


async def account_statement(
    client_id: str,
    date_from: str,
    date_to: str,
    page: int,
    page_size: int,
) -> dict:
    start = _validate_day(date_from, "Data de început")
    end = _validate_day(date_to, "Data de sfârșit")
    if start and end and start > end:
        raise ValueError("Intervalul selectat este invalid")

    invoices = await db.invoices.find(
        {"client_id": client_id, "type": "fiscal"},
        {
            "series": 1,
            "number": 1,
            "issue_date": 1,
            "created_at": 1,
            "kind": 1,
            "totals": 1,
            "storno_reason": 1,
        },
    ).to_list(5000)
    invoice_ids = [str(item["_id"]) for item in invoices]
    payments = await db.payments.find(
        {"$or": [{"client_id": client_id}, {"invoice_id": {"$in": invoice_ids}}]},
        {"doc_number": 1, "invoice_ref": 1, "amount": 1, "date": 1},
    ).to_list(5000)
    movements = [_invoice_movement(item) for item in invoices]
    movements.extend(_payment_movement(item) for item in payments)
    movements.sort(
        key=lambda item: (item["date"], item["at"], item["kind"], item["reference"])
    )

    opening = 0.0
    filtered = []
    for movement in movements:
        amount = movement["debit"] - movement["credit"]
        if start and movement["date"] < start:
            opening = round(opening + amount, 2)
            continue
        if end and movement["date"] > end:
            continue
        filtered.append(movement)

    running_balance = opening
    for movement in filtered:
        running_balance = round(
            running_balance + movement["debit"] - movement["credit"],
            2,
        )
        movement["balance"] = running_balance

    current_page, size = normalize_pagination(page, page_size)
    offset = (current_page - 1) * size
    debit = round(sum(item["debit"] for item in filtered), 2)
    credit = round(sum(item["credit"] for item in filtered), 2)
    return page_response(
        filtered[offset:offset + size],
        len(filtered),
        current_page,
        size,
        summary={
            "opening": opening,
            "debit": debit,
            "credit": credit,
            "closing": round(opening + debit - credit, 2),
        },
        period={"date_from": start, "date_to": end},
        all_items=filtered,
    )