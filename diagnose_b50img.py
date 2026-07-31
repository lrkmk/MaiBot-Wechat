"""One-off diagnostic: run this directly on the server to find exactly
which step of /mai b50img hangs (internal static server / browser launch /
page.goto / screenshot). Prints after each step so the last line before it
stalls tells you where. Run: uv run python diagnose_b50img.py
"""

import asyncio
import errno
import time

import aiohttp

import b50_frontend_server


async def main():
    t0 = time.time()

    def log(msg):
        print(f"[{time.time() - t0:5.1f}s] {msg}", flush=True)

    runner = None
    log("starting internal static server...")
    try:
        runner = await b50_frontend_server.start()
        log("internal static server started")
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        log("port already in use — the wechat-bot service is already running "
            "its own copy, that's fine, testing against that one instead")

    log("checking internal server responds to a plain HTTP request...")
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"http://127.0.0.1:{b50_frontend_server.PORT}/", timeout=aiohttp.ClientTimeout(total=5)
        ) as resp:
            log(f"internal server responded: {resp.status}")

    log("importing playwright...")
    from playwright.async_api import async_playwright

    log("launching headless chromium (no extra args)...")
    async with async_playwright() as p:
        browser = await asyncio.wait_for(p.chromium.launch(), timeout=20)
        log("browser launched (plain)")
        await browser.close()
        log("browser closed")

        log("launching headless chromium (with our real args)...")
        browser2 = await asyncio.wait_for(
            p.chromium.launch(
                args=[
                    "--disable-web-security",
                    "--disable-site-isolation-trials",
                    "--proxy-bypass-list=127.0.0.1;localhost",
                ]
            ),
            timeout=20,
        )
        log("browser launched (with real args)")

        page = await browser2.new_page(viewport={"width": 900, "height": 1600})
        log("page created")

        log("navigating to internal server...")
        await asyncio.wait_for(
            page.goto(
                f"http://127.0.0.1:{b50_frontend_server.PORT}/12345678",
                wait_until="load",
            ),
            timeout=20,
        )
        log("navigation done (load)")

        log("taking screenshot of .container...")
        png = await asyncio.wait_for(page.locator(".container").screenshot(type="png"), timeout=20)
        log(f"screenshot done, {len(png)} bytes")

        await browser2.close()
        log("all done, everything works")

    if runner is not None:
        await runner.cleanup()


asyncio.run(main())
