"""Client for lxns.net's OAuth-protected maimai API.

Per https://maimai.lxns.net/docs/oauth-guide:
- access_token is only valid for 15 minutes
- refresh_token rotates on every use (old one dies the moment you use it),
  and the rotated one must be persisted or the next refresh fails

So every call here refreshes first rather than tracking expiry locally —
simpler, and it doubles as "keep the refresh token from going 30 days
stale from disuse".
"""

import os

import aiohttp

from secrets_store import get_token, set_token

TOKEN_URL = "https://maimai.lxns.net/api/v0/oauth/token"
PLAYER_URL = "https://maimai.lxns.net/api/v0/user/maimai/player"

CLIENT_ID = os.environ.get("LXNS_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("LXNS_CLIENT_SECRET", "")


class LxnsError(Exception):
    """Message is user-facing — safe to relay straight into a bot reply."""


async def _refresh(wechat_user_id: str, refresh_token: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            TOKEN_URL,
            json={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body = await resp.json()

    if resp.status != 200 or "access_token" not in body:
        if body.get("error") == "invalid_grant":
            raise LxnsError("maimai 授权已失效，需要重新绑定")
        raise LxnsError(f"刷新令牌失败: {body.get('error_description') or body}")

    fields = {"access_token": body["access_token"]}
    for key in ("refresh_token", "token_type", "scope", "expires_in"):
        if body.get(key) is not None:
            fields[key] = body[key]
    await set_token(wechat_user_id, "lxns", fields)
    return fields


async def get_player(wechat_user_id: str) -> dict:
    """Refresh the token, then fetch the caller's own maimai player data."""
    stored = await get_token(wechat_user_id, "lxns")
    if stored is None or "refresh_token" not in stored:
        raise LxnsError('还没绑定 maimai 查分账号 — 网页上点"绑定 maimai 查分账号"')

    fresh = await _refresh(wechat_user_id, stored["refresh_token"])

    async with aiohttp.ClientSession() as session:
        async with session.get(
            PLAYER_URL,
            headers={"Authorization": f"Bearer {fresh['access_token']}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body = await resp.json()

    if not body.get("success"):
        raise LxnsError(f"查询失败: {body.get('message', resp.status)}")

    # OAuth-token endpoints use lxns's flat error format (docs say so
    # explicitly); this player endpoint uses the older {success,code,data}
    # envelope like their public query API. Haven't seen a real success
    # response yet (needs someone to actually finish OAuth first) — data
    # shape below is a best guess, adjust once we see a live response.
    return body.get("data", body)
