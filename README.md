# wechat-command-bot

基于 [wechatbot-sdk](https://github.com/corespeed-io/wechatbot)（微信官方 ClawBot / iLink 协议）的纯命令路由 bot demo，不接任何 LLM/agent。

ClawBot 的限制是**一个微信账号同一时间只能绑定一个 bot 实例**，绑定后 bot 窗口只出现在你绑定的那个账号里——它不是"一个账号被很多陌生人当客服加好友"的模式。所以这里给了两个 demo：

## demo 1：单用户 `bot.py`

只绑定你自己扫码用的那个微信账号，只有你自己能在自己的 ClawBot 窗口里用这个 bot。

```bash
pip install -r requirements.txt
python bot.py
```

首次运行会打印二维码链接，用微信扫码登录；登录凭证会缓存到 `~/.wechatbot/credentials.json`，之后重启无需再扫码。

## demo 2：多用户 `web_multi.py`

如果想让**别的用户也用上这个 bot**，因为每个账号要各自绑定，所以做法是：起一个网页，每个访客各自点一下按钮，各自拿到自己的二维码，各自扫码绑定各自的账号——服务端给每个 session 单独跑一个隔离的 `WeChatBot` 实例（独立凭证文件，存在 `.sessions/` 下）。

```bash
pip install -r requirements.txt
python web_multi.py
```

打开 `http://localhost:8080`，点"开始登录"，扫码；扫完之后可以在自己微信的 ClawBot 窗口里发 `/help` 试试。刷新页面/换个浏览器再点一次，就是另一个独立的账号绑定流程。

`.sessions/` 目录是这个 demo 自己攒的每用户凭证缓存，纯本地演示用，不要提交到 git。

## 已支持命令（两个 demo 共用，见 `commands.py`）

- `/help` — 列出所有命令
- `/echo <文本>` — 原样返回文本
- `/time` — 返回当前时间
- `/status` — 返回运行状态

## 扩展新命令

在 `commands.py` 的 `COMMANDS` 字典里加一项 `"名字": handler`，`handler` 是 `async def handler(bot, msg, args)`，`args` 是命令名后面的剩余文本。两个 demo 都会自动拿到新命令。
