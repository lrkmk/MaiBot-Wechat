"""Command handlers shared by the single-user and multi-user demos."""

import re
from datetime import datetime

from lxns_client import LxnsError, get_player
from lxns_dev_client import LxnsDevError
from lxns_dev_client import get_bests as dev_get_bests
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


@game_command("mai", "b50")
async def mai_b50(bot, msg, arg):
    """Best 50 via the developer API (friend_code from /mai bind) — no
    OAuth token needed, works for anyone who's enabled 允许第三方访问."""
    friend_code = await get_binding(msg.user_id, "mai")
    if friend_code is None:
        await bot.reply(msg, "还没绑定好友码，先发 /mai bind <15位好友码>")
        return

    try:
        bests = await dev_get_bests(friend_code)
    except LxnsDevError as e:
        await bot.reply(msg, str(e))
        return
    except Exception as e:
        await bot.reply(msg, f"查询出错: {e}")
        return

    standard_total = bests.get("standard_total", 0)
    dx_total = bests.get("dx_total", 0)
    top_songs = sorted(
        bests.get("standard", []) + bests.get("dx", []),
        key=lambda s: s.get("dx_rating", 0),
        reverse=True,
    )[:5]

    lines = [f"Rating: {standard_total + dx_total} (旧{standard_total} + 新{dx_total})", ""]
    for s in top_songs:
        lines.append(
            f"{s.get('song_name', '?')} [{s.get('level', '?')}] "
            f"{s.get('achievements', '?')}% -> {s.get('dx_rating', '?')}"
        )
    await bot.reply(msg, "\n".join(lines))


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
