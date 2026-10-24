"""每日签到主入口。

自动发现 checkins/ 目录下所有 CheckinTask 子类并执行,
汇总结果后通过 notify/ 推送(若配置了通知渠道)。

反风控调度策略:
- 启动随机延迟 0-40 分钟(仅 cron 触发时;手动触发立即跑,方便验证)
- 同站不同账号串行,每个之间间隔 3-15 分钟,顺序随机
- 不同站点用线程池并行,互不阻塞
- self_check 不算"站点",最早跑一次
- 本地测试时设 CHECKIN_FAST=1 跳过所有延迟
"""
from __future__ import annotations

import concurrent.futures
import importlib
import inspect
import os
import pkgutil
import random
import re
import secrets
import sys
import time
from collections import defaultdict
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


# 调度参数 (秒)
STARTUP_DELAY_MAX = 40 * 60       # 启动随机延迟上限: 40 分钟
SAMEMSITE_GAP_MIN = 3 * 60        # 同站账号最小间隔: 3 分钟
SAMEMSITE_GAP_MAX = 15 * 60       # 同站账号最大间隔: 15 分钟

# 任务 name 形如 "站点[账号]",取 [ 前作为站点标识
_SITE_RE = re.compile(r"^([^\[]+?)(?:\[|$)")

# 站内任务跑前等待用 secrets.SystemRandom 取真随机(避免可预测)
_rng = random.SystemRandom()


def is_fast_mode() -> bool:
    return os.environ.get("CHECKIN_FAST") == "1"


def is_scheduled_run() -> bool:
    """是否是 cron 自动触发(workflow_dispatch / 本地直接跑 → False)。"""
    return os.environ.get("GITHUB_EVENT_NAME") == "schedule"


def cn_now() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")


def fmt_secs(s: float) -> str:
    s = int(s)
    if s < 60:
        return f"{s} 秒"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m} 分 {sec} 秒"
    h, m = divmod(m, 60)
    return f"{h} 小时 {m} 分 {sec} 秒"


def discover_tasks() -> list[CheckinTask]:
    """遍历 checkins 包内所有模块,生成所有 CheckinTask 实例。

    每个模块支持两种导出方式:
    1. 模块顶层提供 `tasks: list[CheckinTask]` —— 直接用(可包含多账号实例)
    2. 否则扫描模块内的 CheckinTask 子类,每个类实例化一份

    注意: 方式 1 的模块即使当前 `tasks` 为空(未配账号),也只算"没有任务",
    不应回退到方式 2 去无参实例化那些 __init__ 需要必填参数的多账号类。
    """
    tasks: list[CheckinTask] = []
    for mod_info in pkgutil.iter_modules(checkins.__path__):
        if mod_info.name in ("base",) or mod_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"checkins.{mod_info.name}")

        # 方式 1: 模块显式声明了 tasks 属性(哪怕是空 list,也代表"由本列表说了算")
        if hasattr(module, "tasks"):
            explicit = module.tasks
            if isinstance(explicit, list):
                tasks.extend(t for t in explicit if isinstance(t, CheckinTask))
            continue

        # 方式 2: 没有 tasks 属性,扫描类并无参实例化
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (issubclass(obj, CheckinTask)
                    and obj is not CheckinTask
                    and obj.__module__ == module.__name__):
                tasks.append(obj())
    return tasks


def site_of(task: CheckinTask) -> str:
    """从任务 name 提取站点标识 (例如 'johndoe.ai[alice]' → 'johndoe.ai')。
    没有 [ 的任务(例如 self_check)整体作为独立站点。"""
    m = _SITE_RE.match(task.name)
    return m.group(1).strip() if m else task.name


def run_one(task: CheckinTask) -> tuple[CheckinResult, str]:
    """执行单任务,返回结果 + 完成时间(用于排序展示)。"""
    result = task.run()
    return result, cn_now()


def run_site(site: str, site_tasks: list[CheckinTask]) -> list[tuple[CheckinResult, str]]:
    """同一站点内,顺序随机打乱后串行执行,每个之间等一个随机间隔。"""
    fast = is_fast_mode()
    order = list(site_tasks)
    _rng.shuffle(order)

    out: list[tuple[CheckinResult, str]] = []
    for idx, task in enumerate(order):
        if idx > 0 and not fast:
            gap = _rng.randint(SAMEMSITE_GAP_MIN, SAMEMSITE_GAP_MAX)
            print(f"[{site}] 等待 {fmt_secs(gap)} 后跑下一个账号", flush=True)
            time.sleep(gap)
        print(f"[{site}] 开始: {task.name}  @ {cn_now()}", flush=True)
        out.append(run_one(task))
    return out


def main() -> int:
    start = cn_now()
    print(f"=== 每日签到唤醒 {start} (UTC+8) ===", flush=True)

    tasks = discover_tasks()
    if not tasks:
        print("未发现任何签到任务。请在 checkins/ 下添加签到脚本。")
        return 0

    # 1) 启动随机延迟(仅 cron 触发且未启用 fast 模式)
    if is_scheduled_run() and not is_fast_mode():
        delay = secrets.randbelow(STARTUP_DELAY_MAX + 1)  # 0..STARTUP_DELAY_MAX
        print(f"启动延迟 {fmt_secs(delay)}, 将在 {cn_now()} 之后开跑", flush=True)
        time.sleep(delay)
    else:
        reason = "fast 模式" if is_fast_mode() else "非定时触发(手动/本地)"
        print(f"跳过启动延迟({reason}),立即开跑", flush=True)

    print(f"=== 实际开跑 {cn_now()} ===", flush=True)

    # 2) 按站点分组
    by_site: dict[str, list[CheckinTask]] = defaultdict(list)
    for t in tasks:
        by_site[site_of(t)].append(t)

    sites = list(by_site.keys())
    _rng.shuffle(sites)  # 站点之间也随机一下顺序(虽然是并行,但日志顺序更不一样)
    print(f"发现 {len(tasks)} 个任务,分布在 {len(sites)} 个站点: {sites}", flush=True)

    # 3) 不同站点用线程池并行,同站内串行(在 run_site 里 sleep+顺序)
    results_with_time: list[tuple[CheckinResult, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(sites))) as pool:
        futures = {pool.submit(run_site, s, by_site[s]): s for s in sites}
        for fut in concurrent.futures.as_completed(futures):
            try:
                results_with_time.extend(fut.result())
            except Exception as exc:  # noqa: BLE001
                site = futures[fut]
                results_with_time.append((
                    CheckinResult(site, success=False,
                                  message=f"站点任务整体异常: {type(exc).__name__}: {exc}"),
                    cn_now(),
                ))

    # 4) 展示按 task.name 字典序排序(让每天的汇总顺序稳定,执行顺序仍随机)
    results_with_time.sort(key=lambda x: x[0].name)
    results = [r for r, _ in results_with_time]

    for result, t in results_with_time:
        if result.skipped:
            icon = "⏭️"
        elif result.success:
            icon = "✅"
        else:
            icon = "❌"
        print(f"{icon} [{result.name}] {result.message}  ({t})")

    # 5) 汇总
    executed = [r for r in results if not r.skipped]
    succeeded = [r for r in executed if r.success]
    failed = [r for r in executed if not r.success]
    skipped = [r for r in results if r.skipped]

    summary_lines = [
        f"开始: {start} (UTC+8)",
        f"结束: {cn_now()} (UTC+8)",
        f"成功 {len(succeeded)} / 失败 {len(failed)} / 跳过 {len(skipped)}",
        "",
    ]
    for r in results:
        mark = "⏭️ 跳过" if r.skipped else ("✅ 成功" if r.success else "❌ 失败")
        summary_lines.append(f"{mark} | {r.name} | {r.message}")
    summary = "\n".join(summary_lines)

    print("\n--- 汇总 ---")
    print(summary)

    if executed:
        title = f"签到完成 ✅{len(succeeded)} ❌{len(failed)}"
        send_notification(title, summary)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
