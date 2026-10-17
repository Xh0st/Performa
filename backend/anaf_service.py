import base64
import io
import os
import random
import re
import secrets
import zipfile
import xml.etree.ElementTree as ET
from datetime import timedelta, datetime
from urllib.parse import urlencode
import httpx
from cryptography.fernet import Fernet
from fastapi import HTTPException
from core import db, iso, now, get_settings
from efactura import build_ubl

OAUTH = "https://logincert.anaf.ro/anaf-oauth2/v1"
BASES = {"test": "https://api.anaf.ro/test/FCTEL/rest", "prod": "https://api.anaf.ro/prod/FCTEL/rest"}
VALIDATE_URL = "https://webservicesp.anaf.ro/prod/FCTEL/rest/validare/FACT1"
ENV_LABEL = {"simulare": "Simulare (fără ANAF)", "test": "Test (ANAF Sandbox)", "prod": "Producție"}
UNECE_UNITS = {"H87", "C62", "HUR", "KGM", "LTR", "MTR", "SET", "XPP", "KWH", "MTK", "DAY", "MON"}
VAT_RATES = {0, 5, 9, 11, 19, 21}
_fernet = Fernet(os.environ["EFACTURA_ENC_KEY"].encode())


def enc(v: str) -> str:
    return _fernet.encrypt(v.encode()).decode() if v else ""


def dec(v: str) -> str:
    return _fernet.decrypt(v.encode()).decode() if v else ""


def cif_digits(cui: str) -> str:
    return re.sub(r"\D", "", cui or "")


async def get_cfg() -> dict:
    doc = await db.efactura_config.find_one({"_id": "main"})
    cfg = {k: v for k, v in (doc or {}).items() if k != "_id"}
    cfg.setdefault("environment", "simulare")
    cfg.setdefault("redirect_uri", f"{os.environ['FRONTEND_URL'].split(',')[0].strip()}/api/efactura/oauth/callback")
    return cfg


async def save_cfg(upd: dict):
    await db.efactura_config.update_one({"_id": "main"}, {"$set": upd}, upsert=True)


def public_cfg(cfg: dict, company: dict) -> dict:
    env = cfg["environment"]
    connected = env == "simulare" or bool(cfg.get("access_token"))
    if env == "simulare":
        status = "Mod simulare activ – nicio comunicare cu ANAF"
    elif connected:
        status = f"Conectat cu succes la SPV - {ENV_LABEL[env]}"
    else:
        status = f"Neconectat - {ENV_LABEL[env]} (necesită autorizare OAuth)"
    return {"environment": env, "client_id": cfg.get("client_id", ""), "has_secret": bool(cfg.get("client_secret")),
            "redirect_uri": cfg["redirect_uri"], "auto_send": cfg.get("auto_send", False), "connected": connected,
            "status_text": status, "token_expires_at": cfg.get("token_expires_at"), "refresh_expires_at": cfg.get("refresh_expires_at"),
            "connected_at": cfg.get("connected_at"), "last_refresh_at": cfg.get("last_refresh_at"), "last_error": cfg.get("last_error", ""),
            "api_base": BASES.get(env, "—"), "cif": cif_digits(company.get("cui", "")),
            "company": {k: company.get(k, "") for k in ("name", "cui", "reg_com", "address", "city", "county_code", "iban")}}


async def log(op: str, ok: bool, message: str, invoice_id: str = "", env: str = ""):
    await db.efactura_logs.insert_one({"op": op, "ok": ok, "message": message[:1500], "invoice_id": invoice_id, "env": env, "at": iso()})


def authorize_url(cfg: dict, state: str) -> str:
    q = urlencode({"response_type": "code", "client_id": cfg["client_id"], "redirect_uri": cfg["redirect_uri"],
                   "token_content_type": "jwt", "state": state})
    return f"{OAUTH}/authorize?{q}"


async def _token_call(cfg: dict, data: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{OAUTH}/token", auth=(cfg["client_id"], dec(cfg["client_secret"])), data=data)
    if r.status_code >= 400:
        raise HTTPException(502, f"ANAF OAuth {r.status_code}: {r.text[:300]}")
    return r.json()


async def _store_tokens(tokens: dict, first: bool):
    exp = now() + timedelta(seconds=int(tokens.get("expires_in", 7776000)))
    upd = {"access_token": enc(tokens["access_token"]), "token_expires_at": exp.isoformat(), "last_refresh_at": iso(), "last_error": ""}
    if tokens.get("refresh_token"):
        upd["refresh_token"] = enc(tokens["refresh_token"])
        upd["refresh_expires_at"] = (now() + timedelta(days=365)).isoformat()
    if first:
        upd["connected_at"] = iso()
    await save_cfg(upd)


async def exchange_code(code: str):
    cfg = await get_cfg()
    tokens = await _token_call(cfg, {"grant_type": "authorization_code", "code": code, "redirect_uri": cfg["redirect_uri"],
                                     "token_content_type": "jwt"})
    await _store_tokens(tokens, True)
    await log("oauth", True, "Autorizare SPV reușită", env=cfg["environment"])


async def refresh_tokens():
    cfg = await get_cfg()
    if not cfg.get("refresh_token"):
        raise HTTPException(400, "Nu există refresh token – autorizați SPV")
    try:
        tokens = await _token_call(cfg, {"grant_type": "refresh_token", "refresh_token": dec(cfg["refresh_token"])})
    except HTTPException as e:
        await save_cfg({"last_error": e.detail})
        await log("refresh", False, e.detail, env=cfg["environment"])
        raise
    await _store_tokens(tokens, False)
    await log("refresh", True, "Token reîmprospătat", env=cfg["environment"])


async def anaf_request(method: str, path: str, params: dict, content: bytes = None) -> httpx.Response:
    cfg = await get_cfg()
    env = cfg["environment"]
    if env not in BASES:
        raise HTTPException(400, "Mediul de simulare nu comunică cu ANAF")
    if not cfg.get("access_token"):
        raise HTTPException(400, "SPV neautorizat – conectați-vă din Administrare › e-Factura")
    if cfg.get("token_expires_at", "") < (now() + timedelta(days=7)).isoformat():
        await refresh_tokens()
        cfg = await get_cfg()
    for attempt in range(2):
        headers = {"Authorization": f"Bearer {dec(cfg['access_token'])}"}
        if content is not None:
            headers["Content-Type"] = "text/plain"
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.request(method, BASES[env] + path, params=params, content=content, headers=headers)
        if r.status_code == 401 and attempt == 0:
            await refresh_tokens()
            cfg = await get_cfg()
            continue
        if r.status_code >= 400:
            raise HTTPException(502, f"ANAF {r.status_code}: {r.text[:500]}")
        return r


def _errors_from_xml(text: str):
    try:
        root = ET.fromstring(text.encode() if isinstance(text, str) else text)
    except ET.ParseError:
        return [text[:500]]
    return [el.attrib.get("errorMessage", "") for el in root.iter() if el.tag.endswith("Errors") and el.attrib.get("errorMessage")]


def validate_ubl(inv: dict, xml: str):
    errs = []
    s, b = inv["seller"], inv["buyer"]
    if not re.fullmatch(r"(RO)?\d{2,10}", (s.get("cui") or "").upper().replace(" ", "")):
        errs.append("CIF emitent invalid (Setări companie)")
    for k, lbl in (("name", "Denumire emitent"), ("address", "Adresă emitent"), ("city", "Localitate emitent")):
        if not s.get(k) or "[" in s.get(k, ""):
            errs.append(f"{lbl} lipsă sau placeholder")
    if not re.fullmatch(r"RO-[A-Z]{1,2}", s.get("county_code") or ""):
        errs.append("Cod județ emitent invalid (format ISO 3166-2, ex. RO-B)")
    iban = (s.get("iban") or "").replace(" ", "").upper()
    if iban and not re.fullmatch(r"RO\d{2}[A-Z]{4}[A-Z0-9]{16}", iban):
        errs.append("IBAN emitent invalid sau placeholder (format RO + 22 caractere)")
    if b.get("cui"):
        if not re.fullmatch(r"(RO)?\d{2,10}", b["cui"].upper().replace(" ", "")):
            errs.append("CIF destinatar invalid")
    elif b.get("cnp") and not re.fullmatch(r"\d{13}", b["cnp"]):
        errs.append("CNP destinatar invalid")
    if not b.get("name"):
        errs.append("Denumire destinatar lipsă")
    if not inv["lines"]:
        errs.append("Factura nu are linii")
    for i, ln in enumerate(inv["lines"], 1):
        unit = "HUR" if ln["type"] == "labor" else "H87"
        if unit not in UNECE_UNITS:
            errs.append(f"Linia {i}: unitate de măsură în afara Codelist UN/ECE")
        if int(ln.get("vat_rate", 21)) not in VAT_RATES:
            errs.append(f"Linia {i}: cotă TVA invalidă ({ln.get('vat_rate')})")
        if ln["qty"] <= 0:
            errs.append(f"Linia {i}: cantitate invalidă")
    t = inv["totals"]
    if abs(sum(ln["net"] for ln in inv["lines"]) - t["net"]) > 0.01:
        errs.append("Total fără TVA nu corespunde sumei liniilor")
    if abs(sum(ln["vat"] for ln in inv["lines"]) - t["vat"]) > 0.05:
        errs.append("Total TVA nu corespunde sumei liniilor")
    try:
        ET.fromstring(xml.encode())
    except ET.ParseError as e:
        errs.append(f"XML invalid: {e}")
    return errs


async def anaf_public_validate(xml: str):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(VALIDATE_URL, content=xml.encode(), headers={"Content-Type": "text/plain"})
    try:
        data = r.json()
        msgs = [m.get("message", str(m)) for m in data.get("Messages", [])]
        return {"ok": data.get("stare") == "ok", "messages": msgs, "raw": data.get("stare", "")}
    except ValueError:
        return {"ok": False, "messages": [r.text[:500]], "raw": r.status_code}


async def _set_ef(inv_id, upd: dict, event: str):
    await db.invoices.update_one({"_id": inv_id}, {"$set": {f"efactura.{k}": v for k, v in upd.items()},
                                                   "$push": {"efactura.history": {"event": event, "at": iso()}}})


async def send_invoice(inv: dict):
    cfg = await get_cfg()
    env = cfg["environment"]
    xml = build_ubl(inv)
    errs = validate_ubl(inv, xml)
    if errs:
        await _set_ef(inv["_id"], {"status": "invalid", "errors": errs, "upload_index": None, "env": env}, "Validare internă eșuată")
        await log("upload", False, "; ".join(errs), str(inv["_id"]), env)
        return
    if env == "simulare":
        idx = str(random.randint(4000000000, 4999999999))
        await _set_ef(inv["_id"], {"status": "pending", "upload_index": idx, "xml": xml, "errors": [], "env": env, "sent_at": iso()},
                      f"Transmis (SIMULARE) – index {idx}")
        return
    settings = await get_settings()
    try:
        r = await anaf_request("POST", "/upload", {"standard": "UBL", "cif": cif_digits(settings.get("cui"))}, xml.encode())
        root = ET.fromstring(r.content)
        idx = root.attrib.get("index_incarcare")
        if root.attrib.get("ExecutionStatus") == "0" and idx:
            await _set_ef(inv["_id"], {"status": "pending", "upload_index": idx, "xml": xml, "errors": [], "env": env, "sent_at": iso()},
                          f"Încărcat în SPV ({ENV_LABEL[env]}) – index {idx}")
            await log("upload", True, f"index {idx}", str(inv["_id"]), env)
        else:
            errs = _errors_from_xml(r.text) or [r.text[:500]]
            await _set_ef(inv["_id"], {"status": "error", "errors": errs, "env": env, "upload_index": None}, "Respins la încărcare")
            await log("upload", False, "; ".join(errs), str(inv["_id"]), env)
    except (HTTPException, ET.ParseError, httpx.HTTPError) as e:
        msg = getattr(e, "detail", str(e))
        await _set_ef(inv["_id"], {"status": "error", "errors": [msg], "env": env, "upload_index": None}, "Eroare comunicare ANAF")
        await log("upload", False, msg, str(inv["_id"]), env)


async def download_zip(download_id: str) -> bytes:
    r = await anaf_request("GET", "/descarcare", {"id": download_id})
    if not zipfile.is_zipfile(io.BytesIO(r.content)):
        raise HTTPException(502, "ANAF nu a returnat o arhivă ZIP")
    return r.content


async def check_status(inv: dict):
    ef = inv.get("efactura", {})
    env = ef.get("env") or (await get_cfg())["environment"]
    if ef.get("status") != "pending":
        return
    if env == "simulare":
        did = str(random.randint(3000000000, 3999999999))
        await _set_ef(inv["_id"], {"status": "ok", "download_id": did, "checked_at": iso()}, f"Validată (SIMULARE) – recipisă {did}")
        return
    try:
        r = await anaf_request("GET", "/stareMesaj", {"id_incarcare": ef["upload_index"]})
        root = ET.fromstring(r.content)
        stare = root.attrib.get("stare", "")
        did = root.attrib.get("id_descarcare")
        if stare == "in prelucrare":
            await db.invoices.update_one({"_id": inv["_id"]}, {"$set": {"efactura.checked_at": iso()}})
            return
        if stare in ("ok", "nok") and did:
            content = await download_zip(did)
            await db.efactura_files.update_one({"invoice_id": str(inv["_id"])}, {"$set": {
                "invoice_id": str(inv["_id"]), "name": f"{did}.zip", "content": base64.b64encode(content).decode(), "at": iso()}}, upsert=True)
            errs = []
            if stare == "nok":
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for n in z.namelist():
                        if not n.lower().startswith("semnatura"):
                            errs += _errors_from_xml(z.read(n).decode("utf-8", "ignore"))
            await _set_ef(inv["_id"], {"status": "ok" if stare == "ok" else "nok", "download_id": did, "errors": errs, "checked_at": iso()},
                          "Validată ANAF – recipisă descărcată" if stare == "ok" else "Respinsă ANAF (nok)")
            await log("status", stare == "ok", stare + (": " + "; ".join(errs) if errs else ""), str(inv["_id"]), env)
        else:
            errs = _errors_from_xml(r.text) or [stare or r.text[:300]]
            await _set_ef(inv["_id"], {"status": "error", "errors": errs, "checked_at": iso()}, "Eroare structură / stare")
            await log("status", False, "; ".join(errs), str(inv["_id"]), env)
    except (HTTPException, ET.ParseError, httpx.HTTPError) as e:
        await log("status", False, getattr(e, "detail", str(e)), str(inv["_id"]), env)


async def poll_pending():
    async for inv in db.invoices.find({"efactura.status": "pending"}):
        await check_status(inv)


async def refresh_if_needed():
    cfg = await get_cfg()
    if cfg["environment"] in BASES and cfg.get("refresh_token") and cfg.get("token_expires_at", "") < (now() + timedelta(days=15)).isoformat():
        await refresh_tokens()


def new_state() -> str:
    return secrets.token_urlsafe(24)


def state_valid(cfg: dict, state: str) -> bool:
    return bool(state) and secrets.compare_digest(cfg.get("oauth_state", ""), state) and \
        cfg.get("oauth_state_at", "") > (now() - timedelta(minutes=15)).isoformat()


_ = datetime
