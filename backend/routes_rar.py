from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import audit, db, get_settings, iso, require, ser
from rar_autopass import ENV_LABELS, get_config, public_config, save_config


router = APIRouter(prefix="/api")


class RarAutoPassConfigIn(BaseModel):
    branch_name: str = "Punct de lucru principal"
    authorization_code: str = Field(min_length=1, max_length=80)
    service_cui: str = Field(min_length=1, max_length=30)
    environment: str
    api_token: Optional[str] = Field(default=None, max_length=4000)


@router.get("/rar-autopass/config")
async def read_rar_config(user=Depends(require("settings"))):
    return public_config(await get_config(), await get_settings())


@router.put("/rar-autopass/config")
async def write_rar_config(body: RarAutoPassConfigIn, user=Depends(require("settings"))):
    if body.environment not in ENV_LABELS:
        raise HTTPException(400, "Mediu RAR AutoPass invalid")
    cfg = await save_config(body.model_dump())
    await audit(
        user,
        "update",
        "rar_autopass_config",
        "primary",
        f"{cfg['branch_name']} · {cfg['environment']}",
    )
    return public_config(cfg, await get_settings())


@router.post("/rar-autopass/test-connection")
async def test_rar_connection(user=Depends(require("settings"))):
    cfg = await get_config()
    missing = []
    if not cfg.get("authorization_code"):
        missing.append("cod autorizație RAR")
    if not cfg.get("service_cui"):
        missing.append("CUI service")
    if not cfg.get("api_token"):
        missing.append("token de acces")
    missing.append("contract API oficial cu endpoint de test")
    await db.rar_autopass_logs.insert_one(
        {
            "operation": "connection_test",
            "ok": False,
            "message": "Lipsesc: " + ", ".join(missing),
            "environment": cfg.get("environment", "test"),
            "at": iso(),
        }
    )
    await audit(user, "test", "rar_autopass", "primary", "test blocat: contract API lipsă")
    raise HTTPException(
        409,
        "Testul necesită contractul API oficial RAR, endpointul de test și tokenul de acces",
    )


@router.get("/rar-autopass/outbox")
async def list_rar_outbox(user=Depends(require("settings"))):
    projection = {"payload": 0, "idempotency_key": 0}
    return [
        ser(item)
        for item in await db.rar_autopass_outbox.find({}, projection).sort("updated_at", -1).to_list(200)
    ]


@router.get("/rar-autopass/logs")
async def list_rar_logs(user=Depends(require("settings"))):
    return [
        ser(item)
        for item in await db.rar_autopass_logs.find({}).sort("at", -1).to_list(100)
    ]