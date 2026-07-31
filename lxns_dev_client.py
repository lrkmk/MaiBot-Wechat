"""Client for lxns.net's Developer API — a single app-wide key, auth'd via
`Authorization: <key>` (no "Bearer" prefix, unlike the OAuth client in
lxns_client.py — these are two separate credential types, not
interchangeable, per https://maimai.lxns.net/docs/developer-guide).

Scoped to any player by friend_code (already collected via /mai bind, see
storage.py) — no per-user OAuth dance needed, but only works for players
who've enabled "允许第三方访问" in their own lxns.net account settings.
"""

import os

import aiohttp

BASE_URL = "https://maimai.lxns.net/api/v0/maimai"
DEVELOPER_TOKEN = os.environ.get("LXNS_DEVELOPER_TOKEN", "")


class LxnsDevError(Exception):
    """Message is user-facing — safe to relay straight into a bot reply."""


async def _get(path: str) -> dict:
    if not DEVELOPER_TOKEN:
        raise LxnsDevError("服务端还没配置开发者密钥")

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}{path}",
            headers={"Authorization": DEVELOPER_TOKEN},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body = await resp.json()

    if not body.get("success"):
        raise LxnsDevError(f"查询失败: {body.get('message', resp.status)}")
    return body.get("data")


async def get_player(friend_code: str) -> dict:
    return await _get(f"/player/{friend_code}")


async def get_bests(friend_code: str) -> dict:
    """standard_total/dx_total + standard/dx/*_selections score lists."""
    return await _get(f"/player/{friend_code}/bests")
