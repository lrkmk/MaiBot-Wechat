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

如果想让**别的用户也用上这个 bot**，因为每个账号要各自绑定，所以做法是：起一个网页，每个访客各自点一下按钮，各自拿到自己的二维码，各自扫码绑定各自的账号——服务端给每个账号单独跑一个隔离的 `WeChatBot` 实例。

```bash
pip install -r requirements.txt
python web_multi.py
```

打开 `http://localhost:8080`，点"开始登录"，扫码；扫完之后可以在自己微信的 ClawBot 窗口里发 `/help` 试试。刷新页面/换个浏览器再点一次，就是另一个独立的账号绑定流程。

**持久化**：登录成功后，凭证按微信账号自己的 iLink id 存成 `.sessions/{account_id}.json`（不是按浏览器 session 存）。服务重启时会自动扫这个目录，把每个已绑定账号重新连接上，不用再扫码。轮询用的 `login_id` 只是一个内存里的临时句柄，用来在还没登录成功前让浏览器查询"我这次扫码扫到哪一步了"，登录成功后就丢弃，不参与任何持久化。

`.sessions/` 目录是这个 demo 自己攒的每账号凭证缓存，纯本地演示用，不要提交到 git（已在 `.gitignore` 里）。

### 拆开部署：前端 Cloudflare Pages + 后端常驻服务器

`web_multi.py` 是个跑长轮询的常驻 Python 进程（每个绑定账号一个 `bot.start()` 循环），Cloudflare Pages/Workers 这种"请求进来才执行"的模型跑不了它，所以要拆成两半：

1. **后端** `web_multi.py` 部署到能跑常驻进程的地方（VPS、Fly.io、Railway 等）：
   - 用环境变量配置：`PORT`（监听端口，很多 PaaS 会自动注入）、`ALLOWED_ORIGIN`（设成你 Pages 站点的完整 origin，比如 `https://your-project.pages.dev`；本地开发不设就默认 `*`）
   - `.sessions/` 目录要挂载持久卷，否则每次重新部署凭证就没了，参见前面「持久化」那段
2. **前端** `static/` 整个目录部署到 Cloudflare Pages（构建输出目录直接指向 `static`，不用挪文件），比如：
   ```bash
   npx wrangler pages deploy static --project-name=your-project
   ```
3. 把 `static/index.html` 里的 `const API_BASE = "";` 改成后端的完整 URL，比如 `const API_BASE = "https://your-backend.example.com";`，重新部署 Pages。

## 已支持命令（两个 demo 共用，见 `commands.py`）

- `/help` — 列出所有命令
- `/echo <文本>` — 原样返回文本
- `/time` — 返回当前时间
- `/status` — 返回运行状态
- `/mai bind <15位好友码>` — 绑定 maimai 好友码（必须是 15 位纯数字），存到服务端

## 持久化的用户数据（好友码等）

`/mai bind` 这类"存点用户信息"的命令，数据存在 `data/bindings.json`，key 是 `msg.user_id`——也就是微信账号自己的稳定 id，不是 `web_multi.py` 里那个只在扫码阶段临时存在的 `login_id`（参见前面「持久化」那段）。所以不管重启多少次、也不管是单用户 `bot.py` 还是多用户 `web_multi.py`，同一个微信账号发的 `/mai bind` 记录都不会丢。

`data/` 目录存的是真实用户信息，不要提交到 git（已在 `.gitignore` 里）。

## 扩展新命令

**普通命令**（不分游戏）：在 `commands.py` 的 `COMMANDS` 字典里加一项 `"名字": handler`，`handler` 是 `async def handler(bot, msg, args)`，`args` 是命令名后面的剩余文本。

**游戏命令**（`/<game> <子命令> ...` 这种，为以后接入更多游戏的查询功能准备的）：用 `@game_command("游戏代号", "子命令")` 装饰一个 `async def handler(bot, msg, arg)`，比如加一个 `/mai query`：

```python
@game_command("mai", "query")
async def mai_query(bot, msg, arg):
    code = await get_binding(msg.user_id, "mai")
    if code is None:
        await bot.reply(msg, "还没绑定，先发 /mai bind <15位好友码>")
        return
    ...
```

两个 demo 都会自动拿到新命令。
