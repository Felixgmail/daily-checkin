"""console.altare.gg 每日奖励签到(daily reward claim),支持多账号。

接口侦察(2026-11-20,前端 bundle 反查 + 实测):
  - 登录: POST /api/auth/login  {"identifier": email, "password": pwd}
          → {token, userId}。纯密码登录,无 Turnstile / 无验证码。
          token 长效(前端存 localStorage.manhattan_token,登录响应无过期字段)。
  - tenant 列表: GET /api/tenants → items[] (取 role=owner 的第一个)
  - 状态: GET /api/tenants/{tid}/rewards → daily.canClaim / currentStreak /
          totalRewardCents 等
  - 签到: POST /api/tenants/{tid}/rewards/claim
          成功 → {totalRewardCents, baseRewardCents, streakBonusCents, ...}
          已签 → HTTP 400 {"error":"Already claimed today"}(幂等,不会重复发额度)
  - 鉴权: Authorization: Bearer <token>
  - 所有非 GET 请求前端会带 Idempotency-Key: <uuid>,这里照做。

⚠️ 反爬注意:该站对裸 curl 指纹的 POST 会由 Cloudflare 返回 429(GET 不受影响)。
   必须带正常浏览器 UA + Origin/Referer。实测带这些头 + 浏览器会话均正常。

规则:每个 UTC 日每人只能在一个自己拥有的 team 上领一次;连续签到每天
      多 0.67 bolts 加成,10 天封顶 6.67 bolts;漏一天归零。

多账号配置:
  每个账号一对 Secret: ALTARE_<账号名>_EMAIL + ALTARE_<账号名>_PASSWORD
  例如: ALTARE_LINDINGCHAN86_EMAIL ↔ ALTARE_LINDINGCHAN86_PASSWORD
"""
from __future__ import annotations

import os
import re
import uuid

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from checkins.base import CheckinTask, CheckinResult

SITE_LABEL = "console.altare.gg"
BASE_URL = "https://console.altare.gg"
ENV_PREFIX = "ALTARE"
_TIMEOUT = 30

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# 站点偶发 502 / 429(Cloudflare 对本机 curl 指纹),重试 2 次、间隔 2s→4s。
# POST 全部带 Idempotency-Key,重复提交不会重复发额度,所以重试安全。
_RETRY = Retry(
    total=2,
    connect=2,
    read=2,
    backoff_factor=2,
    status_forcelist=[429, 502, 503, 504],
    allowed_methods=None,
    respect_retry_after_header=True,
)


class AltareTask(CheckinTask):
    """单个账号的 daily reward claim。"""

    def __init__(self, account: str, email_env: str, password_env: str) -> None:
        self.account = account
        self.name = f"{SITE_LABEL}[{account.lower()}]"
        self.required_env = [email_env, password_env]
        self._email_env = email_env
        self._password_env = password_env
        super().__init__()

    def _base_headers(self) -> dict[str, str]:
        return {
            "User-Agent": UA,
            "Accept": "application/json",
            "Origin": BASE_URL,
            "Referer": BASE_URL + "/billing/rewards/daily",
            "Content-Type": "application/json",
        }

    def _login(self, session: requests.Session) -> str:
        resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "identifier": self.env[self._email_env],
                "password": self.env[self._password_env],
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"登录失败 HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        token = data.get("token")
        if not token:
            # 有些账号可能要求二次验证(challenge),这里给出明确提示
            raise RuntimeError(f"登录响应无 token: {str(data)[:200]}")
        return token

    def _pick_tenant(self, session: requests.Session) -> str:
        resp = session.get(f"{BASE_URL}/api/tenants", timeout=_TIMEOUT)
        if resp.status_code != 200:
            raise RuntimeError(
                f"获取 tenant 失败 HTTP {resp.status_code}: {resp.text[:200]}")
        items = (resp.json() or {}).get("items") or []
        owned = [t for t in items if t.get("role") == "owner"]
        if not owned:
            raise RuntimeError("没有 role=owner 的 team,无法领取每日奖励")
        return owned[0]["id"]

    def check_in(self) -> CheckinResult:
        session = requests.Session()
        session.mount("https://", HTTPAdapter(max_retries=_RETRY))
        session.headers.update(self._base_headers())

        token = self._login(session)
        session.headers["Authorization"] = f"Bearer {token}"
        tid = self._pick_tenant(session)

        # 先查状态:今天已签则直接返回成功(幂等,不必再 POST)
        st = session.get(f"{BASE_URL}/api/tenants/{tid}/rewards", timeout=_TIMEOUT)
        if st.status_code != 200:
            raise RuntimeError(
                f"查询奖励状态失败 HTTP {st.status_code}: {st.text[:200]}")
        daily = (st.json() or {}).get("daily") or {}
        if not daily.get("canClaim", False):
            streak = daily.get("currentStreak", "?")
            return CheckinResult(
                self.name, success=True,
                message=f"今日已签到(连续 {streak} 天)")

        # 领奖
        headers = {"Idempotency-Key": str(uuid.uuid4())}
        claim = session.post(
            f"{BASE_URL}/api/tenants/{tid}/rewards/claim",
            headers=headers, timeout=_TIMEOUT,
        )
        if claim.status_code == 400:
            body = claim.text or ""
            if "already claimed" in body.lower():
                return CheckinResult(self.name, success=True, message="今日已签到")
            raise RuntimeError(f"签到被拒 HTTP 400: {body[:200]}")
        if claim.status_code == 429:
            raise RuntimeError("被限流 HTTP 429(Cloudflare),可稍后重试")
        if claim.status_code != 200:
            raise RuntimeError(
                f"签到失败 HTTP {claim.status_code}: {claim.text[:200]}")

        data = claim.json() or {}
        total = data.get("totalRewardCents")
        cents = f", 奖励 {total} bolts(分)" if total is not None else ""
        bonus = data.get("streakBonusCents") or 0
        streak = data.get("currentStreak") or daily.get("nextStreak") or "?"
        extra = f" (含连续加成 {bonus})" if bonus else ""
        return CheckinResult(
            self.name, success=True,
            message=f"签到成功,连续 {streak} 天{cents}{extra}")


def _discover() -> list[AltareTask]:
    """扫描环境变量发现所有账号。

    约定: ALTARE_<账号名>_EMAIL + ALTARE_<账号名>_PASSWORD
    """
    email_re = re.compile(rf"^{re.escape(ENV_PREFIX)}_(?P<account>[A-Z0-9]+)_EMAIL$")
    tasks: list[AltareTask] = []
    for key in sorted(os.environ.keys()):
        m = email_re.match(key)
        if not m:
            continue
        account = m.group("account")
        pwd_env = f"{ENV_PREFIX}_{account}_PASSWORD"
        if pwd_env not in os.environ:
            continue  # 配了一半,跳过
        tasks.append(AltareTask(account, key, pwd_env))
    return tasks


tasks = _discover()
