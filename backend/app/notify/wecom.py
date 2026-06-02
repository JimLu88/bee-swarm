"""wecom — 企业微信群机器人 webhook 通知.

开发模式里"需要人介入"的环节(申请 Key/验证码、PR 待审、跑批失败)推一条到企业微信,
点链接就处理。配置:环境变量 `WECOM_WEBHOOK_URL`(群机器人 webhook 地址)。
未配置时 notify() 静默返回 {"ok": False, "skipped": True},绝不抛错、绝不阻断主流程。

企业微信群机器人消息格式:POST webhook_url
- text:     {"msgtype":"text","text":{"content":"..."}}
- markdown: {"msgtype":"markdown","markdown":{"content":"..."}}
成功返回 {"errcode":0,"errmsg":"ok"}。
"""

from __future__ import annotations

import os
from typing import Any

import httpx

_TIMEOUT = 8.0


def _webhook_url() -> str:
    return (os.environ.get("WECOM_WEBHOOK_URL") or "").strip()


def is_configured() -> bool:
    return bool(_webhook_url())


def _send(payload: dict[str, Any]) -> dict[str, Any]:
    url = _webhook_url()
    if not url:
        return {"ok": False, "skipped": True, "reason": "WECOM_WEBHOOK_URL 未配置"}
    try:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.post(url, json=payload)
        data: dict[str, Any] = {}
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text[:300]}
        ok = r.status_code < 400 and data.get("errcode", 0) == 0
        return {"ok": ok, "status": r.status_code, "resp": data}
    except Exception as e:
        # best-effort: 通知失败绝不影响主流程
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


def notify(content: str) -> dict[str, Any]:
    """发纯文本提醒。content 会被截到 1800 字(企业微信单条上限 ~2048 字节)。"""
    return _send({"msgtype": "text", "text": {"content": str(content)[:1800]}})


def notify_markdown(content: str) -> dict[str, Any]:
    """发 markdown 提醒(支持加粗/链接/颜色),适合 PR 待审带链接。"""
    return _send({"msgtype": "markdown", "markdown": {"content": str(content)[:3800]}})
