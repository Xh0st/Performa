import os
from datetime import timedelta
from typing import Optional
import jwt
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from pydantic import BaseModel
from core import (db, raw_db, ser, oid, iso, now, hash_password, verify_password, make_token, get_current_user, require,
                  permissions_for, audit, get_settings, ROLES, JWT_ALG)

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


def set_cookies(response: Response, user: dict):
    user_id = str(user["_id"])
    tenant_id = user.get("tenant_id", "")
    branch_id = user.get("active_branch_id", "")
    access = make_token(user_id, "access", ACCESS_MIN, tenant_id, branch_id)
    refresh = make_token(user_id, "refresh", 60 * 24 * 7, tenant_id, branch_id)
    response.set_cookie("access_token", access, httponly=True, secure=True, samesite="none", max_age=ACCESS_MIN * 60, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=True, samesite="none", max_age=604800, path="/")
    return access


def user_out(u: dict):
    d = ser(u)
    d["permissions"] = permissions_for(d["role"])
    return d


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
    token = set_cookies(response, user)
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login": iso()}})
    return {"user": user_out(user), "token": token}


@router.post("/auth/logout")
async def logout(response: Response):
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
    return {"user": user_out(updated), "token": set_cookies(response, updated)}


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
    return {"token": set_cookies(response, user)}


class BranchSwitchIn(BaseModel):
    branch_id: str


@router.post("/auth/active-branch")
async def switch_active_branch(body: BranchSwitchIn, response: Response, user=Depends(get_current_user)):
    branch = await raw_db.branches.find_one({"_id": body.branch_id, "tenant_id": user["tenant_id"], "status": "ACTIVE"})
    if not branch or body.branch_id not in (await raw_db.users.find_one({"_id": oid(user["id"])}))["assigned_branch_ids"]:
        raise HTTPException(403, "Acces interzis la punctul de lucru")
    await raw_db.users.update_one({"_id": oid(user["id"])}, {"$set": {"active_branch_id": body.branch_id}})
    updated = await raw_db.users.find_one({"_id": oid(user["id"])})
    return {"token": set_cookies(response, updated), "user": user_out(updated)}


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
    body.pop("_id", None)
    body.pop("tenant_id", None)
    body.pop("branch_id", None)
    await db.settings.update_one({"kind": "company"}, {"$set": body, "$setOnInsert": {"kind": "company"}}, upsert=True)
    await audit(user, "update", "settings", "company")
    return await get_settings()


@router.get("/audit")
async def audit_list(user=Depends(require("users"))):
    return [ser(a) for a in await db.audit_logs.find().sort("at", -1).to_list(300)]
