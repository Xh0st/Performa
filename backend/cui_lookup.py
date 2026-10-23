import asyncio
import re
from datetime import date

import httpx
from fastapi import HTTPException


ANAF_URL = "https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva"
_lock = asyncio.Lock()
_last_request = 0.0


def normalize_cui(raw: str) -> tuple[str, bool]:
    value = re.sub(r"[ .-]", "", raw.strip().upper())
    had_ro = value.startswith("RO")
    digits = value[2:] if had_ro else value
    if not digits.isdigit() or not 2 <= len(digits) <= 10:
        raise HTTPException(422, "CUI invalid. Folosiți cifre, opțional cu prefixul RO")
    return digits, had_ro


async def lookup_cui(raw: str) -> dict:
    global _last_request
    cui, had_ro = normalize_cui(raw)
    async with _lock:
        loop = asyncio.get_running_loop()
        delay = 1 - (loop.time() - _last_request)
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
                response = await client.post(ANAF_URL, json=[{"cui": int(cui), "data": date.today().isoformat()}])
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise HTTPException(502, "ANAF nu este disponibil temporar") from error
        _last_request = loop.time()
    item = next((entry for entry in payload.get("found", []) if str(entry.get("date_generale", {}).get("cui", "")).lstrip("0") == cui.lstrip("0")), None)
    if not item:
        return {"cui": cui, "input_had_ro": had_ro, "anaf_found": False, "vat_payer": False, "vat_number": None}
    general = item.get("date_generale", {})
    vat = item.get("inregistrare_scop_Tva", {})
    vat_payer = bool(vat.get("scpTVA"))
    return {
        "cui": cui,
        "input_had_ro": had_ro,
        "anaf_found": True,
        "vat_payer": vat_payer,
        "vat_number": f"RO{cui}" if vat_payer else None,
        "name": general.get("denumire", ""),
        "address": general.get("adresa", ""),
        "reg_com": general.get("nrRegCom", ""),
        "caen": general.get("cod_CAEN", ""),
        "legal_form": general.get("forma_juridica", ""),
        "status": general.get("stare_inregistrare", ""),
        "source": "ANAF",
    }