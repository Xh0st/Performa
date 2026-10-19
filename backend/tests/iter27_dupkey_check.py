# Iteration 27: deterministic check that a DuplicateKeyError raised by the unique custom_subdomain index (race past
# the find_one pre-check) is returned as 400, not 500. In-process ASGI call with the pre-check patched out.
# Requires iter25_fixture.py setup (/tmp/iter25.json).
import asyncio
import json
import sys

import httpx

sys.path.insert(0, "/app/backend")
import routes_auth  # noqa: E402
from server import app  # noqa: E402

S = json.load(open("/tmp/iter25.json"))
SD = f"temp27dk-{S['suf']}"


class _SettingsProxy:
    def __init__(self, real):
        self._real = real

    async def find_one(self, *a, **k):
        q = a[0] if a else {}
        if "custom_subdomain" in q:
            return None  # simulate race: pre-check sees nothing
        return await self._real.find_one(*a, **k)

    def __getattr__(self, n):
        return getattr(self._real, n)


class _DbProxy:
    def __init__(self, real):
        self._real = real
        self.settings = _SettingsProxy(real.settings)

    def __getattr__(self, n):
        return getattr(self._real, n)

    def __getitem__(self, n):
        return self._real[n]


async def main():
    real = routes_auth.raw_db
    tr = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=tr, base_url="http://t") as c:
        h = lambda p: {"Authorization": f"Bearer {S['tenants'][p]['token']}"}  # noqa: E731
        r = await c.put("/api/settings", json={"custom_subdomain": SD}, headers=h("FULL"))
        print("FULL set", r.status_code)
        assert r.status_code == 200
        routes_auth.raw_db = _DbProxy(real)
        try:
            r = await c.put("/api/settings", json={"custom_subdomain": SD}, headers=h("ENTERPRISE"))
        finally:
            routes_auth.raw_db = real
        print("ENTERPRISE dup (pre-check bypassed)", r.status_code, r.text[:150])
        ok = r.status_code == 400
        for p in ("FULL", "ENTERPRISE"):
            await c.put("/api/settings", json={"custom_subdomain": ""}, headers=h(p))
        cnt = await real.settings.count_documents({"custom_subdomain": SD})
        print("leftover", cnt)
        assert ok and cnt == 0
        print("PASS")


asyncio.run(main())
