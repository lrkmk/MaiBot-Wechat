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

The browser itself is a long-lived singleton (see start_browser/
stop_browser) instead of a fresh `chromium.launch()` per call — launching
Chromium costs ~1-2s, not worth paying on every /mai b50img. Each call gets
its own BrowserContext (cheap, isolated cookies/localStorage/cache) so
concurrent requests don't interfere with each other's route interception.
"""

import json

from playwright.async_api import Browser, Playwright, async_playwright

import lxns_dev_client as dev
from b50_frontend_server import PORT

# DataProviderFactory.ts only routes to the LuoXue/lxns provider for a
# 7-11 digit "username" (it assumes that's a QQ number). Our friend_code is
# 15 digits and wouldn't match — but since we intercept every network call
# that provider makes anyway, the actual value here is never used for
# anything except satisfying that regex.
DUMMY_ROUTE_PARAM = "12345678"

_LAUNCH_ARGS = [
    # Not a real user's browser — safe to disable CORS enforcement.
    # maimai.mpas.top (the asset host this frontend pulls covers/badges
    # from) doesn't send Access-Control-Allow-Origin on some paths, which
    # otherwise blocks those images from rendering at all.
    "--disable-web-security",
    "--disable-site-isolation-trials",
    # If the host has any system/env proxy configured, make sure it never
    # applies to our own loopback server — a proxy trying to forward a
    # 127.0.0.1 request is a classic way for page.goto() to hang instead
    # of erroring. External asset fetches (lxns.net, mpas.top) still go
    # through the proxy normally, only loopback is bypassed.
    "--proxy-bypass-list=127.0.0.1;localhost",
]

_playwright: Playwright | None = None
_browser: Browser | None = None


def _wrap(data) -> str:
    return json.dumps({"code": 200, "success": True, "data": data})


async def start_browser() -> None:
    """Launch the shared headless browser once — call from web_multi.py's
    on_startup so the first real /mai b50img doesn't pay the launch cost."""
    global _playwright, _browser
    if _browser is not None:
        return
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(args=_LAUNCH_ARGS)


async def stop_browser() -> None:
    global _playwright, _browser
    if _browser is not None:
        await _browser.close()
        _browser = None
    if _playwright is not None:
        await _playwright.stop()
        _playwright = None


async def render_b50_image(friend_code: str) -> bytes:
    if _browser is None or not _browser.is_connected():
        await start_browser()

    player = await dev.get_player(friend_code)
    bests = await dev.get_bests(friend_code)

    context = await _browser.new_context(viewport={"width": 900, "height": 1600})
    try:
        page = await context.new_page()

        async def fulfill_player(route):
            await route.fulfill(content_type="application/json", body=_wrap(player))

        async def fulfill_bests(route):
            await route.fulfill(content_type="application/json", body=_wrap(bests))

        await page.route("**/api/v0/maimai/player/qq/**", fulfill_player)
        await page.route("**/api/v0/maimai/player/*/bests", fulfill_bests)

        # "networkidle" is flaky here — this page has some background
        # network activity that never goes fully quiet, so that wait
        # condition intermittently never resolves and hangs forever.
        # "load" + a fixed extra wait is slower but actually reliable.
        await page.goto(f"http://127.0.0.1:{PORT}/{DUMMY_ROUTE_PARAM}", wait_until="load")
        # Song-list metadata fetch (~1.2MB, real network call to lxns.net,
        # not intercepted — it's a public endpoint) plus rendering all the
        # charts takes a while after `load` fires.
        await page.wait_for_timeout(10000)

        # JPEG, not PNG: this page is a long scrolling screenshot (tall,
        # colorful, lots of gradients/photos) so PNG comes out quite large
        # — the reference project itself exports as JPEG for the same
        # reason (see capture.ts: toDataURL("image/jpeg", 0.95)).
        return await page.locator(".container").screenshot(type="jpeg", quality=90)
    finally:
        await context.close()
