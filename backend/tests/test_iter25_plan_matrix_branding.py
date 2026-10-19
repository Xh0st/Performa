# Iteration 25: BASIC/FULL/ENTERPRISE plan matrix (branch/user/WO quotas, premium gating) + PDF branding
# (Performa header/footer for BASIC, custom Base64 logo + no footer for FULL/ENTERPRISE). Needs iter25_fixture.py setup.
import asyncio
import base64
import io
import json
import os
import re
import sys
from datetime import datetime, timezone

import fitz
import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
sys.path.insert(0, "/app/backend")

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
STATE = json.load(open("/tmp/iter25.json"))
T = STATE["tenants"]
SUF = STATE["suf"]
FOOTER = "Generat cu Performa - performa.net"
LOOP = asyncio.new_event_loop()
_cli = None
_txt = open("/app/memory/test_credentials.md").read()
OWNER_PW = re.search(r"andrei\.melek@gmail\.com / (\S+)", _txt).group(1)
LOGO_W, LOGO_H = 64, 32
_buf = io.BytesIO()
Image.new("RGB", (LOGO_W, LOGO_H), (200, 20, 20)).save(_buf, "PNG")
LOGO_URL = "data:image/png;base64," + base64.b64encode(_buf.getvalue()).decode()


def run(c):
    return LOOP.run_until_complete(c)


def rdb():
    global _cli
    if _cli is None:
        asyncio.set_event_loop(LOOP)
        _cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return _cli[os.environ["DB_NAME"]]


def sess(plan):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {T[plan]['token']}"
    return s


@pytest.fixture(scope="module")
def owner():
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": "andrei.melek@gmail.com", "password": OWNER_PW})
    assert r.status_code == 200
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


def pdf_info(content):
    doc = fitz.open(stream=content, filetype="pdf")
    text = "\n".join(p.get_text() for p in doc)
    imgs = [(i[2], i[3]) for p in doc for i in p.get_images(full=True)]
    return text, imgs


LIMITS = {"BASIC": (1, 500, 500), "FULL": (5, 10240, 5000), "ENTERPRISE": (999, 51200, None)}


# --- plan limits in settings + tenant record
@pytest.mark.parametrize("plan", ["BASIC", "FULL", "ENTERPRISE"])
def test_settings_plan_limits(plan, owner):
    s = sess(plan).get(f"{BASE}/settings").json()
    b, st, wo = LIMITS[plan]
    assert s["subscription_plan"] == plan
    assert s["plan_limits"] == {"branches": b, "storage_mb": st, "work_orders_monthly": wo}
    t = [x for x in owner.get(f"{BASE}/platform/tenants").json() if x["id"] == T[plan]["id"]][0]
    assert t["max_branches_allowed"] == b


# --- branch quota
def _branch(owner, plan, i):
    return owner.post(f"{BASE}/platform/tenants/{T[plan]['id']}/branches",
                      json={"branch_id": f"temp25-br-{plan.lower()}-{i}-{SUF}", "branch_name": f"TEMP25 br {i}"})


def test_branch_quota_basic(owner):
    assert _branch(owner, "BASIC", 2).status_code == 403


def test_branch_quota_full(owner):
    for i in range(2, 6):
        assert _branch(owner, "FULL", i).status_code == 200
    r = _branch(owner, "FULL", 6)
    assert r.status_code == 403


def test_branch_quota_enterprise(owner):
    for i in range(2, 8):
        assert _branch(owner, "ENTERPRISE", i).status_code == 200


# --- premium gating
PREMIUM_GET = ["/appointments?start=2026-01-01T00:00:00%2B00:00&end=2026-01-31T00:00:00%2B00:00", "/products", "/efactura/config",
               "/efactura/inbox", "/rar-autopass/config"]


@pytest.mark.parametrize("plan", ["BASIC", "FULL", "ENTERPRISE"])
def test_premium_gating(plan):
    s = sess(plan)
    expect_ok = plan != "BASIC"
    for p in PREMIUM_GET:
        r = s.get(f"{BASE}{p}")
        assert (r.status_code == 200) == expect_ok, (p, r.status_code, r.text[:120])
        if not expect_ok:
            assert r.status_code == 403
    r = s.put(f"{BASE}/settings/logo", json={"data_url": LOGO_URL})
    assert r.status_code == (200 if expect_ok else 403)
    r = s.put(f"{BASE}/settings", json={"custom_subdomain": f"temp25-{plan.lower()}-{SUF}"})
    assert r.status_code == (200 if expect_ok else 403), r.text
    me = s.get(f"{BASE}/auth/me").json()
    assert ("planning" in me["permissions"]) == expect_ok
    assert ("stock" in me["permissions"]) == expect_ok


def test_basic_logo_delete_blocked():
    assert sess("BASIC").delete(f"{BASE}/settings/logo").status_code == 403


# --- user quota
def _user(s, tag):
    return s.post(f"{BASE}/users", json={"email": f"temp25_u{tag}_{SUF}@example.com", "name": f"TEMP25 {tag}",
                                         "role": "receptioner", "password": "TempUser2026!", "active": True})


def test_basic_user_quota():
    s = sess("BASIC")
    assert _user(s, "b1").status_code == 200
    assert _user(s, "b2").status_code == 200
    r = _user(s, "b3")
    assert r.status_code == 403 and "3" in r.json()["detail"]


def test_full_enterprise_no_3_user_limit():
    for plan in ("FULL", "ENTERPRISE"):
        for i in range(4):
            assert _user(sess(plan), f"{plan[0]}{i}").status_code == 200


def test_superadmin_tenant_admin_bypasses_basic_user_quota(owner):
    # BASIC tenant already has 3 active users; superadmin admin creation should respect the cap too
    r = owner.post(f"{BASE}/platform/tenants/{T['BASIC']['id']}/admins",
                   json={"email": f"temp25_sa_{SUF}@example.com", "name": "TEMP25 SA", "password": "TempUser2026!",
                         "branch_ids": [T["BASIC"]["branch_id"]]})
    active = run(rdb().users.count_documents({"tenant_id": T["BASIC"]["id"], "active": True}))
    assert r.status_code == 403, f"created 4th active user via superadmin route (status {r.status_code}, active={active})"


# --- monthly WO quota (controlled seed)
def _seed_wo(plan, n):
    month = datetime.now(timezone.utc).isoformat()
    run(rdb().work_orders.insert_many([{"number": f"TEMP25-Q-{i}", "tenant_id": T[plan]["id"],
                                        "branch_id": T[plan]["branch_id"], "status": "noua", "created_at": month,
                                        "lines": [], "temp_iter25": True} for i in range(n)]))


def _client_vehicle(s, tag):
    c = s.post(f"{BASE}/clients", json={"name": f"TEMP25 client {tag}", "type": "pf", "phone": "0700000000"})
    assert c.status_code in (200, 201), c.text
    vin = (f"TMP25{tag}{SUF}" + "0" * 17)[:17].upper()
    v = s.post(f"{BASE}/vehicles", json={"client_id": c.json()["id"], "vin": vin, "plate": f"B25{tag[:3]}",
                                          "make": "Dacia", "model": "Logan"})
    assert v.status_code in (200, 201), v.text
    return c.json()["id"], v.json()["id"]


def _wo(s, cid, vid):
    return s.post(f"{BASE}/work-orders", json={"client_id": cid, "vehicle_id": vid, "mileage_in": 1000,
                                                "complaint": "TEMP25", "photos": {}, "signature": "data:image/png;base64,AA"})


@pytest.mark.parametrize("plan,seed", [("BASIC", 499), ("FULL", 4999)])
def test_wo_monthly_quota(plan, seed):
    s = sess(plan)
    cid, vid = _client_vehicle(s, plan[:2])
    _seed_wo(plan, seed)
    r = _wo(s, cid, vid)
    assert r.status_code in (200, 201), r.text
    r = _wo(s, cid, vid)
    assert r.status_code == 403
    assert str(LIMITS[plan][2]) in r.json()["detail"]


def test_wo_quota_enterprise_unlimited():
    s = sess("ENTERPRISE")
    cid, vid = _client_vehicle(s, "EN")
    _seed_wo("ENTERPRISE", 5001)
    r = _wo(s, cid, vid)
    assert r.status_code in (200, 201), r.text


# --- PDF branding
def _assert_basic_pdf(content):
    text, imgs = pdf_info(content)
    assert "Performa" in text and FOOTER in text
    assert (458, 201) in imgs, imgs
    assert (LOGO_W, LOGO_H) not in imgs


def _assert_premium_pdf(content):
    text, imgs = pdf_info(content)
    assert FOOTER not in text
    assert (LOGO_W, LOGO_H) in imgs, imgs
    assert (458, 201) not in imgs


def _pdfs(plan):
    s = sess(plan)
    d = T[plan]["docs"]
    out = {}
    r = s.get(f"{BASE}/reports/final-inspections/pdf", params={"start": "2026-01-01", "end": "2026-12-31"})
    assert r.status_code == 200, r.text
    out["anexa5"] = r.content
    r = s.get(f"{BASE}/warranties/invoices/{d['warranty']}/certificate")
    assert r.status_code == 200, r.text
    out["warranty"] = r.content
    r = s.get(f"{BASE}/efactura/inbox/{d['efactura']}/pdf")
    if plan == "BASIC":
        assert r.status_code == 403
    else:
        assert r.status_code == 200, r.text
        out["efactura"] = r.content
    return out


def test_basic_pdf_branding():
    for name, c in _pdfs("BASIC").items():
        _assert_basic_pdf(c)


def test_basic_efactura_builder_branding():
    from efactura_pdf import render_pdf
    m = run(rdb().efactura_inbox.find_one({"tenant_id": T["BASIC"]["id"]}))
    _assert_basic_pdf(render_pdf(m["xml"], m, include_footer=True, custom_logo_data_url=""))


@pytest.mark.parametrize("plan", ["FULL", "ENTERPRISE"])
def test_premium_pdf_branding_custom_logo(plan):
    s = sess(plan)
    assert s.put(f"{BASE}/settings/logo", json={"data_url": LOGO_URL}).status_code == 200
    for name, c in _pdfs(plan).items():
        try:
            _assert_premium_pdf(c)
        except AssertionError as e:
            raise AssertionError(f"{plan}/{name}: {e}")


def test_premium_pdf_without_logo_falls_back_and_no_footer():
    s = sess("ENTERPRISE")
    assert s.delete(f"{BASE}/settings/logo").status_code == 200
    for name, c in _pdfs("ENTERPRISE").items():
        text, imgs = pdf_info(c)
        assert FOOTER not in text and (458, 201) in imgs and "Performa" in text, name
    assert s.put(f"{BASE}/settings/logo", json={"data_url": LOGO_URL}).status_code == 200


def test_downgraded_tenant_with_stale_logo_gets_performa_branding(owner):
    # FULL tenant with uploaded logo downgraded to BASIC -> PDFs must use Performa logo + footer
    t = T["FULL"]
    base = {"company_name": t["company"], "cui": f"RO-TEMP25FULL{SUF}".upper(), "admin_email": t["email"], "status": "ACTIVE"}
    r = owner.put(f"{BASE}/platform/tenants/{t['id']}", json=base | {"subscription_plan": "BASIC"})
    assert r.status_code == 200, r.text
    try:
        r = sess("FULL").get(f"{BASE}/reports/final-inspections/pdf", params={"start": "2026-01-01", "end": "2026-12-31"})
        assert r.status_code == 200
        text, imgs = pdf_info(r.content)
        assert FOOTER in text
        assert "Performa" in text and (458, 201) in imgs and (LOGO_W, LOGO_H) not in imgs, \
            f"BASIC (downgraded) Anexa5 uses stale custom logo; images={imgs}"
    finally:
        owner.put(f"{BASE}/platform/tenants/{t['id']}", json=base | {"subscription_plan": "FULL"})


# --- invoice seller snapshot used by PrintDoc header
def test_invoice_seller_snapshot_has_branding_fields():
    inv = sess("BASIC").get(f"{BASE}/invoices/{T['BASIC']['docs']['fiscal']}").json()
    seller = inv["seller"]
    assert "subscription_plan" in seller, f"seller keys={sorted(seller)} -> PrintDoc Invoice header cannot detect BASIC"
