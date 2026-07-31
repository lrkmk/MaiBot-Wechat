"""Multi-user demo: each visitor binds their OWN WeChat account.

ClawBot only allows one bound bot instance per WeChat account, so there is
no such thing as "one shared bot contact everyone messages" — every user
who wants to use the bot has to scan their own QR code and get their own
ClawBot session.

Persistence: once a login is confirmed, its credentials are filed under
`.sessions/{account_id}.json`, keyed by the WeChat account's own iLink id
— not by anything this server invents. On startup every such file is
reloaded and reconnected automatically (no QR needed again).

`login_id` below is *not* a persistent identity — it only exists so a
browser tab can poll the status of its own not-yet-authenticated QR flow.
It's discarded the moment login succeeds.

Run: python web_multi.py
Open: http://localhost:8080
"""

import asyncio
import base64
import io
import json
import os
import uuid
from pathlib import Path

import qrcode
from aiohttp import web
from wechatbot import WeChatBot

from commands import dispatch
from secrets_store import set_token

BASE_DIR = Path(__file__).parent
CRED_DIR = BASE_DIR / ".sessions"
CRED_DIR.mkdir(exist_ok=True)

# The frontend (static/index.html) is meant to be deployable separately, e.g.
# to Cloudflare Pages, while this API server runs wherever it can stay a
# long-lived process. Set ALLOWED_ORIGIN to that frontend's origin in
# production; "*" is fine for local development only.
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
PORT = int(os.environ.get("PORT", 8080))

# Shared secret the oauth-callback Worker authenticates with when it POSTs
# a freshly-exchanged token here. Must match the Worker's BACKEND_SECRET.
WORKER_SHARED_SECRET = os.environ.get("WORKER_SHARED_SECRET", "")


@web.middleware
async def cors_middleware(request: web.Request, handler):
    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    return response

# login_id -> {"status", "qr_url", "qr_png", "error"} — in-memory only,
# scoped to a single pending (not-yet-confirmed) QR login.
pending_logins: dict[str, dict] = {}

# account_id -> running WeChatBot, for accounts currently connected
# (just logged in, or auto-resumed from disk on startup).
live_bots: dict[str, WeChatBot] = {}


def render_qr_png(url: str) -> str:
    """qrcode_img_content is a plain link — encode it into a QR PNG data URI."""
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


async def run_bot(bot: WeChatBot) -> None:
    @bot.on_message
    async def handle(msg):
        await dispatch(bot, msg)

    await bot.start()


async def start_login(login_id: str) -> None:
    """Drive one QR login attempt, then hand off to the persistent account store."""
    state = pending_logins[login_id]
    pending_path = CRED_DIR / f".pending-{login_id}.json"

    def on_qr_url(url: str) -> None:
        state.update(status="waiting", qr_url=url, qr_png=render_qr_png(url))

    bot = WeChatBot(
        cred_path=pending_path,
        on_qr_url=on_qr_url,
        on_scanned=lambda: state.update(status="scanned"),
        on_expired=lambda: state.update(status="expired"),
        on_error=lambda err: state.update(status="error", error=str(err)),
    )

    try:
        creds = await bot.login()
    except Exception as e:
        state.update(status="error", error=str(e))
        pending_path.unlink(missing_ok=True)
        return

    # Re-file credentials under the account's own id so a restart can find
    # and resume them without ever needing this login_id again.
    account_path = CRED_DIR / f"{creds.account_id}.json"
    pending_path.replace(account_path)
    bot._cred_path = account_path  # keep any future credential writes consistent

    # user_id (not account_id) is what commands.py/storage.py/secrets_store.py
    # key everything by — it's the only identifier a message handler has
    # (msg.user_id), and it's also what should go in the lxns.net authorize
    # link's &state= so /api/save-token knows whose token it just got.
    state.update(status="confirmed", account_id=creds.account_id, user_id=creds.user_id)
    live_bots[creds.account_id] = bot
    await run_bot(bot)


async def resume_bound_accounts() -> None:
    """On startup, reconnect every account that already has saved credentials."""
    for path in CRED_DIR.glob("*.json"):
        if path.name.startswith(".pending-"):
            path.unlink(missing_ok=True)  # stale — login never finished
            continue

        bot = WeChatBot(
            cred_path=path,
            on_error=lambda err, name=path.stem: print(f"[{name}] {err}"),
        )
        try:
            creds = await bot.login()
        except Exception as e:
            print(f"[resume] failed for {path.name}: {e}")
            continue

        live_bots[creds.account_id] = bot
        asyncio.create_task(run_bot(bot))
        print(f"[resume] reconnected account {creds.account_id}")


async def new_login(request: web.Request) -> web.Response:
    login_id = uuid.uuid4().hex
    pending_logins[login_id] = {
        "status": "starting",
        "qr_url": None,
        "qr_png": None,
        "error": None,
        "account_id": None,
        "user_id": None,
    }
    asyncio.create_task(start_login(login_id))
    return web.json_response({"login_id": login_id})


async def login_status(request: web.Request) -> web.Response:
    state = pending_logins.get(request.match_info["login_id"])
    if state is None:
        return web.json_response({"status": "not_found"}, status=404)
    return web.json_response(state)


def is_bound_wechat_user(wechat_user_id: str) -> bool:
    """True if some already-confirmed ClawBot account has this user_id.

    Credential files are named by account_id, not user_id, so this scans
    file contents — fine at the scale of a personal-use deployment.
    """
    for path in CRED_DIR.glob("*.json"):
        if path.name.startswith(".pending-"):
            continue
        try:
            data = json.loads(path.read_text("utf-8"))
        except Exception:
            continue
        if data.get("userId") == wechat_user_id:
            return True
    return False


async def save_token(request: web.Request) -> web.Response:
    """Receive a freshly-exchanged OAuth token from the oauth-callback Worker.

    Auth is a shared secret (Bearer WORKER_SHARED_SECRET), not a public
    endpoint — the Worker is the only caller. The token is attributed to a
    WeChat account via `state`, which the authorize link must carry as
    &state=<wechat user_id> (shown on the login page after QR confirm) —
    without it there's no way to know whose token this is.
    """
    auth = request.headers.get("Authorization", "")
    if not WORKER_SHARED_SECRET or auth != f"Bearer {WORKER_SHARED_SECRET}":
        return web.json_response({"error": "unauthorized"}, status=401)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON body"}, status=400)

    wechat_user_id = str(body.get("state") or "").strip()
    if not wechat_user_id:
        return web.json_response(
            {
                "error": "missing state — the authorize link must include "
                "&state=<wechat user_id> so this token can be attributed "
                "to someone"
            },
            status=400,
        )
    if not is_bound_wechat_user(wechat_user_id):
        return web.json_response({"error": "unknown user_id in state"}, status=404)

    access_token = body.get("access_token")
    if not access_token:
        return web.json_response({"error": "missing access_token"}, status=400)

    fields = {"access_token": access_token}
    for key in ("refresh_token", "token_type", "scope", "expires_in"):
        if body.get(key) is not None:
            fields[key] = body[key]

    await set_token(wechat_user_id, "lxns", fields)
    return web.json_response({"ok": True})


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(BASE_DIR / "static" / "index.html")


async def on_startup(app: web.Application) -> None:
    asyncio.create_task(resume_bound_accounts())
    import b50_frontend_server

    await b50_frontend_server.start()


app = web.Application(middlewares=[cors_middleware])
app.on_startup.append(on_startup)
app.router.add_get("/", index)
app.router.add_post("/api/login", new_login)
app.router.add_get("/api/login/{login_id}", login_status)
app.router.add_post("/api/save-token", save_token)

if __name__ == "__main__":
    web.run_app(app, port=PORT)
