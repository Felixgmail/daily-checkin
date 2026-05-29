"""签到任务基类。

新增一个站点签到时,在 checkins/ 目录下新建一个 .py 文件,
定义一个继承 CheckinTask 的类并实现 check_in() 即可被自动发现并执行。
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class CheckinResult:
    name: str
    success: bool
    message: str = ""
    skipped: bool = False


class CheckinTask:
    # 站点显示名,子类覆盖
    name: str = "未命名"

    # 该任务需要的环境变量名列表。若任一为空则跳过该任务(视为未配置)。
    # 注意: CheckinTask 不是 dataclass,这里就是一个普通类变量。子类一般会覆盖它;
    # 不覆盖时所有实例共享这个空 list —— 但没人会去 append 它,所以安全。
    required_env: list[str] = []

    def __init__(self) -> None:
        self.env = {key: os.environ.get(key, "") for key in self.required_env}

    def is_configured(self) -> bool:
        """所有必需的环境变量都非空才算已配置。"""
        if not self.required_env:
            return True
        return all(self.env.get(k) for k in self.required_env)

    def check_in(self) -> CheckinResult:
        """执行签到。子类必须实现。返回 CheckinResult。"""
        raise NotImplementedError

    def run(self) -> CheckinResult:
        if not self.is_configured():
            return CheckinResult(self.name, success=False, skipped=True,
                                 message="未配置环境变量,已跳过")
        try:
            return self.check_in()
        except Exception as exc:  # noqa: BLE001 - 单个任务失败不应中断整体
            return CheckinResult(self.name, success=False,
                                 message=f"异常: {type(exc).__name__}: {exc}")
