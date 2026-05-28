"""每日签到主入口。

自动发现 checkins/ 目录下所有 CheckinTask 子类并执行,
汇总结果后通过 notify/ 推送(若配置了通知渠道)。
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
from datetime import datetime, timezone, timedelta

# Windows 控制台默认 GBK,强制切到 UTF-8 让 emoji/中文正常显示
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import checkins
from checkins.base import CheckinTask, CheckinResult
from notify import send_notification


def discover_tasks() -> list[CheckinTask]:
    """遍历 checkins 包内所有模块,实例化每个 CheckinTask 子类。"""
    tasks: list[CheckinTask] = []
    for mod_info in pkgutil.iter_modules(checkins.__path__):
        if mod_info.name in ("base",) or mod_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"checkins.{mod_info.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (issubclass(obj, CheckinTask)
                    and obj is not CheckinTask
                    and obj.__module__ == module.__name__):
                tasks.append(obj())
    return tasks


def cn_now() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")


def main() -> int:
    print(f"=== 每日签到开始 {cn_now()} (UTC+8) ===")
    tasks = discover_tasks()
    if not tasks:
        print("未发现任何签到任务。请在 checkins/ 下添加签到脚本。")
        return 0

    results: list[CheckinResult] = []
    for task in tasks:
        result = task.run()
        results.append(result)
        if result.skipped:
            icon = "⏭️"
        elif result.success:
            icon = "✅"
        else:
            icon = "❌"
        print(f"{icon} [{result.name}] {result.message}")

    # 汇总
    executed = [r for r in results if not r.skipped]
    succeeded = [r for r in executed if r.success]
    failed = [r for r in executed if not r.success]
    skipped = [r for r in results if r.skipped]

    summary_lines = [
        f"签到时间: {cn_now()} (UTC+8)",
        f"成功 {len(succeeded)} / 失败 {len(failed)} / 跳过 {len(skipped)}",
        "",
    ]
    for r in results:
        mark = "⏭️ 跳过" if r.skipped else ("✅ 成功" if r.success else "❌ 失败")
        summary_lines.append(f"{mark} | {r.name} | {r.message}")
    summary = "\n".join(summary_lines)

    print("\n--- 汇总 ---")
    print(summary)

    # 通知(仅当有实际执行的任务时才推送,避免空跑刷屏)
    if executed:
        title = f"签到完成 ✅{len(succeeded)} ❌{len(failed)}"
        send_notification(title, summary)

    # 有失败任务时返回非 0,便于 Actions 标记为失败(可在 workflow 里选择是否当真失败)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
