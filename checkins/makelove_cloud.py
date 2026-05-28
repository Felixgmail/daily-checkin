"""newapi.makelove.cloud 签到 (New API 衍生版),支持多账号。

⚠️ 该站对 GitHub Actions 的 Azure IP 段做了两层限制:
   1) /api/user/login 直接拒登(用户名或密码错误,即使密码对)
   2) session cookie 绑定登录 IP, 跨 IP 复用 cookie 会被拒(401 未登录)
   因此本脚本使用 New API 的 **Access Token** (不绑 IP, 不依赖 session) 鉴权。

多账号配置:
   每个账号定义两个环境变量 (账号名用大写, 任意标识符):
     MAKELOVE_<账号名>_TOKEN     = 该账号的 access token
     MAKELOVE_<账号名>_USER_ID   = 该账号的 user id

   例如两个账号:
     MAKELOVE_A6732413_TOKEN       MAKELOVE_A6732413_USER_ID
     MAKELOVE_JDUHG82736_TOKEN     MAKELOVE_JDUHG82736_USER_ID

   脚本会扫描所有匹配的环境变量并为每个账号注册一个签到任务。

获取 access token:
   1. 浏览器登录 https://newapi.makelove.cloud/console/personal,在页面里找
   2. 或在已登录会话里 GET /api/user/token,响应 data 字段就是

接口侦察记录:
- 鉴权: Authorization: <token> + New-Api-User: <id> (Bearer 前缀可加可不加)
- 签到: POST /api/user/checkin
- 用户信息: GET /api/user/self → data.quota,余额 ≈ quota / 500000 USD
"""
from __future__ import annotations

import os
import re

import requests

from checkins.base import CheckinTask, CheckinResult


BASE = "https://newapi.makelove.cloud"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
QUOTA_PER_USD = 500000

# 环境变量名格式: MAKELOVE_<账号名>_TOKEN 配对 MAKELOVE_<账号名>_USER_ID
_TOKEN_RE = re.compile(r"^MAKELOVE_(?P<account>[A-Z0-9]+)_TOKEN$")


class MakeloveCloudTask(CheckinTask):
    def __init__(self, account: str, token_env: str, user_id_env: str) -> None:
        self.account = account
        self.name = f"makelove.cloud[{account.lower()}]"
        self.required_env = [token_env, user_id_env]
        self._token_env = token_env
        self._user_id_env = user_id_env
        super().__init__()

    def check_in(self) -> CheckinResult:
        session = requests.Session()
        session.headers.update({
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {self.env[self._token_env]}",
            "New-Api-User": self.env[self._user_id_env],
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


def _discover_accounts() -> list[MakeloveCloudTask]:
    """扫描所有 MAKELOVE_<账号名>_TOKEN 环境变量,配对 _USER_ID 生成任务。"""
    found: list[MakeloveCloudTask] = []
    for key in sorted(os.environ.keys()):
        m = _TOKEN_RE.match(key)
        if not m:
            continue
        account = m.group("account")
        user_id_env = f"MAKELOVE_{account}_USER_ID"
        if user_id_env not in os.environ:
            # token 配了 user_id 没配 —— 跳过(任务的 is_configured 也会再次拒绝)
            continue
        found.append(MakeloveCloudTask(account, key, user_id_env))
    return found


tasks = _discover_accounts()
