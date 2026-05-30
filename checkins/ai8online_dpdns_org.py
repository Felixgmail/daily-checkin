"""ai.8online.dpdns.org 签到 (Codex API Platform),支持多账号。

接口特征:
  - 登录: POST /api/auth/login {"username":"xxx","password":"xxx"} → {token, user}
  - 签到: POST /api/user/checkin (需 Authorization: Bearer <token>)
    - 成功: {"error":"今日已签到","voucher":{...}} 或 {"voucher":{...}}
    - 失败: {"error":"xxx"}
  - 余额在 voucher.balance 字段

多账号配置:
   每个账号一对 Secret: AI8ONLINE_<账号名>_USERNAME + AI8ONLINE_<账号名>_PASSWORD
   例如:
     AI8ONLINE_LINDINGCHAN_F4DA_USERNAME  ↔  AI8ONLINE_LINDINGCHAN_F4DA_PASSWORD

获取凭据:
   直接使用网站的用户名和密码。
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

# 对超时 / 连接错误 / 5xx 自动重试 2 次,间隔 1s → 2s。
# allowed_methods=None 表示所有方法都重试(含 POST)——签到 POST 是幂等的
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


class AI8OnlineTask(CheckinTask):
    """单个 ai.8online.dpdns.org 账号的签到。"""

    def __init__(self, account: str, username_env: str, password_env: str) -> None:
        self.account = account
        self.name = f"ai.8online[{account.lower()}]"
        self.required_env = [username_env, password_env]
        self._username_env = username_env
        self._password_env = password_env
        super().__init__()

    def _make_session(self) -> requests.Session:
        session = requests.Session()
        session.mount("https://", HTTPAdapter(max_retries=_RETRY))
        session.headers.update({
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
        })
        return session

    def check_in(self) -> CheckinResult:
        session = self._make_session()
        base_url = "https://ai.8online.dpdns.org"

        # 1) 登录获取 token
        login_data = {
            "username": self.env[self._username_env],
            "password": self.env[self._password_env],
        }
        try:
            login_resp = session.post(f"{base_url}/api/auth/login",
                                     json=login_data, timeout=_TIMEOUT)
        except requests.RequestException as e:
            return CheckinResult(self.name, success=False,
                                message=f"登录请求失败: {type(e).__name__}: {e}")

        if login_resp.status_code != 200:
            return CheckinResult(self.name, success=False,
                                message=f"登录失败 HTTP {login_resp.status_code}: {login_resp.text[:200]}")

        try:
            login_json = login_resp.json()
        except ValueError:
            return CheckinResult(self.name, success=False,
                                message=f"登录响应非 JSON: {login_resp.text[:200]}")

        token = login_json.get("token")
        if not token:
            return CheckinResult(self.name, success=False,
                                message=f"登录响应无 token: {login_resp.text[:200]}")

        # 2) 签到
        session.headers["Authorization"] = f"Bearer {token}"
        try:
            ci_resp = session.post(f"{base_url}/api/user/checkin", timeout=_TIMEOUT)
        except requests.RequestException as e:
            return CheckinResult(self.name, success=False,
                                message=f"签到请求失败: {type(e).__name__}: {e}")

        # 409 表示今日已签到,仍然算成功
        if ci_resp.status_code not in (200, 409):
            return CheckinResult(self.name, success=False,
                                message=f"签到请求失败 HTTP {ci_resp.status_code}: {ci_resp.text[:200]}")

        try:
            ci_data = ci_resp.json()
        except ValueError:
            return CheckinResult(self.name, success=False,
                                message=f"签到响应非 JSON: {ci_resp.text[:200]}")

        # 3) 解析结果
        error_msg = ci_data.get("error", "")
        voucher = ci_data.get("voucher", {})
        balance = voucher.get("balance", 0)
        today_reward = voucher.get("todayReward", 0)
        checked_in_today = voucher.get("checkedInToday", False)

        balance_text = f", 余额 ${balance:.2f}"

        # 判断成功:要么已签到,要么有 voucher 数据
        if checked_in_today or voucher:
            if "已签到" in error_msg or checked_in_today:
                msg = f"今日已签到 +${today_reward:.2f}{balance_text}"
            else:
                msg = f"签到成功 +${today_reward:.2f}{balance_text}"
            return CheckinResult(self.name, success=True, message=msg)

        # 失败
        return CheckinResult(self.name, success=False,
                            message=f"{error_msg or '签到失败'}{balance_text}")


def build_tasks() -> list[AI8OnlineTask]:
    """扫描环境变量自动发现所有账号。

    约定的 Secret 命名:
      AI8ONLINE_<账号名>_USERNAME     该账号的用户名
      AI8ONLINE_<账号名>_PASSWORD     该账号的密码

    例如:
      AI8ONLINE_LINDINGCHAN_F4DA_USERNAME  ↔  AI8ONLINE_LINDINGCHAN_F4DA_PASSWORD
    """
    username_re = re.compile(r"^AI8ONLINE_(?P<account>[A-Z0-9_]+)_USERNAME$")
    tasks: list[AI8OnlineTask] = []
    for key in sorted(os.environ.keys()):
        m = username_re.match(key)
        if not m:
            continue
        account = m.group("account")
        password_env = f"AI8ONLINE_{account}_PASSWORD"
        if password_env not in os.environ:
            continue  # 配了一半,跳过
        tasks.append(AI8OnlineTask(account, key, password_env))
    return tasks


# 导出任务列表供 main.py 自动发现
tasks = build_tasks()
