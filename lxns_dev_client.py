"""Client for lxns.net's Developer API — a single app-wide key, auth'd via
`Authorization: <key>` (no "Bearer" prefix, unlike the OAuth client in
lxns_client.py — these are two separate credential types, not
interchangeable, per https://maimai.lxns.net/docs/developer-guide).

Scoped to any player by friend_code (already collected via /mai bind, see
storage.py) — no per-user OAuth dance needed, but only works for players
who've enabled "允许第三方访问" in their own lxns.net account settings.

Covers every GET endpoint under 开发者 API per
https://maimai.lxns.net/docs/api/maimai — write endpoints (POST) and the
QQ-lookup endpoint are intentionally not wrapped here.
"""

import os

import aiohttp

BASE_URL = "https://maimai.lxns.net/api/v0/maimai"
DEVELOPER_TOKEN = os.environ.get("LXNS_DEVELOPER_TOKEN", "")


class LxnsDevError(Exception):
    """Message is user-facing — safe to relay straight into a bot reply."""


async def _get(path: str, params: dict | None = None):
    if not DEVELOPER_TOKEN:
        raise LxnsDevError("服务端还没配置开发者密钥")

    query = {k: v for k, v in (params or {}).items() if v is not None}

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}{path}",
            headers={"Authorization": DEVELOPER_TOKEN},
            params=query,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body = await resp.json()

    if not body.get("success"):
        raise LxnsDevError(f"查询失败: {body.get('message', resp.status)}")
    return body.get("data")


async def get_player(friend_code: str) -> dict:
    """GET /player/{friend_code} — 获取玩家信息"""
    return await _get(f"/player/{friend_code}")


async def get_best(
    friend_code: str,
    *,
    song_id: int | None = None,
    song_name: str | None = None,
    level_index: int | None = None,
    song_type: str | None = None,
) -> dict:
    """GET /player/{friend_code}/best — 获取玩家缓存谱面的最佳成绩"""
    return await _get(
        f"/player/{friend_code}/best",
        {
            "song_id": song_id,
            "song_name": song_name,
            "level_index": level_index,
            "song_type": song_type,
        },
    )


async def get_bests(friend_code: str) -> dict:
    """GET /player/{friend_code}/bests — Best 50（不带 song 参数时的整体聚合）"""
    return await _get(f"/player/{friend_code}/bests")


async def get_bests_ap(friend_code: str) -> dict:
    """GET /player/{friend_code}/bests/ap — All Perfect 50，结构同 Best 50"""
    return await _get(f"/player/{friend_code}/bests/ap")


async def get_song_scores(
    friend_code: str,
    *,
    song_id: int | None = None,
    song_name: str | None = None,
    song_type: str | None = None,
) -> list:
    """GET /player/{friend_code}/bests?song_id=... — 带 song 参数时返回该曲目
    所有谱面的成绩列表（跟上面 get_bests 是同一个 URL，靠有没有带
    song_id/song_name 区分是聚合结果还是单曲列表，见官方文档）"""
    return await _get(
        f"/player/{friend_code}/bests",
        {"song_id": song_id, "song_name": song_name, "song_type": song_type},
    )


async def get_recents(friend_code: str) -> list:
    """GET /player/{friend_code}/recents — Recent 50（仅增量爬取可用）"""
    return await _get(f"/player/{friend_code}/recents")


async def get_scores(friend_code: str) -> list:
    """GET /player/{friend_code}/scores — 所有最佳成绩（简化）"""
    return await _get(f"/player/{friend_code}/scores")


async def get_heatmap(friend_code: str) -> dict:
    """GET /player/{friend_code}/heatmap — 成绩上传热力图，日期 -> 数量"""
    return await _get(f"/player/{friend_code}/heatmap")


async def get_trend(friend_code: str, *, version: int | None = None) -> list:
    """GET /player/{friend_code}/trend — DX Rating 趋势"""
    return await _get(f"/player/{friend_code}/trend", {"version": version})


async def get_score_history(
    friend_code: str,
    *,
    song_id: int | None = None,
    song_type: str | None = None,
    level_index: int | None = None,
) -> list:
    """GET /player/{friend_code}/score/history — 成绩游玩历史（仅含 play_time 的成绩）"""
    return await _get(
        f"/player/{friend_code}/score/history",
        {"song_id": song_id, "song_type": song_type, "level_index": level_index},
    )


async def get_collection(friend_code: str, collection_type: str, collection_id: int) -> dict:
    """GET /player/{friend_code}/{collection_type}/{collection_id} — 收藏品进度

    collection_type: trophy | icon | plate | frame
    """
    return await _get(f"/player/{friend_code}/{collection_type}/{collection_id}")
