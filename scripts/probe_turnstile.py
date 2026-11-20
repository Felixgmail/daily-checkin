"""临时探针: 在 GitHub Actions runner 上验证 dialoguedui 新版签到风控。

不消耗 refresh_token,只用存量 access_token。
不打印任何 token 明文。
跑完确认后请删除本文件及 .github/workflows/probe_turnstile.yml。
"""
from __future__ import annotations

import json
import os
import time

from playwright.sync_api import sync_playwright

BASE = "https://token.dialoguedui.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

def main() -> None:
    at = os.environ.get("DDU_ACCESS_TOKEN", "").strip()
    exp = os.environ.get("DDU_ACCESS_EXP", "").strip()
    print(f"access_token present: {bool(at)}, len={len(at)}")
    try:
        left = int(float(exp)) - int(time.time())
        print(f"access_token 剩余有效期: {left} 秒")
    except ValueError:
        print("ACCESS_EXP 无法解析")
    if not at:
        print("无 access_token,跳过")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, locale="zh-CN",
                                  viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        failed = []
        page.on("requestfailed", lambda r: failed.append((r.url[:110], str(r.failure)[:80])))

        page.goto(f"{BASE}/checkin/", wait_until="domcontentloaded", timeout=60000)
        # 注入登录态(前端 getAuthToken 从 localStorage 读)
        page.evaluate("t => localStorage.setItem('token', t)", at)
        page.reload(wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)

        status = page.evaluate("""async () => {
            const t = localStorage.getItem('token') || '';
            const r = await fetch('./api/status', {headers:{Authorization:'Bearer '+t}});
            let d={}; try{d=await r.json();}catch(e){}
            return {status:r.status, data:d};
        }""")
        print("status HTTP:", status["status"])
        data = (status["data"] or {}).get("data") or {}
        ver = data.get("verification") or {}
        print("status.data keys:", list(data.keys()))
        print("signedToday:", data.get("signedToday"))
        print("verification:", {
            "configured": ver.get("configured"),
            "siteKeyLen": len(ver.get("siteKey") or ""),
            "cDataLen": len(ver.get("cData") or ""),
            "action": ver.get("action"),
        })

        obs = page.evaluate("""() => ({
            turnstileLoaded: !!window.turnstile,
            panelHidden: document.querySelector('#verification-panel')?.hidden,
            statusText: document.querySelector('#verification-status')?.textContent,
            btnDisabled: document.querySelector('#checkin-button')?.disabled,
            hiddenTokenLen: (document.querySelector("input[name='cf-turnstile-response']")?.value||'').length,
            iframes: [...document.querySelectorAll('iframe')].map(f=>f.src.slice(0,100)),
        })""")
        print("observation:", json.dumps(obs, ensure_ascii=False))
        print("failed requests:", failed[-8:])

        # 若 Turnstile 自动签发了 token,尝试签到
        tt = page.evaluate(
            "() => document.querySelector(\"input[name='cf-turnstile-response']\")?.value || ''")
        if tt and not data.get("signedToday"):
            claim = page.evaluate("""async (tt) => {
                const t = localStorage.getItem('token') || '';
                const r = await fetch('./api/checkin', {
                    method:'POST',
                    headers:{'Content-Type':'application/json', Authorization:'Bearer '+t},
                    body: JSON.stringify({turnstileToken: tt}),
                });
                let d={}; try{d=await r.json();}catch(e){}
                return {status:r.status, body:d};
            }""", tt)
            print("claim result:", json.dumps(claim, ensure_ascii=False)[:500])
        else:
            print(f"未尝试签到 (turnstileToken len={len(tt)}, signedToday={data.get('signedToday')})")

        browser.close()

if __name__ == "__main__":
    main()
