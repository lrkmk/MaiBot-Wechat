"""Multi-user demo: each visitor binds their OWN WeChat account.

ClawBot only allows one bound bot instance per WeChat account, so there is
no such thing as "one shared bot contact everyone messages" — every user
who wants to use the bot has to scan their own QR code and get their own
ClawBot session. This server just runs one isolated WeChatBot login per
visiting browser session and shows each of them their own QR code.

Run: python web_multi.py
Open: http://localhost:8080
"""

import asyncio
import base64
import io
import uuid
from pathlib import Path

import qrcode
from aiohttp import web
from wechatbot import WeChatBot

from commands import dispatch

BASE_DIR = Path(__file__).parent
CRED_DIR = BASE_DIR / ".sessions"
CRED_DIR.mkdir(exist_ok=True)

# session_id -> {"status", "qr_url", "qr_png", "error"}
sessions: dict[str, dict] = {}


def render_qr_png(url: str) -> str:
    """qrcode_img_content is a plain link — encode it into a QR PNG data URI."""
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def on_qr_url(state: dict, url: str) -> None:
    state.update(status="waiting", qr_url=url, qr_png=render_qr_png(url))


async def run_session(session_id: str) -> None:
    state = sessions[session_id]
    cred_path = CRED_DIR / f"{session_id}.json"

    bot = WeChatBot(
        cred_path=cred_path,
        on_qr_url=lambda url: on_qr_url(state, url),
        on_scanned=lambda: state.update(status="scanned"),
        on_expired=lambda: state.update(status="expired"),
        on_error=lambda err: state.update(status="error", error=str(err)),
    )

    @bot.on_message
    async def handle(msg):
        await dispatch(bot, msg)

    try:
        await bot.login()
        state.update(status="confirmed")
        await bot.start()
    except Exception as e:
        state.update(status="error", error=str(e))


async def new_session(request: web.Request) -> web.Response:
    session_id = uuid.uuid4().hex
    sessions[session_id] = {
        "status": "starting",
        "qr_url": None,
        "qr_png": None,
        "error": None,
    }
    asyncio.create_task(run_session(session_id))
    return web.json_response({"session_id": session_id})


async def session_status(request: web.Request) -> web.Response:
    state = sessions.get(request.match_info["session_id"])
    if state is None:
        return web.json_response({"status": "not_found"}, status=404)
    return web.json_response(state)


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(BASE_DIR / "static" / "index.html")


app = web.Application()
app.router.add_get("/", index)
app.router.add_post("/api/session", new_session)
app.router.add_get("/api/session/{session_id}", session_status)

if __name__ == "__main__":
    web.run_app(app, port=8080)
