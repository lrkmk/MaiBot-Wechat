"""Internal-only static file server for the built maimai-rating-web SPA
(b50_frontend/dist/), with SPA fallback so Vue Router's history-mode
routes (/{username}) resolve to index.html instead of 404ing.

Bound to 127.0.0.1 only — Playwright is the only intended client, running
on the same machine. Never exposed through the public web_multi.py routes
or opened in the EC2 security group.
"""

from pathlib import Path

from aiohttp import web

DIST_DIR = Path(__file__).parent / "b50_frontend" / "dist"
PORT = 5511


async def _handle(request: web.Request) -> web.Response:
    rel = request.path.lstrip("/")
    candidate = DIST_DIR / rel
    if rel and candidate.is_file():
        return web.FileResponse(candidate)
    return web.FileResponse(DIST_DIR / "index.html")


async def start() -> web.AppRunner:
    app = web.Application()
    app.router.add_route("GET", "/{tail:.*}", _handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", PORT)
    await site.start()
    return runner
