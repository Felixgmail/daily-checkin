"""V2EX 每日签到示例。

需要设置环境变量 V2EX_COOKIE,值为登录后浏览器中的整个 Cookie 字符串。

获取方法:
1. 浏览器登录 v2ex.com
2. F12 → Network → 刷新页面 → 找到 GET https://www.v2ex.com/
   → Headers → Request Headers → Cookie → 整段复制
3. 把它存到 GitHub Secrets 里,key 命名为 V2EX_COOKIE

签到完会得到一次随机奖励铜币。
"""
from __future__ import annotations

import re

import requests

from checkins.base import CheckinTask, CheckinResult


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


class V2EXTask(CheckinTask):
    name = "V2EX"
    required_env = ["V2EX_COOKIE"]

    def check_in(self) -> CheckinResult:
        cookie = self.env["V2EX_COOKIE"]
        headers = {
            "User-Agent": UA,
            "Cookie": cookie,
            "Referer": "https://www.v2ex.com/",
        }
        session = requests.Session()

        # 第 1 步: 获取签到页面 + once token
        r = session.get("https://www.v2ex.com/mission/daily",
                        headers=headers, timeout=20, allow_redirects=False)
        if r.status_code != 200:
            return CheckinResult(self.name, success=False,
                                 message=f"获取签到页失败 HTTP {r.status_code} (Cookie 可能已失效)")

        if "每日登录奖励已领取" in r.text:
            # 拿一下当前余额
            balance = self._get_balance(session, headers)
            return CheckinResult(self.name, success=True,
                                 message=f"今日已签到{balance}")

        m = re.search(r"/mission/daily/redeem\?once=(\d+)", r.text)
        if not m:
            return CheckinResult(self.name, success=False,
                                 message="未找到 once token,Cookie 可能已失效")
        once = m.group(1)

        # 第 2 步: 领取奖励
        r2 = session.get(f"https://www.v2ex.com/mission/daily/redeem?once={once}",
                         headers=headers, timeout=20, allow_redirects=False)
        if r2.status_code not in (200, 302):
            return CheckinResult(self.name, success=False,
                                 message=f"领取失败 HTTP {r2.status_code}")

        balance = self._get_balance(session, headers)
        return CheckinResult(self.name, success=True,
                             message=f"签到成功{balance}")

    def _get_balance(self, session: requests.Session, headers: dict) -> str:
        try:
            r = session.get("https://www.v2ex.com/balance",
                            headers=headers, timeout=20)
            # 余额页第一行通常是当前铜币总数
            m = re.search(r"<td[^>]*>(\d+)\s*</td>", r.text)
            if m:
                return f",当前铜币 {m.group(1)}"
        except Exception:
            pass
        return ""
