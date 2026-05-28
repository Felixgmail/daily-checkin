"""newapi.makelove.cloud 签到 (New API 衍生版)。

需要环境变量:
- MAKELOVE_USERNAME: 登录用户名
- MAKELOVE_PASSWORD: 登录密码

接口侦察记录:
- 登录: POST /api/user/login {"username","password"} → 设置 session cookie,响应 data.id 是用户 id
- 鉴权: 后续请求需带 Cookie: session=... 和 New-Api-User: <id> 两个头
- 签到: POST /api/user/checkin
    成功: {"success":true,"message":"...","data":{...}}
    已签: {"success":false,"message":"今日已签到"}
- 用户信息: GET /api/user/self → quota 字段是配额 (quota/500000 ≈ USD)
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
    required_env = ["MAKELOVE_USERNAME", "MAKELOVE_PASSWORD"]

    def check_in(self) -> CheckinResult:
        session = requests.Session()
        session.headers.update({
            "User-Agent": UA,
            "Origin": BASE,
            "Referer": f"{BASE}/login",
        })

        # 1) 登录
        login_resp = session.post(
            f"{BASE}/api/user/login",
            json={
                "username": self.env["MAKELOVE_USERNAME"],
                "password": self.env["MAKELOVE_PASSWORD"],
            },
            timeout=20,
        )
        if login_resp.status_code != 200:
            return CheckinResult(self.name, success=False,
                                 message=f"登录失败 HTTP {login_resp.status_code}")
        login_data = login_resp.json()
        if not login_data.get("success"):
            return CheckinResult(self.name, success=False,
                                 message=f"登录失败: {login_data.get('message', '未知错误')}")
        user_id = login_data["data"]["id"]

        # 2) 签到 (需要 New-Api-User header)
        session.headers["New-Api-User"] = str(user_id)
        session.headers["Referer"] = f"{BASE}/console/personal"
        ci_resp = session.post(f"{BASE}/api/user/checkin", timeout=20)
        if ci_resp.status_code != 200:
            return CheckinResult(self.name, success=False,
                                 message=f"签到请求失败 HTTP {ci_resp.status_code}")
        ci_data = ci_resp.json()
        ci_msg = ci_data.get("message", "")
        ci_ok = ci_data.get("success", False)

        # 3) 查余额 (无论签到成功与否都查一下,展示给用户)
        balance_text = ""
        try:
            self_resp = session.get(f"{BASE}/api/user/self", timeout=20)
            if self_resp.status_code == 200:
                quota = self_resp.json().get("data", {}).get("quota", 0)
                balance_text = f", 余额 ${quota / QUOTA_PER_USD:.2f}"
        except Exception:
            pass

        # "今日已签到" 也算成功的常见结果
        if ci_ok or "已签" in ci_msg:
            return CheckinResult(self.name, success=True,
                                 message=f"{ci_msg or '签到成功'}{balance_text}")
        return CheckinResult(self.name, success=False,
                             message=f"{ci_msg or '签到失败'}{balance_text}")
