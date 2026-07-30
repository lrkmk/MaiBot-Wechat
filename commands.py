"""Command handlers shared by the single-user and multi-user demos."""

from datetime import datetime


async def cmd_help(bot, msg, args):
    lines = ["可用命令："] + [f"/{name}" for name in sorted(COMMANDS)]
    await bot.reply(msg, "\n".join(lines))


async def cmd_echo(bot, msg, args):
    await bot.reply(msg, args if args else "用法: /echo <文本>")


async def cmd_time(bot, msg, args):
    await bot.reply(msg, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


async def cmd_status(bot, msg, args):
    await bot.reply(msg, "运行中 ✅")


COMMANDS = {
    "help": cmd_help,
    "echo": cmd_echo,
    "time": cmd_time,
    "status": cmd_status,
}


async def dispatch(bot, msg):
    """Route an incoming message to the matching /command handler."""
    text = msg.text.strip()

    if not text.startswith("/"):
        await bot.reply(msg, "输入 /help 查看可用命令")
        return

    name, _, args = text[1:].partition(" ")
    handler = COMMANDS.get(name)

    if handler is None:
        await bot.reply(msg, f"未知命令: /{name}\n输入 /help 查看可用命令")
        return

    await bot.send_typing(msg.user_id)
    await handler(bot, msg, args.strip())
