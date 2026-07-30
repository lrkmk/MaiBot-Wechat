"""Single-user command bot: binds ONE WeChat account (the one you scan with).

Run: python bot.py
Prints a QR code URL on first run; scan it with the WeChat account you want
to bind. Credentials are cached afterwards (see WeChatBot(cred_path=...)),
so later restarts don't need a re-scan.

Only the account you scanned with gets a ClawBot chat window — this demo
does not let other WeChat accounts use the bot. For that, see web_multi.py.
"""

from wechatbot import WeChatBot

from commands import dispatch

bot = WeChatBot(
    on_qr_url=lambda url: print(f"Scan to login: {url}"),
    on_scanned=lambda: print("Scanned, waiting for confirmation..."),
    on_expired=lambda: print("QR expired, restart the bot to retry."),
    on_error=lambda err: print(f"Error: {err}"),
)


@bot.on_message
async def handle(msg):
    await dispatch(bot, msg)


if __name__ == "__main__":
    bot.run()
