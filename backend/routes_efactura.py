import asyncio
import base64
import hmac
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from core import db, raw_db, ser, iso, require, audit, get_or_404, get_settings
from tenant_context import set_scope
from efactura import build_ubl
import anaf_service as ef
import efactura_inbox as inbox
from efactura_pdf import render_pdf

router = APIRouter(prefix="/api")


class CfgIn(BaseModel):
    environment: str
    client_id: str = ""
    client_secret: Optional[str] = None
    redirect_uri: str = ""
    auto_send: bool = False


@router.get("/efactura/config")
async def get_config(user=Depends(require("settings"))):
    return ef.public_cfg(await ef.get_cfg(), await get_settings())


@router.put("/efactura/config")
async def put_config(body: CfgIn, user=Depends(require("settings"))):
    if body.environment not in ("simulare", "test", "prod"):
        raise HTTPException(400, "Mediu invalid")
    cfg = await ef.get_cfg()
    upd = {"environment": body.environment, "client_id": body.client_id.strip(), "redirect_uri": body.redirect_uri.strip() or cfg["redirect_uri"],
           "auto_send": body.auto_send}
    if body.client_secret:
        upd["client_secret"] = ef.enc(body.client_secret.strip())
    if body.environment != cfg["environment"]:
        await ef.log("config", True, f"Mediu schimbat: {cfg['environment']} → {body.environment}", env=body.environment)
    await ef.save_cfg(upd)
    await audit(user, "update", "efactura_config", "main", body.environment)
    return ef.public_cfg(await ef.get_cfg(), await get_settings())


@router.post("/efactura/oauth/start")
async def oauth_start(user=Depends(require("settings"))):
    cfg = await ef.get_cfg()
    if not cfg.get("client_id") or not cfg.get("client_secret"):
        raise HTTPException(400, "Completați și salvați Client ID și Client Secret")
    state = ef.new_state()
    await ef.save_cfg({"oauth_state": state, "oauth_state_at": iso()})
    return {"url": ef.authorize_url(cfg, state)}


@router.get("/efactura/oauth/callback")
async def oauth_callback(code: str = "", state: str = "", error: str = ""):
    front = os.environ["FRONTEND_URL"].split(",")[0].strip()
    if not state:
        return RedirectResponse(f"{front}/efactura?oauth=error")
    state_doc = await raw_db.efactura_config.find_one({"kind": "efactura", "oauth_state": state})
    if not state_doc:
        return RedirectResponse(f"{front}/efactura?oauth=error")
    set_scope({"tenant_id": state_doc["tenant_id"], "branch_id": state_doc["branch_id"]})
    cfg = await ef.get_cfg()
    if error or not code or not ef.state_valid(cfg, state):
        await ef.log("oauth", False, error or "state invalid / cod lipsă", env=cfg["environment"])
        return RedirectResponse(f"{front}/efactura?oauth=error")
    await ef.save_cfg({"oauth_state": ""})
    try:
        await ef.exchange_code(code)
    except Exception as e:  # noqa: BLE001
        message = e.detail if isinstance(e, HTTPException) else str(e)
        await ef.save_cfg({"last_error": message[:1500]})
        await ef.log("oauth", False, message[:1500], env=cfg["environment"])
        return RedirectResponse(f"{front}/efactura?oauth=error")
    return RedirectResponse(f"{front}/efactura?oauth=ok")


@router.post("/efactura/oauth/refresh")
async def oauth_refresh(user=Depends(require("settings"))):
    await ef.refresh_tokens()
    return ef.public_cfg(await ef.get_cfg(), await get_settings())


@router.post("/efactura/oauth/disconnect")
async def oauth_disconnect(user=Depends(require("settings"))):
    await db.efactura_config.update_one({"kind": "efactura"}, {"$unset": {"access_token": "", "refresh_token": "", "token_expires_at": "",
                                                                     "refresh_expires_at": "", "connected_at": ""}})
    await ef.log("oauth", True, "Deconectat SPV")
    return ef.public_cfg(await ef.get_cfg(), await get_settings())


@router.get("/efactura/logs")
async def logs(user=Depends(require("settings"))):
    return [ser(x) for x in await db.efactura_logs.find().sort("at", -1).to_list(200)]


async def _fiscal(iid: str):
    inv = await get_or_404("invoices", iid)
    if inv["type"] != "fiscal":
        raise HTTPException(400, "e-Factura se aplică doar facturilor fiscale")
    return inv


async def _out(iid: str):
    inv = ser(await get_or_404("invoices", iid))
    inv.get("efactura", {}).pop("xml", None)
    inv["payments"] = [ser(p) for p in await db.payments.find({"invoice_id": iid}).sort("date", 1).to_list(200)]
    inv["efactura"]["has_receipt"] = bool(await db.efactura_files.find_one({"invoice_id": iid}, {"_id": 1}))
    return inv


@router.post("/invoices/{iid}/efactura/validate")
async def validate(iid: str, anaf: bool = False, user=Depends(require("invoices"))):
    inv = await _fiscal(iid)
    xml = build_ubl(inv)
    res = {"errors": ef.validate_ubl(inv, xml)}
    if anaf and not res["errors"]:
        res["anaf"] = await ef.anaf_public_validate(xml)
    return res


@router.post("/invoices/{iid}/efactura/submit")
async def submit(iid: str, user=Depends(require("invoices"))):
    inv = await _fiscal(iid)
    if inv["efactura"].get("status") in ("pending", "ok"):
        raise HTTPException(400, "Factura a fost deja transmisă")
    await ef.send_invoice(inv)
    await audit(user, "efactura_submit", "invoice", iid)
    return await _out(iid)


@router.post("/invoices/{iid}/efactura/refresh")
async def refresh_status(iid: str, user=Depends(require("invoices"))):
    inv = await _fiscal(iid)
    if inv["efactura"].get("status") != "pending":
        raise HTTPException(400, "Factura nu este în prelucrare")
    await ef.check_status(inv)
    return await _out(iid)


@router.get("/invoices/{iid}/efactura/receipt")
async def receipt(iid: str, user=Depends(require("invoices"))):
    f = await db.efactura_files.find_one({"invoice_id": iid})
    if not f:
        raise HTTPException(404, "Recipisa nu este disponibilă")
    return Response(base64.b64decode(f["content"]), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="recipisa_{f["name"]}"'})


@router.get("/efactura/inbox")
async def inbox_list(user=Depends(require("stock"))):
    return [ser(m) for m in await db.efactura_inbox.find({}, {"xml": 0, "signature_xml": 0}).sort("received_at", -1).to_list(500)]


class UploadIn(BaseModel):
    filename: str = ""
    content: str


@router.post("/efactura/inbox/upload")
async def inbox_upload(body: UploadIn, user=Depends(require("stock"))):
    await inbox.store_message({"filename": body.filename, "data_creare": iso()}, body.content, source="import")
    return {"ok": True}


@router.post("/efactura/inbox/sync")
async def inbox_sync(user=Depends(require("stock"))):
    return await inbox.sync_inbox()


@router.get("/efactura/inbox/{mid}")
async def inbox_get(mid: str, user=Depends(require("stock"))):
    return await inbox.inbox_detail(mid)


@router.get("/efactura/inbox/{mid}/pdf")
async def inbox_pdf(mid: str, user=Depends(require("stock"))):
    m = await get_or_404("efactura_inbox", mid)
    settings = await get_settings()
    custom_logo = settings.get("custom_logo_data_url", "") if settings.get("subscription_plan") != "BASIC" else ""
    pdf = render_pdf(
        m["xml"],
        m,
        include_footer=settings.get("subscription_plan") == "BASIC",
        custom_logo_data_url=custom_logo,
    )
    name = "".join(c for c in m["parsed"]["series_number"] if c.isalnum() or c in "-_") or "factura"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="efactura_{name}.pdf"'})


@router.post("/efactura/inbox/{mid}/create-nir")
async def inbox_create_nir(mid: str, body: inbox.MapIn, user=Depends(require("stock"))):
    return await inbox.create_nir_from_message(mid, body, user)


@router.post("/efactura/inbox/{mid}/link/{nir_id}")
async def inbox_link(mid: str, nir_id: str, body: inbox.MapIn, user=Depends(require("stock"))):
    res = await inbox.link_overwrite(mid, nir_id, body, user)
    await audit(user, "efactura_overwrite", "nir", nir_id, "; ".join(res["changes"])[:300])
    return res


async def _run_job(job: str):
    try:
        if job == "tokens":
            await ef.refresh_if_needed()
        elif job == "status":
            await ef.poll_pending()
        elif job == "inbox":
            cfg = await ef.get_cfg()
            if cfg["environment"] in ef.BASES and cfg.get("access_token"):
                await inbox.sync_inbox()
    except HTTPException as e:
        await ef.log(f"cron-{job}", False, str(e.detail))


async def _run_job_all_tenants(job: str):
    branches = await raw_db.branches.find({"status": "ACTIVE"}).to_list(5000)
    for branch in branches:
        try:
            set_scope({"tenant_id": branch["tenant_id"], "branch_id": branch["_id"], "system_scope": True})
            await _run_job(job)
        except Exception as error:  # noqa: BLE001
            await raw_db.cron_errors.insert_one({"job": f"efactura-{job}", "tenant_id": branch["tenant_id"], "branch_id": branch["_id"], "error": str(error)[:1500], "at": iso()})


@router.post("/cron/efactura/{job}")
async def cron(job: str, request: Request, background: BackgroundTasks):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], os.environ["WEBHOOK_CRON_SECRET"]):
        raise HTTPException(401, "Unauthorized")
    if job not in ("tokens", "status", "inbox"):
        raise HTTPException(400, "Job invalid")
    run_id = request.headers.get("X-Webhook-Id", "")
    if run_id and await db.cron_runs.find_one({"_id": run_id}):
        return {"ok": True, "duplicate": True}
    if run_id:
        await db.cron_runs.insert_one({"_id": run_id, "job": job, "at": iso()})
    background.add_task(_run_job_all_tenants, job)
    return {"ok": True}


_tasks = set()


def schedule_auto_send(inv: dict):
    async def go():
        try:
            if (await ef.get_cfg()).get("auto_send"):
                await ef.send_invoice(inv)
        except Exception as e:  # noqa: BLE001
            await ef.log("auto-send", False, str(e), str(inv["_id"]))
    task = asyncio.create_task(go())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
