"""通知模块: 把签到结果推送到 Server酱 / Bark / Telegram。

每个通道独立判断是否配置了环境变量,未配置则静默跳过。
"""
from __future__ import annotations

import os
from html import escape

import requests

TIMEOUT = 15


def _serverchan(title: str, content: str) -> str | None:
    key = os.environ.get("SERVERCHAN_KEY", "").strip()
    if not key:
        return None
    try:
        url = f"https://sctapi.ftqq.com/{key}.send"
        r = requests.post(url, data={"title": title, "desp": content},
                          timeout=TIMEOUT)
        return f"Server酱: HTTP {r.status_code}"
    except Exception as exc:
        return f"Server酱: 异常 {exc}"


def _bark(title: str, content: str) -> str | None:
    key = os.environ.get("BARK_KEY", "").strip()
    if not key:
        return None
    server = os.environ.get("BARK_SERVER", "https://api.day.app").rstrip("/")
    try:
        # 把多行内容用 / 简单处理(Bark 路径不允许换行)
        body = content.replace("\n", " | ")
        r = requests.post(f"{server}/{key}",
                          json={"title": title, "body": body},
                          timeout=TIMEOUT)
        return f"Bark: HTTP {r.status_code}"
    except Exception as exc:
        return f"Bark: 异常 {exc}"


def _telegram(title: str, content: str) -> str | None:
    token = os.environ.get("TG_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TG_CHAT_ID", "").strip()
    if not token or not chat_id:
        return None
    try:
        text = f"<b>{escape(title)}</b>\n\n<pre>{escape(content)}</pre>"
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=TIMEOUT,
        )
        return f"Telegram: HTTP {r.status_code}"
    except Exception as exc:
        return f"Telegram: 异常 {exc}"


def send_notification(title: str, content: str) -> None:
    """触发所有已配置的通知通道。无配置则什么也不做。"""
    channels = (_serverchan, _bark, _telegram)
    fired_any = False
    for fn in channels:
        result = fn(title, content)
        if result is not None:
            fired_any = True
            print(f"[notify] {result}")
    if not fired_any:
        print("[notify] 未配置任何通知通道,跳过推送")
