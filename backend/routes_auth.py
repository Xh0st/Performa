import os
import re
import base64
from datetime import timedelta
from typing import Optional
import jwt
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError
from core import (db, raw_db, ser, oid, iso, now, hash_password, verify_password, make_token, get_current_user, require,
                  permissions_for, audit, get_settings, plan_limits, ROLES, JWT_ALG, tenant_plan)

router = APIRouter(prefix="/api")


async def ensure_active_context(user: dict) -> None:
    if not user.get("active", True):
        raise HTTPException(401, "Utilizator inactiv")
    tenant = await raw_db.tenants.find_one({"_id": user.get("tenant_id")})
    branch = await raw_db.branches.find_one({"_id": user.get("active_branch_id"), "tenant_id": user.get("tenant_id")})
    if not tenant or tenant.get("status") != "ACTIVE":
        raise HTTPException(403, "Tenant suspendat sau expirat")
    if not branch or branch.get("status") != "ACTIVE":
        raise HTTPException(403, "Punctul de lucru este inactiv")
ACCESS_MIN = 60 * 8


class LoginIn(BaseModel):
    email: str
    password: str


class InitialPasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


class TenantLogoIn(BaseModel):
    data_url: str


def set_cookies(response: Response, user: dict):
    user_id = str(user["_id"])
    tenant_id = user.get("tenant_id", "")
    branch_id = user.get("active_branch_id", "")
    session_version = user.get("session_version", 0)
    access = make_token(
        user_id,
        "access",
        ACCESS_MIN,
        tenant_id,
        branch_id,
        session_version,
    )
    refresh = make_token(
        user_id,
        "refresh",
        60 * 24 * 7,
        tenant_id,
        branch_id,
        session_version,
    )
    response.set_cookie("access_token", access, httponly=True, secure=True, samesite="none", max_age=ACCESS_MIN * 60, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=True, samesite="none", max_age=604800, path="/")


def user_out(u: dict):
    d = ser(u)
    d["permissions"] = permissions_for(d["role"])
    return d


async def user_context_out(user: dict) -> dict:
    output = user_out(user)
    output["platform_role"] = user.get("platform_role")
    output["tenant_id"] = user.get("tenant_id", "")
    output["active_branch_id"] = user.get("active_branch_id", "")
    if output["tenant_id"]:
        output["branches"] = [
            {"id": item["_id"], "name": item["branch_name"]}
            for item in await raw_db.branches.find({
                "tenant_id": output["tenant_id"],
                "status": "ACTIVE",
                "_id": {"$in": user.get("assigned_branch_ids", [])},
            }).to_list(100)
        ]
    return output


@router.post("/auth/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = body.email.strip().lower()
    ip = (request.headers.get("x-forwarded-for") or request.client.host).split(",")[0].strip()
    ident = f"{ip}:{email}"
    att = await db.login_attempts.find_one({"identifier": ident})
    if att and att.get("count", 0) >= 5:
        if att["locked_until"] > iso():
            raise HTTPException(429, "Prea multe încercări. Reîncercați peste 15 minute.")
        await db.login_attempts.delete_one({"identifier": ident})
    user = await db.users.find_one({"email": email})
    if not user or not user.get("active", True) or not verify_password(body.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": ident},
            {"$inc": {"count": 1}, "$set": {"locked_until": (now() + timedelta(minutes=15)).isoformat()}}, upsert=True)
        raise HTTPException(401, "Email sau parolă incorectă")
    await ensure_active_context(user)
    await db.login_attempts.delete_many({"identifier": ident})
    set_cookies(response, user)
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login": iso()}})
    return {"user": user_out(user)}


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("access_token") or request.cookies.get("refresh_token")
    if token:
        try:
            payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALG])
            if payload.get("type") in {"access", "refresh"}:
                await raw_db.users.update_one(
                    {"_id": oid(payload.get("sub", ""))},
                    {"$inc": {"session_version": 1}},
                )
        except (jwt.InvalidTokenError, HTTPException):
            pass
    response.delete_cookie("access_token", path="/", secure=True, samesite="none")
    response.delete_cookie("refresh_token", path="/", secure=True, samesite="none")
    return {"ok": True}


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@router.post("/auth/change-initial-password")
async def change_initial_password(
    body: InitialPasswordChangeIn,
    response: Response,
    user: dict = Depends(get_current_user),
):
    if not user.get("must_change_password"):
        raise HTTPException(400, "Parola inițială a fost deja schimbată")
    if len(body.new_password) < 8:
        raise HTTPException(400, "Parola nouă trebuie să aibă minim 8 caractere")
    current = await raw_db.users.find_one({"_id": oid(user["id"])})
    if not current or not verify_password(body.current_password, current["password_hash"]):
        raise HTTPException(401, "Parola curentă este incorectă")
    if verify_password(body.new_password, current["password_hash"]):
        raise HTTPException(400, "Alegeți o parolă nouă, diferită de parola inițială")
    await raw_db.users.update_one(
        {"_id": current["_id"]},
        {
            "$set": {
                "password_hash": hash_password(body.new_password),
                "must_change_password": False,
                "password_changed_at": iso(),
            }
        },
    )
    updated = await raw_db.users.find_one({"_id": current["_id"]})
    await audit(user, "change_initial_password", "user", user["id"])
    await raw_db.users.update_one({"_id": current["_id"]}, {"$inc": {"session_version": 1}})
    updated = await raw_db.users.find_one({"_id": current["_id"]})
    set_cookies(response, updated)
    return {"user": await user_context_out(updated)}


@router.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(401, "No refresh token")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALG])
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(401, "Invalid token type")
    user = await raw_db.users.find_one({"_id": oid(payload["sub"])})
    if not user:
        raise HTTPException(401, "User not found")
    await ensure_active_context(user)
    set_cookies(response, user)
    return {"ok": True}


class BranchSwitchIn(BaseModel):
    branch_id: str


@router.post("/auth/active-branch")
async def switch_active_branch(body: BranchSwitchIn, response: Response, user=Depends(get_current_user)):
    branch = await raw_db.branches.find_one({"_id": body.branch_id, "tenant_id": user["tenant_id"], "status": "ACTIVE"})
    if not branch or body.branch_id not in (await raw_db.users.find_one({"_id": oid(user["id"])}))["assigned_branch_ids"]:
        raise HTTPException(403, "Acces interzis la punctul de lucru")
    await raw_db.users.update_one(
        {"_id": oid(user["id"])},
        {"$set": {"active_branch_id": body.branch_id}, "$inc": {"session_version": 1}},
    )
    updated = await raw_db.users.find_one({"_id": oid(user["id"])})
    set_cookies(response, updated)
    return {"user": user_out(updated)}


class UserIn(BaseModel):
    email: str
    name: str
    role: str
    password: Optional[str] = None
    active: bool = True


@router.get("/users")
async def list_users(user=Depends(require("users"))):
    return [user_out(u) for u in await raw_db.users.find({"tenant_id": user["tenant_id"]}).sort("name", 1).to_list(1000)]


@router.post("/users")
async def create_user(body: UserIn, user=Depends(require("users"))):
    if body.role not in ROLES:
        raise HTTPException(400, "Rol invalid")
    if not body.password or len(body.password) < 8:
        raise HTTPException(400, "Parola trebuie să aibă minim 8 caractere")
    email = body.email.strip().lower()
    if await raw_db.users.find_one({"email": email}):
        raise HTTPException(400, "Email deja existent")
    if body.active and await tenant_plan(user["tenant_id"]) == "BASIC":
        active_users = await raw_db.users.count_documents({"tenant_id": user["tenant_id"], "active": True})
        if active_users >= 3:
            raise HTTPException(403, "Planul BASIC permite maximum 3 utilizatori activi")
    doc = {"email": email, "name": body.name, "role": body.role, "active": body.active,
           "password_hash": hash_password(body.password), "tenant_id": user["tenant_id"],
           "assigned_branch_ids": [user["active_branch_id"]], "active_branch_id": user["active_branch_id"], "created_at": iso()}
    r = await raw_db.users.insert_one(doc)
    await audit(user, "create", "user", str(r.inserted_id), email)
    doc["_id"] = r.inserted_id
    return user_out(doc)


@router.put("/users/{uid}")
async def update_user(uid: str, body: UserIn, user=Depends(require("users"))):
    if body.role not in ROLES:
        raise HTTPException(400, "Rol invalid")
    upd = {"name": body.name, "role": body.role, "active": body.active}
    if body.password:
        if len(body.password) < 8:
            raise HTTPException(400, "Parola trebuie să aibă minim 8 caractere")
        upd["password_hash"] = hash_password(body.password)
    target = await raw_db.users.find_one({"_id": oid(uid), "tenant_id": user["tenant_id"]})
    if not target:
        raise HTTPException(404, "Not found")
    if target.get("platform_role") and user.get("platform_role") != "SUPERADMIN":
        raise HTTPException(403, "Contul Superadmin poate fi administrat doar de Superadmin")
    if body.active and not target.get("active", True) and await tenant_plan(user["tenant_id"]) == "BASIC":
        active_users = await raw_db.users.count_documents({"tenant_id": user["tenant_id"], "active": True})
        if active_users >= 3:
            raise HTTPException(403, "Planul BASIC permite maximum 3 utilizatori activi")
    await raw_db.users.update_one({"_id": oid(uid)}, {"$set": upd})
    await audit(user, "update", "user", uid, body.email)
    return user_out(await raw_db.users.find_one({"_id": oid(uid)}))


@router.delete("/users/{uid}")
async def delete_user(uid: str, user=Depends(require("users"))):
    if uid == user["id"]:
        raise HTTPException(400, "Nu vă puteți șterge propriul cont")
    target = await raw_db.users.find_one({"_id": oid(uid), "tenant_id": user["tenant_id"]})
    if not target:
        raise HTTPException(404, "Not found")
    if target.get("platform_role") and user.get("platform_role") != "SUPERADMIN":
        raise HTTPException(403, "Contul Superadmin poate fi administrat doar de Superadmin")
    await raw_db.users.delete_one({"_id": oid(uid)})
    await audit(user, "delete", "user", uid)
    return {"ok": True}


@router.get("/settings")
async def read_settings(user=Depends(get_current_user)):
    return await get_settings()


@router.put("/settings")
async def write_settings(body: dict, user=Depends(require("settings"))):
    allowed_fields = {
        "name", "cui", "reg_com", "capital", "address", "city", "county_code", "iban", "bank",
        "phone", "email", "rar_authorization", "vat_rate", "payment_terms_days", "labor_rates",
        "elevators", "invoice_series", "proforma_series", "custom_subdomain",
    }
    body = {key: value for key, value in body.items() if key in allowed_fields}
    custom_subdomain = str(body.get("custom_subdomain") or "").strip().lower()
    if custom_subdomain:
        if await tenant_plan(user["tenant_id"]) == "BASIC":
            raise HTTPException(403, "Subdomeniul dedicat este disponibil doar în planurile FULL sau ENTERPRISE")
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", custom_subdomain):
            raise HTTPException(400, "Subdomeniu invalid")
        duplicate = await raw_db.settings.find_one({
            "custom_subdomain": custom_subdomain,
            "tenant_id": {"$ne": user["tenant_id"]},
        })
        if duplicate:
            raise HTTPException(400, "Subdomeniul este deja folosit de alt tenant")
        body["custom_subdomain"] = custom_subdomain
    update = {"$set": body, "$setOnInsert": {"kind": "company"}}
    if "custom_subdomain" in body and not custom_subdomain:
        body.pop("custom_subdomain")
        update["$unset"] = {"custom_subdomain": ""}
    try:
        await db.settings.update_one({"kind": "company"}, update, upsert=True)
    except DuplicateKeyError as error:
        raise HTTPException(400, "Subdomeniul este deja folosit de alt tenant") from error
    await audit(user, "update", "settings", "company")
    return await get_settings()


@router.put("/settings/logo")
async def upload_tenant_logo(body: TenantLogoIn, user=Depends(require("settings"))):
    if await tenant_plan(user["tenant_id"]) == "BASIC":
        raise HTTPException(403, "Logo-ul personalizat este disponibil doar în planurile FULL sau ENTERPRISE")
    match = re.fullmatch(r"data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)", body.data_url)
    if not match:
        raise HTTPException(400, "Logo invalid. Sunt acceptate PNG, JPEG sau WebP")
    try:
        content = base64.b64decode(match.group(2), validate=True)
    except ValueError as error:
        raise HTTPException(400, "Logo Base64 invalid") from error
    if not content or len(content) > 1024 * 1024:
        raise HTTPException(400, "Logo-ul poate avea maximum 1 MB")
    current = await db.settings.find_one({"kind": "company"}) or {}
    previous = current.get("custom_logo_data_url", "")
    previous_size = len(base64.b64decode(previous.split(",", 1)[1])) if "," in previous else 0
    tenant = await raw_db.tenants.find_one({"_id": user["tenant_id"]}) or {}
    used = max(0, tenant.get("document_storage_used_bytes", 0) - previous_size + len(content))
    if used > plan_limits(await tenant_plan(user["tenant_id"]))["storage_mb"] * 1024 * 1024:
        raise HTTPException(403, "Limita de storage a planului a fost depășită")
    await db.settings.update_one(
        {"kind": "company"},
        {"$set": {"custom_logo_data_url": body.data_url, "custom_logo_mime": match.group(1)}},
        upsert=True,
    )
    await raw_db.tenants.update_one({"_id": user["tenant_id"]}, {"$set": {"document_storage_used_bytes": used}})
    await audit(user, "upload_custom_logo", "settings", "company")
    return await get_settings()


@router.delete("/settings/logo")
async def delete_tenant_logo(user=Depends(require("settings"))):
    if await tenant_plan(user["tenant_id"]) == "BASIC":
        raise HTTPException(403, "Logo-ul personalizat este disponibil doar în planurile FULL sau ENTERPRISE")
    current_settings = await db.settings.find_one({"kind": "company"}) or {}
    previous_logo = current_settings.get("custom_logo_data_url", "")
    previous_size = len(base64.b64decode(previous_logo.split(",", 1)[1])) if "," in previous_logo else 0
    await db.settings.update_one(
        {"kind": "company"},
        {"$unset": {"custom_logo_data_url": "", "custom_logo_mime": ""}},
    )
    tenant = await raw_db.tenants.find_one({"_id": user["tenant_id"]}) or {}
    used = max(0, tenant.get("document_storage_used_bytes", 0) - previous_size)
    await raw_db.tenants.update_one(
        {"_id": user["tenant_id"]},
        {"$set": {"document_storage_used_bytes": used}},
    )
    await audit(user, "delete_custom_logo", "settings", "company")
    return await get_settings()


@router.get("/audit")
async def audit_list(user=Depends(require("users"))):
    return [ser(a) for a in await db.audit_logs.find().sort("at", -1).to_list(300)]
