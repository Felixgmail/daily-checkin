"""newapi.makelove.cloud 签到 (New API 衍生版)。

⚠️ 该站对 GitHub Actions 的 Azure IP 段做了两层限制:
   1) /api/user/login 直接拒登(用户名或密码错误,即使密码对)
   2) session cookie 绑定登录 IP, 跨 IP 复用 cookie 会被拒(401 未登录)
   因此本脚本使用 New API 的 **Access Token** (不绑 IP, 不依赖 session) 鉴权,
   完美绕过 IP 风控。

需要环境变量:
- MAKELOVE_ACCESS_TOKEN: 个人 access token (不是渠道 API key,也不是 session)
- MAKELOVE_USER_ID: 用户 id (从 /api/user/self 拿,本账号是 952)

获取方法:
1. 浏览器登录 https://newapi.makelove.cloud/console/personal
2. 找到 "系统访问令牌" / "Access Token" 区域 → 复制 token (示例: mYiXtl...)
   也可在已登录会话里 GET /api/user/token 直接获得 data 字段
3. 在 GitHub Secrets 里设 MAKELOVE_ACCESS_TOKEN

接口侦察记录:
- 鉴权: Authorization: <token> + New-Api-User: <id> (Bearer 前缀可加可不加)
- 签到: POST /api/user/checkin
    成功: {"success":true,"message":"...","data":{...}}
    已签: {"success":false,"message":"今日已签到"}
- 用户信息: GET /api/user/self → data.quota,余额 ≈ quota / 500000 USD
- Access Token 不会过期(除非用户主动重置),比 cookie 方案稳得多
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
    required_env = ["MAKELOVE_ACCESS_TOKEN", "MAKELOVE_USER_ID"]

    def check_in(self) -> CheckinResult:
        session = requests.Session()
        session.headers.update({
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {self.env['MAKELOVE_ACCESS_TOKEN']}",
            "New-Api-User": self.env["MAKELOVE_USER_ID"],
        })

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

        # token 失效的典型特征
        if "无权" in ci_msg or "Unauthorized" in ci_msg or ci_resp.status_code == 401:
            return CheckinResult(self.name, success=False,
                                 message=f"Access Token 已失效或被重置 ({ci_msg})")

        # 2) 查余额
        balance_text = ""
        try:
            self_resp = session.get(f"{BASE}/api/user/self", timeout=20)
            if self_resp.status_code == 200:
                data = self_resp.json().get("data") or {}
                quota = data.get("quota", 0)
                balance_text = f", 余额 ${quota / QUOTA_PER_USD:.2f}"
        except Exception:
            pass

        if ci_ok or "已签" in ci_msg:
            return CheckinResult(self.name, success=True,
                                 message=f"{ci_msg or '签到成功'}{balance_text}")
        return CheckinResult(self.name, success=False,
                             message=f"{ci_msg or '签到失败'}{balance_text}")
