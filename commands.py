"""Command handlers shared by the single-user and multi-user demos."""

import re
from datetime import datetime

import lxns_dev_client as dev
from b50_image import render_b50_image
from lxns_client import LxnsError, get_player
from lxns_dev_client import LxnsDevError
from storage import get_binding, set_binding

# ── flat utility commands: /help, /echo, ... ────────────────────────────

COMMANDS = {}


async def cmd_help(bot, msg, args):
    lines = ["可用命令："]
    lines += [f"/{name}" for name in sorted(COMMANDS)]
    lines += [f"/{game} {sub}" for game in sorted(GAMES) for sub in sorted(GAMES[game])]
    await bot.reply(msg, "\n".join(lines))


async def cmd_echo(bot, msg, args):
    await bot.reply(msg, args if args else "用法: /echo <文本>")


async def cmd_time(bot, msg, args):
    await bot.reply(msg, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


async def cmd_status(bot, msg, args):
    await bot.reply(msg, "运行中 ✅")


COMMANDS.update(help=cmd_help, echo=cmd_echo, time=cmd_time, status=cmd_status)


# ── per-game commands: /mai bind, /mai <sub>, ... ───────────────────────
# Namespaced so more games can be added later without touching dispatch().

GAMES: dict[str, dict] = {}


def game_command(game: str, sub: str):
    """Register handler(bot, msg, arg) as `/<game> <sub> <arg>`."""

    def decorator(func):
        GAMES.setdefault(game, {})[sub] = func
        return func

    return decorator


FRIEND_CODE_RE = re.compile(r"^\d{15}$")


@game_command("mai", "bind")
async def mai_bind(bot, msg, arg):
    if not FRIEND_CODE_RE.match(arg):
        await bot.reply(msg, "好友码必须是 15 位纯数字，用法：/mai bind <15位好友码>")
        return
    await set_binding(msg.user_id, "mai", arg)
    await bot.reply(msg, f"已绑定 maimai 好友码：{arg}")


@game_command("mai", "info")
async def mai_info(bot, msg, arg):
    try:
        player = await get_player(msg.user_id)
    except LxnsError as e:
        await bot.reply(msg, str(e))
        return
    except Exception as e:
        await bot.reply(msg, f"查询出错: {e}")
        return

    lines = [
        f"昵称: {player.get('name', '?')}",
        f"Rating: {player.get('rating', '?')}",
    ]
    await bot.reply(msg, "\n".join(lines))


async def resolve_friend_code(user_id: str) -> str | None:
    """/mai bind's stored code, or — if the user's done OAuth instead —
    derive it from their Player data (which already includes friend_code)
    and cache it so future calls skip the OAuth round-trip entirely."""
    friend_code = await get_binding(user_id, "mai")
    if friend_code:
        return friend_code

    try:
        player = await get_player(user_id)
    except Exception:
        return None

    friend_code = str(player.get("friend_code", "")).strip()
    if not FRIEND_CODE_RE.match(friend_code):
        return None

    await set_binding(user_id, "mai", friend_code)
    return friend_code


async def _require_friend_code(bot, msg) -> str | None:
    friend_code = await resolve_friend_code(msg.user_id)
    if friend_code is None:
        await bot.reply(
            msg,
            "还没绑定好友码——发 /mai bind <15位好友码>，"
            '或者在网页上点"绑定 maimai 查分账号"完成授权也行',
        )
    return friend_code


def _format_bests_block(bests: dict, rating: int | str = "?") -> str:
    standard_total = bests.get("standard_total", 0)
    dx_total = bests.get("dx_total", 0)
    top_songs = sorted(
        bests.get("standard", []) + bests.get("dx", []),
        key=lambda s: s.get("dx_rating", 0),
        reverse=True,
    )[:5]

    lines = [
        f"Rating: {rating}",
        f"(Best 缓存合计 旧{standard_total} + 新{dx_total} = {standard_total + dx_total}，"
        "不含 Selection，跟官方 Rating 可能对不上)",
        "",
    ]
    for s in top_songs:
        lines.append(
            f"{s.get('song_name', '?')} [{s.get('level', '?')}] "
            f"{s.get('achievements', '?')}% -> {s.get('dx_rating', '?')}"
        )
    return "\n".join(lines)


@game_command("mai", "b50")
async def mai_b50(bot, msg, arg):
    """Best 50 — Rating 取权威的 Player.rating，Best35/15 只当明细展示。"""
    friend_code = await _require_friend_code(bot, msg)
    if friend_code is None:
        return

    try:
        player = await dev.get_player(friend_code)
        bests = await dev.get_bests(friend_code)
    except LxnsDevError as e:
        await bot.reply(msg, str(e))
        return
    except Exception as e:
        await bot.reply(msg, f"查询出错: {e}")
        return

    await bot.reply(msg, _format_bests_block(bests, player.get("rating", "?")))


@game_command("mai", "b50img")
async def mai_b50img(bot, msg, arg):
    """Best 50 图片版 — 渲染 https://github.com/MeowKJ/maimai-rating-web 的
    页面截图，数据来自我们自己已经在查的开发者API，不让那边页面自己请求。"""
    friend_code = await _require_friend_code(bot, msg)
    if friend_code is None:
        return

    try:
        image_bytes = await render_b50_image(friend_code)
    except LxnsDevError as e:
        await bot.reply(msg, str(e))
        return
    except Exception as e:
        await bot.reply(msg, f"生成图片出错: {e}")
        return

    await bot.reply_media(msg, {"image": image_bytes})


@game_command("mai", "apbest")
async def mai_apbest(bot, msg, arg):
    """All Perfect 50 — 结构同 Best 50。"""
    friend_code = await _require_friend_code(bot, msg)
    if friend_code is None:
        return

    try:
        bests = await dev.get_bests_ap(friend_code)
    except LxnsDevError as e:
        await bot.reply(msg, str(e))
        return
    except Exception as e:
        await bot.reply(msg, f"查询出错: {e}")
        return

    await bot.reply(msg, _format_bests_block(bests))


@game_command("mai", "best")
async def mai_best(bot, msg, arg):
    """单个谱面的最佳成绩：/mai best <曲名> <难度0-4，缺省则不限>"""
    friend_code = await _require_friend_code(bot, msg)
    if friend_code is None:
        return
    if not arg:
        await bot.reply(msg, "用法：/mai best <曲名> [难度0-4]")
        return

    song_name, _, level_str = arg.rpartition(" ")
    level_index = None
    if level_str.isdigit() and 0 <= int(level_str) <= 4:
        level_index = int(level_str)
    else:
        song_name = arg  # 没带难度，整段都是曲名

    try:
        score = await dev.get_best(friend_code, song_name=song_name, level_index=level_index)
    except LxnsDevError as e:
        await bot.reply(msg, str(e))
        return
    except Exception as e:
        await bot.reply(msg, f"查询出错: {e}")
        return

    await bot.reply(
        msg,
        f"{score.get('song_name', '?')} [{score.get('level', '?')}] "
        f"{score.get('achievements', '?')}% {score.get('rate', '')} "
        f"DX Rating: {score.get('dx_rating', '?')}",
    )


@game_command("mai", "song")
async def mai_song(bot, msg, arg):
    """一首曲目所有谱面的成绩：/mai song <曲名>"""
    friend_code = await _require_friend_code(bot, msg)
    if friend_code is None:
        return
    if not arg:
        await bot.reply(msg, "用法：/mai song <曲名>")
        return

    try:
        scores = await dev.get_song_scores(friend_code, song_name=arg)
    except LxnsDevError as e:
        await bot.reply(msg, str(e))
        return
    except Exception as e:
        await bot.reply(msg, f"查询出错: {e}")
        return

    if not scores:
        await bot.reply(msg, "没查到这首曲目的成绩")
        return

    lines = [scores[0].get("song_name", arg)]
    for s in scores:
        lines.append(
            f"[{s.get('level', '?')}] {s.get('achievements', '?')}% "
            f"{s.get('fc') or ''} {s.get('rate', '')}"
        )
    await bot.reply(msg, "\n".join(lines))


@game_command("mai", "recent")
async def mai_recent(bot, msg, arg):
    """Recent 50（仅增量爬取可用）"""
    friend_code = await _require_friend_code(bot, msg)
    if friend_code is None:
        return

    try:
        scores = await dev.get_recents(friend_code)
    except LxnsDevError as e:
        await bot.reply(msg, str(e))
        return
    except Exception as e:
        await bot.reply(msg, f"查询出错: {e}")
        return

    if not scores:
        await bot.reply(msg, "没查到最近游玩记录（这个接口仅增量爬取时可用）")
        return

    lines = []
    for s in scores[:10]:
        lines.append(
            f"{s.get('play_time', '?')} {s.get('song_name', '?')} "
            f"[{s.get('level', '?')}] {s.get('achievements', '?')}%"
        )
    await bot.reply(msg, "\n".join(lines))


@game_command("mai", "scores")
async def mai_scores(bot, msg, arg):
    """所有最佳成绩（简化），条数太多只汇总。"""
    friend_code = await _require_friend_code(bot, msg)
    if friend_code is None:
        return

    try:
        scores = await dev.get_scores(friend_code)
    except LxnsDevError as e:
        await bot.reply(msg, str(e))
        return
    except Exception as e:
        await bot.reply(msg, f"查询出错: {e}")
        return

    rate_counts: dict[str, int] = {}
    for s in scores:
        rate = s.get("rate", "?")
        rate_counts[rate] = rate_counts.get(rate, 0) + 1

    lines = [f"共 {len(scores)} 条成绩记录"]
    for rate, count in sorted(rate_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"{rate}: {count}")
    await bot.reply(msg, "\n".join(lines))


@game_command("mai", "heatmap")
async def mai_heatmap(bot, msg, arg):
    """成绩上传热力图汇总（总数 + 最近有记录的日期）"""
    friend_code = await _require_friend_code(bot, msg)
    if friend_code is None:
        return

    try:
        heatmap = await dev.get_heatmap(friend_code)
    except LxnsDevError as e:
        await bot.reply(msg, str(e))
        return
    except Exception as e:
        await bot.reply(msg, f"查询出错: {e}")
        return

    if not heatmap:
        await bot.reply(msg, "没有上传记录")
        return

    total = sum(heatmap.values())
    recent_days = sorted(heatmap.items(), reverse=True)[:7]
    lines = [f"累计上传 {total} 条", "最近 7 天有记录的日期："]
    lines += [f"{date}: {count}" for date, count in recent_days]
    await bot.reply(msg, "\n".join(lines))


@game_command("mai", "trend")
async def mai_trend(bot, msg, arg):
    """DX Rating 趋势：/mai trend [游戏版本号，缺省用默认版本]"""
    friend_code = await _require_friend_code(bot, msg)
    if friend_code is None:
        return

    version = int(arg) if arg.isdigit() else None

    try:
        trend = await dev.get_trend(friend_code, version=version)
    except LxnsDevError as e:
        await bot.reply(msg, str(e))
        return
    except Exception as e:
        await bot.reply(msg, f"查询出错: {e}")
        return

    if not trend:
        await bot.reply(msg, "没有趋势数据")
        return

    lines = [f"{p.get('date', '?')}: {p.get('total', '?')} (旧{p.get('standard', '?')}+新{p.get('dx', '?')})" for p in trend[-10:]]
    await bot.reply(msg, "\n".join(lines))


@game_command("mai", "history")
async def mai_history(bot, msg, arg):
    """成绩游玩历史：/mai history <曲目ID>（lxns 这个接口按 song_id 查，不支持曲名）"""
    friend_code = await _require_friend_code(bot, msg)
    if friend_code is None:
        return
    if not arg.isdigit():
        await bot.reply(msg, "用法：/mai history <曲目ID>（数字，这个接口不支持按曲名查）")
        return

    try:
        history = await dev.get_score_history(friend_code, song_id=int(arg))
    except LxnsDevError as e:
        await bot.reply(msg, str(e))
        return
    except Exception as e:
        await bot.reply(msg, f"查询出错: {e}")
        return

    if not history:
        await bot.reply(msg, "没查到这首曲目的游玩历史")
        return

    lines = [f"{s.get('play_time', '?')} [{s.get('level', '?')}] {s.get('achievements', '?')}%" for s in history[:15]]
    await bot.reply(msg, "\n".join(lines))


@game_command("mai", "collection")
async def mai_collection(bot, msg, arg):
    """收藏品进度：/mai collection <trophy|icon|plate|frame> <收藏品ID>"""
    friend_code = await _require_friend_code(bot, msg)
    if friend_code is None:
        return

    collection_type, _, collection_id_str = arg.partition(" ")
    if collection_type not in ("trophy", "icon", "plate", "frame") or not collection_id_str.strip().isdigit():
        await bot.reply(msg, "用法：/mai collection <trophy|icon|plate|frame> <收藏品ID>")
        return

    try:
        collection = await dev.get_collection(friend_code, collection_type, int(collection_id_str.strip()))
    except LxnsDevError as e:
        await bot.reply(msg, str(e))
        return
    except Exception as e:
        await bot.reply(msg, f"查询出错: {e}")
        return

    await bot.reply(msg, f"{collection.get('name', '?')}\n{collection.get('description', '') or '(无说明)'}")


# ── dispatch ─────────────────────────────────────────────────────────

async def dispatch(bot, msg):
    """Route an incoming message to the matching /command or /<game> <sub> handler."""
    text = msg.text.strip()

    if not text.startswith("/"):
        await bot.reply(msg, "输入 /help 查看可用命令")
        return

    name, _, rest = text[1:].partition(" ")
    await bot.send_typing(msg.user_id)

    if name in GAMES:
        sub, _, arg = rest.strip().partition(" ")
        handler = GAMES[name].get(sub)
        if handler is None:
            usage = "\n".join(f"/{name} {s}" for s in sorted(GAMES[name]))
            await bot.reply(msg, f"用法：\n{usage}")
            return
        await handler(bot, msg, arg.strip())
        return

    handler = COMMANDS.get(name)
    if handler is None:
        await bot.reply(msg, f"未知命令: /{name}\n输入 /help 查看可用命令")
        return

    await handler(bot, msg, rest.strip())
