"""自检任务: 不需要任何凭据,永远成功。

用于验证签到框架本身在 Actions 上跑得通。
当你添加了真实站点签到任务后,可以删除这个文件。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from checkins.base import CheckinTask, CheckinResult


class SelfCheckTask(CheckinTask):
    name = "自检"
    required_env: list[str] = []  # 无需任何环境变量

    def check_in(self) -> CheckinResult:
        now = datetime.now(timezone(timedelta(hours=8))).strftime("%H:%M:%S")
        return CheckinResult(
            self.name, success=True,
            message=f"框架运行正常 (UTC+8 {now})",
        )
