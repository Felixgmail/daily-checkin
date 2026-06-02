"""token.dialoguedui.com (小怼Code) 签到,支持多账号。

这个站点登录走 Cloudflare Turnstile 人机验证,脚本无法自动登录,所以不能
"账号密码现登现签"。但它有 refresh_token 机制可以绕开 Turnstile 续期:

  - 鉴权: POST /api/v1/auth/refresh {refresh_token}
           → 返回 {access_token(JWT,24h), refresh_token(新值), expires_in}
           refresh_token 是【一次性轮转】的: 用一次旧的立即失效(401),且无重叠
           宽限期。所以每次用完必须把新 refresh_token 持久化回 GitHub Secret,
           否则次日链条断裂,需重新登录网页取 rt。
  - 签到: POST /checkin/api/checkin  (注意: 这是 /checkin/ 独立站点,无 /v1 前缀)
           header Authorization: Bearer <access_token>, body "{}"
           成功返回 {"ok":true,"data":{"alreadyChecked":bool,"record":{...}}}

轮转加固(关键): 实测 access_token 独立于 rt 生命周期 —— rt 被轮转掉后,先前
换出的 access_token 在 24h 内仍能签到。利用这点做四层加固:
  L1 顺序最稳:  refresh 拿到新 rt → 立即落盘待回写 → 再签到(签到失败也不丢 rt)
  L3 at 兜底:   存量 access_token 未过期就直接签到、不碰 rt(正常一天最多消费 1 次 rt)
  L4 主动告警:  refresh 401(链断)时由 main 汇总后通过 notify 推醒目告警
  (L2 回写读回校验+重试在 workflow 层做)

多账号配置:
   DIALOGUEDUI_<账号>_REFRESH_TOKEN          (必填, 当前有效 refresh_token)
   DIALOGUEDUI_<账号>_ACCESS_TOKEN / _ACCESS_EXP  (可选, 脚本自动回写维护, 首次可不配)

轮转出的新 token 写到 ROTATED_TOKENS_FILE 指向的文件(默认 rotated_tokens.env),
dotenv 行格式,由 workflow 用 `gh secret set --env-file` 回写(避开 shell 转义)。
"""
from __future__ import annotations

import os
import re
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from checkins.base import CheckinTask, CheckinResult


SITE_LABEL = "token.dialoguedui.com"
BASE_URL = "https://token.dialoguedui.com"
ENV_PREFIX = "DIALOGUEDUI"

# access_token 过期余量: 距离过期不足这么多秒就视为"将过期",改走 refresh。
_EXP_MARGIN = 5 * 60

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# 对超时 / 连接错误 / 5xx 自动重试 2 次。注意: refresh 接口【不能】重试 ——
# rt 一次性轮转,若首次其实成功但响应丢失,重试会拿失效的旧 rt 报 401。
# 所以只对 GET / 签到(幂等)开重试,refresh 单独用不带重试的请求。
_RETRY = Retry(
    total=2,
    connect=2,
    read=2,
    backoff_factor=1,
    status_forcelist=[502, 503, 504],
    allowed_methods=frozenset(["GET", "HEAD"]),
)

_TIMEOUT = 30


def _rotated_file() -> str:
    return os.environ.get("ROTATED_TOKENS_FILE", "rotated_tokens.env").strip() \
        or "rotated_tokens.env"


class DialogueDuiTask(CheckinTask):
    """token.dialoguedui.com 单账号签到。"""

    def __init__(self, account: str, rt_env: str,
                 at_env: str, exp_env: str) -> None:
        self.account = account
        self.name = f"{SITE_LABEL}[{account.lower()}]"
        # 只有 refresh_token 是必需的; access_token/exp 是脚本自维护的可选项。
        self.required_env = [rt_env]
        self._rt_env = rt_env
        self._at_env = at_env
        self._exp_env = exp_env
        # refresh 返回 401(rt 彻底失效)时置位,供 message 给出醒目提示(L4)。
        self.chain_broken = False
        super().__init__()
        # 可选的 at / exp 单独读(不进 required_env,避免影响 is_configured)
        self._stored_at = os.environ.get(at_env, "").strip()
        self._stored_exp = os.environ.get(exp_env, "").strip()

    def _make_session(self) -> requests.Session:
        session = requests.Session()
        session.mount("https://", HTTPAdapter(max_retries=_RETRY))
        session.headers.update({
            "User-Agent": UA,
            "Accept": "application/json",
            "Origin": BASE_URL,
            "Referer": BASE_URL + "/",
        })
        return session

    def _stored_at_valid(self) -> bool:
        """存量 access_token 是否存在且距过期还有余量(L3 兜底前置判断)。"""
        if not self._stored_at or not self._stored_exp:
            return False
        try:
            exp = int(float(self._stored_exp))
        except ValueError:
            return False
        return exp - int(time.time()) > _EXP_MARGIN

    def _write_rotated(self, refresh_token: str, access_token: str,
                       exp: int) -> None:
        """把新 token 落盘待 workflow 回写(L1: 一拿到就写,在签到之前)。
        失败只记日志,不影响签到。绝不打印 token 本身。"""
        try:
            lines = [
                f"{self._rt_env}={refresh_token}",
                f"{self._at_env}={access_token}",
                f"{self._exp_env}={exp}",
            ]
            with open(_rotated_file(), "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError as exc:
            print(f"[{self.name}] 警告: 写 rotated 文件失败: {exc}", flush=True)

    def _refresh(self, session: requests.Session) -> str:
        """用 refresh_token 换新 access_token。成功后立即落盘新 token。
        返回 access_token。401 时置 chain_broken 并抛异常。"""
        resp = session.post(
            f"{BASE_URL}/api/v1/auth/refresh",
            json={"refresh_token": self.env[self._rt_env]},
            headers={"Content-Type": "application/json"},
            timeout=_TIMEOUT,
        )
        if resp.status_code == 401:
            self.chain_broken = True
            raise RuntimeError(
                "refresh_token 失效(401),链条已断。请重新登录 "
                f"{BASE_URL} 后在浏览器 Console 执行 "
                "localStorage.getItem('refresh_token') 取新值更新 Secret")
        if resp.status_code != 200:
            raise RuntimeError(
                f"refresh 失败 HTTP {resp.status_code}: {resp.text[:200]}")

        data = (resp.json() or {}).get("data") or {}
        access_token = data.get("access_token")
        new_rt = data.get("refresh_token")
        expires_in = data.get("expires_in") or 0
        if not access_token or not new_rt:
            raise RuntimeError("refresh 响应缺 access_token / refresh_token")

        # L1: 立即落盘(在签到之前),保证拿到的新 rt 不丢
        exp_ts = int(time.time()) + int(expires_in)
        self._write_rotated(new_rt, access_token, exp_ts)
        return access_token

    def _do_checkin(self, session: requests.Session, access_token: str
                    ) -> CheckinResult:
        resp = session.post(
            f"{BASE_URL}/checkin/api/checkin",
            headers={"Authorization": f"Bearer {access_token}",
                     "Content-Type": "application/json"},
            data="{}",
            timeout=_TIMEOUT,
        )
        try:
            body = resp.json() or {}
        except ValueError:
            body = {}

        if resp.status_code == 200 and body.get("ok"):
            data = body.get("data") or {}
            record = data.get("record") or {}
            streak = record.get("streak_days")
            reward = record.get("reward_amount")
            extra = ""
            if streak is not None:
                extra += f", 连续 {streak} 天"
            if reward is not None:
                extra += f", 奖励 ${reward}"
            head = "今日已签到" if data.get("alreadyChecked") else "签到成功"
            return CheckinResult(self.name, success=True, message=head + extra)

        msg = body.get("message") or resp.text[:200]
        return CheckinResult(self.name, success=False,
                             message=f"签到失败 HTTP {resp.status_code}: {msg}")

    def check_in(self) -> CheckinResult:
        session = self._make_session()

        # L3: 存量 access_token 没过期就直接签到,不消费 refresh_token
        if self._stored_at_valid():
            try:
                result = self._do_checkin(session, self._stored_at)
                if result.success:
                    return result
                # 存量 at 签到失败(可能服务端提前失效),回退到 refresh
                print(f"[{self.name}] 存量 access_token 签到失败,回退 refresh",
                      flush=True)
            except requests.RequestException as exc:
                print(f"[{self.name}] 存量 access_token 签到异常,回退 refresh: "
                      f"{exc}", flush=True)

        # 走 refresh 换新 token(内部已 L1 落盘),再签到
        access_token = self._refresh(session)
        return self._do_checkin(session, access_token)


def _discover() -> list[DialogueDuiTask]:
    """扫描环境变量发现所有账号。
    约定: DIALOGUEDUI_<账号>_REFRESH_TOKEN(必需),
          DIALOGUEDUI_<账号>_ACCESS_TOKEN / _ACCESS_EXP(可选,自维护)。
    """
    rt_re = re.compile(
        rf"^{re.escape(ENV_PREFIX)}_(?P<account>[A-Z0-9]+)_REFRESH_TOKEN$")
    tasks: list[DialogueDuiTask] = []
    for key in sorted(os.environ.keys()):
        m = rt_re.match(key)
        if not m:
            continue
        account = m.group("account")
        at_env = f"{ENV_PREFIX}_{account}_ACCESS_TOKEN"
        exp_env = f"{ENV_PREFIX}_{account}_ACCESS_EXP"
        tasks.append(DialogueDuiTask(account, key, at_env, exp_env))
    return tasks


tasks = _discover()
