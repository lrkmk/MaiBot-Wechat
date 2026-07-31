"""Render a Best 50 image using MeowKJ/maimai-rating-web's frontend
(b50_frontend/dist/, built ahead of time — see README), driven headlessly
via Playwright.

Instead of letting that frontend fetch data itself (it'd need a real
DataProviderFactory-selected friend_code/QQ lookup, and — worse — its
LuoXue.ts bundles the lxns developer key into client-side JS, which we
don't want to ship even to our own headless browser), we intercept its two
network calls and feed it data from lxns_dev_client.py, which we already
fetch server-side for the text-based /mai commands. Same lxns.net response
shape (RawLuoXueUserData / RawLuoXueSongsData), no transformation needed.
"""

import json

from playwright.async_api import async_playwright

import lxns_dev_client as dev
from b50_frontend_server import PORT

# DataProviderFactory.ts only routes to the LuoXue/lxns provider for a
# 7-11 digit "username" (it assumes that's a QQ number). Our friend_code is
# 15 digits and wouldn't match — but since we intercept every network call
# that provider makes anyway, the actual value here is never used for
# anything except satisfying that regex.
DUMMY_ROUTE_PARAM = "12345678"


def _wrap(data) -> str:
    return json.dumps({"code": 200, "success": True, "data": data})


async def render_b50_image(friend_code: str) -> bytes:
    player = await dev.get_player(friend_code)
    bests = await dev.get_bests(friend_code)

    async with async_playwright() as p:
        # Not a real user's browser — safe to disable CORS enforcement.
        # maimai.mpas.top (the asset host this frontend pulls covers/badges
        # from) doesn't send Access-Control-Allow-Origin on some paths,
        # which otherwise blocks those images from rendering at all.
        browser = await p.chromium.launch(
            args=["--disable-web-security", "--disable-site-isolation-trials"]
        )
        try:
            page = await browser.new_page(viewport={"width": 900, "height": 1600})

            async def fulfill_player(route):
                await route.fulfill(content_type="application/json", body=_wrap(player))

            async def fulfill_bests(route):
                await route.fulfill(content_type="application/json", body=_wrap(bests))

            await page.route("**/api/v0/maimai/player/qq/**", fulfill_player)
            await page.route("**/api/v0/maimai/player/*/bests", fulfill_bests)

            await page.goto(
                f"http://127.0.0.1:{PORT}/{DUMMY_ROUTE_PARAM}", wait_until="networkidle"
            )
            # Song-list metadata fetch (~1.2MB, real network call to
            # lxns.net, not intercepted — it's a public endpoint) needs
            # more than networkidle's quiet-window to fully parse+render.
            await page.wait_for_timeout(8000)

            return await page.locator(".container").screenshot(type="png")
        finally:
            await browser.close()
