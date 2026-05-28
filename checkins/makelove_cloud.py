"""newapi.makelove.cloud 签到 (New API 衍生版)。

⚠️ 该站对 GitHub Actions 的 Azure IP 段做了登录风控,
   GitHub IP 直接登录会被拒("用户名或密码错误,或用户已被封禁"),
   即使密码正确。
   因此本脚本走 Cookie 方案: 跳过登录,直接用浏览器抓到的 session cookie 调签到接口。

需要环境变量:
- MAKELOVE_SESSION: 浏览器登录后的 session cookie 值(不包含 "session=")
- MAKELOVE_USER_ID: 用户 id (登录后任意 API 响应里的 data.id,本账号是 952)

获取方法:
1. 浏览器登录 https://newapi.makelove.cloud
2. F12 → Application → Cookies → https://newapi.makelove.cloud
   → 复制 "session" 的 Value → 设到 MAKELOVE_SESSION
3. F12 → Network → 任意 /api/user/* 请求 → Request Headers
   → 找 "New-Api-User" 的值 → 设到 MAKELOVE_USER_ID

cookie 有效期 30 天,过期了需要重新登录浏览器再复制一次。

接口侦察记录:
- 鉴权: session Cookie + New-Api-User: <id> header 双因子,缺一不可
- 签到: POST /api/user/checkin
    成功: {"success":true,"message":"...","data":{...}}
    已签: {"success":false,"message":"今日已签到"}
- 用户信息: GET /api/user/self → data.quota,余额 ≈ quota / 500000 USD
"""
from __future__ import annotations

import requests

from checkins.base import CheckinTask, CheckinResult


BASE = "https://newapi.makelove.cloud"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
QUOTA_PER_USD = 500000  # New API 默认换算


class MakeloveCloudTask(CheckinTask):
    name = "makelove.cloud"
    required_env = ["MAKELOVE_SESSION", "MAKELOVE_USER_ID"]

    def check_in(self) -> CheckinResult:
        session = requests.Session()
        session.headers.update({
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": BASE,
            "Referer": f"{BASE}/console/personal",
            "New-Api-User": self.env["MAKELOVE_USER_ID"],
        })
        session.cookies.set("session", self.env["MAKELOVE_SESSION"],
                            domain="newapi.makelove.cloud", path="/")

        # 1) 签到
        ci_resp = session.post(f"{BASE}/api/user/checkin", timeout=20)
        if ci_resp.status_code != 200:
            return CheckinResult(self.name, success=False,
                                 message=f"签到请求失败 HTTP {ci_resp.status_code}: {ci_resp.text[:200]}")
        try:
            ci_data = ci_resp.json()
        except ValueError:
            return CheckinResult(self.name, success=False,
                                 message=f"响应非 JSON: {ci_resp.text[:200]}")
        ci_msg = ci_data.get("message", "")
        ci_ok = ci_data.get("success", False)

        # cookie 失效的典型特征
        if "Unauthorized" in ci_msg or "请先登录" in ci_msg or ci_resp.status_code == 401:
            return CheckinResult(self.name, success=False,
                                 message=f"Cookie 已失效,请更新 MAKELOVE_SESSION ({ci_msg})")

        # 2) 查余额
        balance_text = ""
        try:
            self_resp = session.get(f"{BASE}/api/user/self", timeout=20)
            if self_resp.status_code == 200:
                data = self_resp.json().get("data", {})
                if data:
                    quota = data.get("quota", 0)
                    balance_text = f", 余额 ${quota / QUOTA_PER_USD:.2f}"
        except Exception:
            pass

        if ci_ok or "已签" in ci_msg:
            return CheckinResult(self.name, success=True,
                                 message=f"{ci_msg or '签到成功'}{balance_text}")
        return CheckinResult(self.name, success=False,
                             message=f"{ci_msg or '签到失败'}{balance_text}")
