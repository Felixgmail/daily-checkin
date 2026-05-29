"""New API 通用签到逻辑(被各 New API 站点共用,本身不会作为任务被扫描)。

只要站点是基于 [New API](https://github.com/QuantumNous/new-api) 或其衍生版本,
鉴权和签到接口都是一致的:
  - 鉴权: Authorization: Bearer <access_token> + New-Api-User: <user_id>
  - 签到: POST /api/user/checkin
  - 用户信息: GET /api/user/self → data.quota,余额 ≈ quota / 500000 USD

每个站点写一个薄模块,调用 build_tasks_for_site() 注册多账号即可。
"""
from __future__ import annotations

import os
import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from checkins.base import CheckinTask, CheckinResult


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
QUOTA_PER_USD = 500000

# 对 5xx / 连接错误自动重试 2 次,间隔 1s → 2s
_RETRY = Retry(total=2, backoff_factor=1, status_forcelist=[502, 503, 504])


class NewAPITask(CheckinTask):
    """单个 New API 站点 + 单个账号的签到。"""

    def __init__(self, site_label: str, base_url: str, account: str,
                 token_env: str, user_id_env: str) -> None:
        self.site_label = site_label
        self.base_url = base_url.rstrip("/")
        self.account = account
        self.name = f"{site_label}[{account.lower()}]"
        self.required_env = [token_env, user_id_env]
        self._token_env = token_env
        self._user_id_env = user_id_env
        super().__init__()

    def _make_session(self) -> requests.Session:
        session = requests.Session()
        session.mount("https://", HTTPAdapter(max_retries=_RETRY))
        session.headers.update({
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {self.env[self._token_env]}",
            "New-Api-User": self.env[self._user_id_env],
        })
        return session

    def check_in(self) -> CheckinResult:
        session = self._make_session()

        # 1) 签到
        ci_resp = session.post(f"{self.base_url}/api/user/checkin", timeout=20)
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

        # 2) 查余额(失败不影响签到结果展示)
        balance_text = ""
        try:
            self_resp = session.get(f"{self.base_url}/api/user/self", timeout=20)
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


def build_tasks_for_site(site_label: str, base_url: str,
                         env_prefix: str) -> list[NewAPITask]:
    """扫描环境变量自动发现该站的所有账号。

    约定的 Secret 命名:
      <env_prefix>_<账号名>_TOKEN     该账号的 access token
      <env_prefix>_<账号名>_USER_ID   该账号的 user id

    例如 env_prefix='MAKELOVE',则:
      MAKELOVE_A6732413_TOKEN  ↔  MAKELOVE_A6732413_USER_ID
      MAKELOVE_JDUHG82736_TOKEN ↔  MAKELOVE_JDUHG82736_USER_ID
    """
    token_re = re.compile(rf"^{re.escape(env_prefix)}_(?P<account>[A-Z0-9]+)_TOKEN$")
    tasks: list[NewAPITask] = []
    for key in sorted(os.environ.keys()):
        m = token_re.match(key)
        if not m:
            continue
        account = m.group("account")
        user_id_env = f"{env_prefix}_{account}_USER_ID"
        if user_id_env not in os.environ:
            continue  # 配了一半,跳过
        tasks.append(NewAPITask(site_label, base_url, account, key, user_id_env))
    return tasks
