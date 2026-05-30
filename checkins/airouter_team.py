"""ai.router.team (RouterTeam) 签到,支持多账号。

这个站点不是 New API 架构,接口/鉴权与其他站点都不同,所以单独成模块:
  - 鉴权: 账号密码登录 POST /api/auth/login {username,password} → 返回 accessToken (JWT)
           JWT 约 24h 过期,因此不能像 New API 那样存长期 token,必须每次现登。
  - 签到: POST /api/user/reward-center/sign-in
           成功返回 200;已签到返回 HTTP 400 + code "already_signed_in"。
  - 余额: GET /api/user/dashboard → balance 字段(对应 dashboard 页 $XX.XX)。

多账号配置:
   每个账号一对 Secret: AIROUTER_<账号名>_USERNAME + AIROUTER_<账号名>_PASSWORD
   例如:
     AIROUTER_LINFANLONG_USERNAME  ↔  AIROUTER_LINFANLONG_PASSWORD
"""
from __future__ import annotations

import os
import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from checkins.base import CheckinTask, CheckinResult


SITE_LABEL = "ai.router.team"
BASE_URL = "https://ai.router.team"
ENV_PREFIX = "AIROUTER"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# 对超时 / 连接错误 / 5xx 自动重试 2 次,间隔 1s → 2s。
# allowed_methods=None → 所有方法(含 POST)都重试。登录幂等、签到接口对重复请求
# 只返回 already_signed_in,重试安全。
_RETRY = Retry(
    total=2,
    connect=2,
    read=2,
    backoff_factor=1,
    status_forcelist=[502, 503, 504],
    allowed_methods=None,
)

# 单次请求超时(秒)
_TIMEOUT = 30


class AIRouterTask(CheckinTask):
    """ai.router.team 单账号签到。"""

    def __init__(self, account: str, user_env: str, pass_env: str) -> None:
        self.account = account
        self.name = f"{SITE_LABEL}[{account.lower()}]"
        self.required_env = [user_env, pass_env]
        self._user_env = user_env
        self._pass_env = pass_env
        super().__init__()

    def _make_session(self) -> requests.Session:
        session = requests.Session()
        session.mount("https://", HTTPAdapter(max_retries=_RETRY))
        session.headers.update({
            "User-Agent": UA,
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        return session

    def _login(self, session: requests.Session) -> str:
        """登录换取 JWT access token。失败抛异常由 run() 兜底。"""
        resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "username": self.env[self._user_env],
                "password": self.env[self._pass_env],
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"登录失败 HTTP {resp.status_code}: {resp.text[:200]}")
        token = (resp.json() or {}).get("accessToken")
        if not token:
            raise RuntimeError("登录响应未包含 accessToken")
        return token

    def _balance_text(self, session: requests.Session) -> str:
        """查余额(失败不影响签到结果展示)。"""
        try:
            resp = session.get(f"{BASE_URL}/api/user/dashboard", timeout=_TIMEOUT)
            if resp.status_code == 200:
                balance = (resp.json() or {}).get("balance")
                if balance is not None:
                    return f", 余额 ${balance:.2f}"
        except Exception:
            pass
        return ""

    def check_in(self) -> CheckinResult:
        session = self._make_session()

        token = self._login(session)
        session.headers["Authorization"] = f"Bearer {token}"

        resp = session.post(
            f"{BASE_URL}/api/user/reward-center/sign-in", json={}, timeout=_TIMEOUT)

        # 成功
        if resp.status_code == 200:
            return CheckinResult(self.name, success=True,
                                 message=f"签到成功{self._balance_text(session)}")

        # 解析错误码
        code = msg = ""
        try:
            body = resp.json() or {}
            code = body.get("code", "")
            msg = body.get("message", "")
        except ValueError:
            msg = resp.text[:200]

        # 已签到也算成功(幂等)
        if code == "already_signed_in" or "已" in msg:
            return CheckinResult(self.name, success=True,
                                 message=f"今日已签到{self._balance_text(session)}")

        return CheckinResult(self.name, success=False,
                             message=f"签到失败 HTTP {resp.status_code} {code}: {msg}")


def _discover() -> list[AIRouterTask]:
    """扫描环境变量发现所有账号。
    约定: AIROUTER_<账号>_USERNAME ↔ AIROUTER_<账号>_PASSWORD
    """
    user_re = re.compile(rf"^{re.escape(ENV_PREFIX)}_(?P<account>[A-Z0-9]+)_USERNAME$")
    tasks: list[AIRouterTask] = []
    for key in sorted(os.environ.keys()):
        m = user_re.match(key)
        if not m:
            continue
        account = m.group("account")
        pass_env = f"{ENV_PREFIX}_{account}_PASSWORD"
        if pass_env not in os.environ:
            continue  # 配了一半,跳过
        tasks.append(AIRouterTask(account, key, pass_env))
    return tasks


tasks = _discover()
