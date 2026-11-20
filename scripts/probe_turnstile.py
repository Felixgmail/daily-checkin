"""临时探针: 用 Chromium --host-resolver-rules 修复 Turnstile 挑战域名 IPv6-only DNS。

不消耗 refresh_token,只用存量 access_token。不打印任何 token 明文。
验证后删除本文件及 .github/workflows/probe_turnstile.yml。
"""
from __future__ import annotations

import json
import os
import time

from playwright.sync_api import sync_playwright

BASE = "https://token.dialoguedui.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# brunhild.challenges.cloudflare.com 只有 AAAA 记录, runner 无 IPv6 出口。
# challenges.cloudflare.com 的 IPv4(104.18.94.41 / 104.18.95.41) 属同一 CDN,
# 用 Chromium 的 host-resolver-rules 通配映射, TLS SNI/Host 头仍是原子域。
RULES = "MAP *.challenges.cloudflare.com 104.18.95.41, MAP challenges.cloudflare.com 104.18.95.41"


def run_once(p, label: str, launch_args: list[str]) -> dict:
    browser = p.chromium.launch(headless=True, args=launch_args)
    ctx = browser.new_context(user_agent=UA, locale="zh-CN",
                              viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    failed = []
    console = []
    responses = []
    page.on("requestfailed", lambda r: failed.append((r.url[:110], str(r.failure)[:80])))
    page.on("console", lambda m: console.append((m.type, m.text[:160])))
    page.on("response", lambda r: responses.append((r.status, r.url[:120]))
            if "challenge" in r.url or "turnstile" in r.url else None)

    at = os.environ.get("DDU_ACCESS_TOKEN", "").strip()
    page.goto(f"{BASE}/checkin/", wait_until="domcontentloaded", timeout=60000)
    page.evaluate("t => localStorage.setItem('token', t)", at)
    page.reload(wait_until="domcontentloaded", timeout=60000)

    # 等 Turnstile 最多 60 秒
    token_len = 0
    for _ in range(60):
        page.wait_for_timeout(1000)
        token_len = page.evaluate(
            "() => (document.querySelector(\"input[name='cf-turnstile-response']\")?.value||'').length")
        if token_len > 20:
            break

    obs = page.evaluate("""() => ({
        turnstileLoaded: !!window.turnstile,
        statusText: document.querySelector('#verification-status')?.textContent,
        btnDisabled: document.querySelector('#checkin-button')?.disabled,
        hiddenTokenLen: (document.querySelector("input[name='cf-turnstile-response']")?.value||'').length,
        iframes: [...document.querySelectorAll('iframe')].map(f=>f.src.slice(0,90)),
    })""")
    result = {"label": label, "obs": obs, "failed": failed[-6:],
              "console": console[-8:], "challenge_responses": responses[-8:]}

    # 拿到真 token 就签到
    if obs["hiddenTokenLen"] > 20:
        claim = page.evaluate("""async () => {
            const t = localStorage.getItem('token') || '';
            const tt = document.querySelector("input[name='cf-turnstile-response']")?.value || '';
            const r = await fetch('./api/checkin', {
                method:'POST',
                headers:{'Content-Type':'application/json', Authorization:'Bearer '+t},
                body: JSON.stringify({turnstileToken: tt}),
            });
            let d={}; try{d=await r.json();}catch(e){}
            return {status:r.status, body:d};
        }""")
        result["claim"] = claim
    browser.close()
    return result


def main() -> None:
    at = os.environ.get("DDU_ACCESS_TOKEN", "")
    exp = os.environ.get("DDU_ACCESS_EXP", "")
    print(f"access_token present: {bool(at)}, len={len(at)}")
    try:
        print(f"剩余有效期: {int(float(exp)) - int(time.time())} 秒")
    except ValueError:
        pass
    if not at:
        return

    with sync_playwright() as p:
        for label, args in [
            ("baseline", []),
            ("host-resolver-rules", [f"--host-resolver-rules={RULES}"]),
        ]:
            try:
                r = run_once(p, label, args)
                print(json.dumps(r, ensure_ascii=False)[:700])
            except Exception as e:
                print(f"{label} ERR: {type(e).__name__}: {str(e)[:200]}")

if __name__ == "__main__":
    main()
