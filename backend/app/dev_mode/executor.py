"""executor — 把单个 DevTask 交给 PC 上的 Claude Code 写码, 再跑测试.

claude(agent_task, acceptEdits)负责改文件; 但它 shell 被拦, 跑测试走 agent_exec(白名单).
agent_task 是异步(submit→轮询 status), 这里 submit 后轮询到 done/failed/超时。
bee_clients 同步 → asyncio.to_thread 包一层。
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from ..tools.seven_clients import bee_clients

_CODE_MODEL = os.environ.get("BEE_DEV_CODE_MODEL", "")  # 空=用 claude CLI 默认模型
_POLL_INTERVAL = 6.0
_MAX_WAIT = float(os.environ.get("BEE_DEV_CODE_MAX_WAIT", "900"))  # claude 最长等待秒

# 配额信号兜底(agent_hands 已透传 quota_hit; 这里再按文本兜一层, 兼容旧服务)
_QUOTA_MARKERS = (
    "usage limit", "rate limit", "rate_limit", "quota", "429", "exceeded your",
    "try again later", "too many requests", "weekly limit", "5-hour limit",
    "4-hour limit", "reached your", "upgrade your plan", "limit reached", "overloaded",
)


def _looks_like_quota(text: str) -> bool:
    t = (text or "").lower()
    return any(m in t for m in _QUOTA_MARKERS)


def _build_prompt(*, spec: str, sop_hint: str, constraint_text: str) -> str:
    parts = []
    if constraint_text:
        parts.append(f"[项目约束 CLAUDE.md/learnings]\n{constraint_text}")
    if sop_hint:
        parts.append(f"[本次打法]\n{sop_hint}")
    parts.append(f"[任务]\n{spec}")
    parts.append("请直接实现这个任务, 只改必要的文件, 保持改动最小、可回滚。"
                 "实现完成后用一句话总结你改了哪些文件、做了什么。")
    return "\n\n".join(parts)


async def run_task(*, spec: str, sop_hint: str = "", constraint_text: str = "",
                   workdir: str, model: str = "", dev_id: str = "") -> dict[str, Any]:
    """让 claude 在 workdir 写码。返回 {ok, paused, stopped, claude_status, output, error}。

    - STOP: 提交前/轮询中检测 dev_state.is_stopped() → agent_cancel 真杀 + 返回 stopped。
    - 配额: agent_hands 透传 quota_hit(或 stderr 像配额)→ 返回 paused(上游存档暂停, 不算失败)。
    """
    from . import dev_state
    if dev_state.is_stopped():
        return {"ok": False, "stopped": True, "error": "已停止(STOP)"}
    prompt = _build_prompt(spec=spec, sop_hint=sop_hint, constraint_text=constraint_text)
    try:
        sub = await asyncio.to_thread(
            bee_clients.agent_task, prompt,
            workdir=workdir, yolo_mode=True, model=model or _CODE_MODEL)
    except Exception as e:
        return {"ok": False, "error": f"agent_task 提交失败: {type(e).__name__}: {str(e)[:200]}"}
    task_id = sub.get("task_id")
    if not task_id:
        return {"ok": False, "error": f"agent_task 无 task_id: {str(sub)[:200]}"}

    dev_state.register_task(dev_id, task_id)
    try:
        waited = 0.0
        last: dict[str, Any] = {}
        while waited < _MAX_WAIT:
            await asyncio.sleep(_POLL_INTERVAL)
            waited += _POLL_INTERVAL
            if dev_state.is_stopped():
                try:
                    await asyncio.to_thread(bee_clients.agent_cancel, task_id)
                except Exception:
                    pass
                return {"ok": False, "stopped": True, "task_id": task_id,
                        "claude_status": "cancelled", "error": "已停止(STOP)"}
            try:
                last = await asyncio.to_thread(bee_clients.agent_status, task_id)
            except Exception:
                continue
            status = str(last.get("status") or "")
            if status in ("done", "failed", "error", "cancelled"):
                break
        status = str(last.get("status") or "timeout")
        output = (last.get("stdout_tail") or "")
        quota = status != "done" and (
            bool(last.get("quota_hit"))
            or _looks_like_quota((last.get("stderr_tail") or "") + "\n" + (last.get("error") or "")))
        return {
            "ok": status == "done",
            "paused": quota,
            "reason": "quota" if quota else "",
            "task_id": task_id,
            "claude_status": status,
            "output": output[-8000:],
            "error": (last.get("error") or last.get("stderr_tail") or "")[:1000] if status != "done" else "",
        }
    finally:
        dev_state.unregister_task(dev_id, task_id)


async def run_tests(*, workdir: str, test_cmd: list[str] | None) -> dict[str, Any]:
    """跑测试(白名单 exec)。test_cmd 为空则跳过(返回 skipped)。返回 {ran, passed, summary}。"""
    if not test_cmd:
        return {"ran": False, "passed": False, "summary": "未指定测试命令, 跳过"}
    try:
        res = await asyncio.to_thread(bee_clients.agent_exec, test_cmd, workdir=workdir, timeout=300)
    except Exception as e:
        return {"ran": True, "passed": False, "summary": f"测试执行失败: {type(e).__name__}: {str(e)[:200]}"}
    passed = bool(res.get("ok"))
    tail = ((res.get("stdout") or "") + "\n" + (res.get("stderr") or "")).strip()
    return {"ran": True, "passed": passed, "exit_code": res.get("exit_code"),
            "summary": tail[-3000:] or res.get("error", "")}
