/**
 * Cloudflare Worker — OAuth 回调处理
 *
 * 流程:
 * 1. 接收 OAuth provider 回调的 ?code=xxx&state=xxx
 * 2. 用 code 向 provider 换取 access_token
 * 3. 把 token 转发给你自己的服务器保存
 * 4. 重定向用户到前端成功页
 *
 * 部署方式:
 *   wrangler deploy
 *
 * 需要在 wrangler.toml 或 Cloudflare Dashboard 里配置以下环境变量 / Secrets:
 *   OAUTH_TOKEN_URL      - OAuth provider 换取token的接口地址
 *   OAUTH_CLIENT_ID      - 你的client_id
 *   OAUTH_CLIENT_SECRET  - 你的client_secret (务必用 wrangler secret put 设置,不要明文写 toml)
 *   OAUTH_REDIRECT_URI   - 这个worker本身的回调地址,要和OAuth provider后台注册的一致
 *   BACKEND_SAVE_URL     - 你自己服务器接收token的接口地址
 *   BACKEND_SECRET       - Worker和你服务器之间的共享密钥,用于校验请求来源
 *   FRONTEND_SUCCESS_URL - 处理完成后重定向到的前端页面
 *   FRONTEND_ERROR_URL   - 出错时重定向到的前端页面
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname !== "/callback") {
      return new Response("Not found", { status: 404 });
    }

    const code = url.searchParams.get("code");
    const state = url.searchParams.get("state");
    const errorParam = url.searchParams.get("error");

    // OAuth provider 直接返回了错误(比如用户拒绝授权)
    if (errorParam) {
      return Response.redirect(
        `${env.FRONTEND_ERROR_URL}?error=${encodeURIComponent(errorParam)}`,
        302
      );
    }

    if (!code) {
      return new Response("Missing code parameter", { status: 400 });
    }

    // 有意跳过 state 校验：授权链接是 lxns.net 给的固定地址，跳转前那一步
    // 不在这个 Worker 里发起，没有地方存"当初发的 state 是什么"，所以校验
    // 无从对比。风险是 OAuth CSRF（见此前讨论）——如果以后要补，需要在
    // 发起授权跳转的地方（前端）先生成随机 state 存进 KV/Cookie，再拼到
    // 授权链接的 &state= 上，这里再读回来比对。

    try {
      // 1. 用 code 换 access_token
      const tokenRes = await fetch(env.OAUTH_TOKEN_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          Accept: "application/json",
        },
        body: new URLSearchParams({
          grant_type: "authorization_code",
          code,
          client_id: env.OAUTH_CLIENT_ID,
          client_secret: env.OAUTH_CLIENT_SECRET,
          redirect_uri: env.OAUTH_REDIRECT_URI,
        }),
      });

      if (!tokenRes.ok) {
        const errText = await tokenRes.text();
        console.error("Token exchange failed:", tokenRes.status, errText);
        return Response.redirect(
          `${env.FRONTEND_ERROR_URL}?error=token_exchange_failed`,
          302
        );
      }

      const tokenData = await tokenRes.json();
      // tokenData 一般形如:
      // { access_token, refresh_token, expires_in, token_type, scope, ... }

      // 2. 转发给自己的服务器保存
      //    用共享密钥签名/认证这次请求,避免别人直接伪造请求打你的save接口
      const saveRes = await fetch(env.BACKEND_SAVE_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${env.BACKEND_SECRET}`,
        },
        body: JSON.stringify({
          ...tokenData,
          state, // 如果 state 里编码了你自己的 userId/session,一并传给后端用于关联账号
          received_at: new Date().toISOString(),
        }),
      });

      if (!saveRes.ok) {
        const errText = await saveRes.text();
        console.error("Backend save failed:", saveRes.status, errText);
        return Response.redirect(
          `${env.FRONTEND_ERROR_URL}?error=backend_save_failed`,
          302
        );
      }

      // 3. 成功,跳回前端
      return Response.redirect(env.FRONTEND_SUCCESS_URL, 302);
    } catch (err) {
      console.error("Callback handling error:", err);
      return Response.redirect(
        `${env.FRONTEND_ERROR_URL}?error=internal_error`,
        302
      );
    }
  },
};
