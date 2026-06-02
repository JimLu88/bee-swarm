"""planner — 意图理解 + 优化 SPEC + 拆分 DevTask (Spec→Plan→Tasks 骨架).

流程: 用户原始需求 → prompt_optimizer 整理成 SPEC → LLM 拆成可独立验证的 DevTask 列表。
单需求若很简单, 会拆成 1 个 task(也合法)。失败兜底: 拆不出就退化为单 task = 整个 SPEC。
DevTask: {task_id, title, kind(feature|bugfix|refactor|test), spec, files_hint[], depends_on[]}.
"""

from __future__ import annotations

import json
import os
from typing import Any

from . import prompt_optimizer

_MODEL = os.environ.get("BEE_DEV_PLANNER_MODEL", "deepseek/deepseek-chat")
MAX_TASKS = 8

_SYSTEM = (
    "你是开发总规划师。把 SPEC 拆成最少数量、可独立验证的开发任务(能少则少, 简单需求就 1 个)。"
    "只输出 JSON 数组, 每项: "
    '{"title":"简短标题","kind":"feature|bugfix|refactor|test","spec":"该任务要做什么(可独立执行)",'
    '"files_hint":["可能涉及的文件/目录"],"depends_on":[]}。 '
    "depends_on 填本数组里它依赖的其它任务的 0 基序号(无依赖留空)。不要任何解释, 只要 JSON 数组。"
)


def _parse_tasks(text: str) -> list[dict[str, Any]]:
    s = (text or "").strip()
    a, b = s.find("["), s.rfind("]")
    if a == -1 or b == -1 or b < a:
        return []
    try:
        arr = json.loads(s[a:b + 1])
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for i, it in enumerate(arr if isinstance(arr, list) else []):
        if not isinstance(it, dict) or not str(it.get("spec") or it.get("title") or "").strip():
            continue
        kind = str(it.get("kind", "feature"))
        if kind not in ("feature", "bugfix", "refactor", "test"):
            kind = "feature"
        deps = [int(d) for d in (it.get("depends_on") or []) if isinstance(d, (int, float))]
        out.append({
            "task_id": f"t{i + 1}",
            "title": str(it.get("title", "") or f"任务{i + 1}")[:120],
            "kind": kind,
            "spec": str(it.get("spec") or it.get("title") or "").strip(),
            "files_hint": [str(x) for x in (it.get("files_hint") or [])][:12],
            "depends_on": [f"t{d + 1}" for d in deps if 0 <= d < MAX_TASKS],
        })
        if len(out) >= MAX_TASKS:
            break
    return out


async def plan(raw_request: str, *, context: str = "") -> dict[str, Any]:
    """返回 {spec, tasks}. tasks 至少 1 个。"""
    spec = await prompt_optimizer.optimize(raw_request, context=context)
    spec = spec or (raw_request or "").strip()
    tasks: list[dict[str, Any]] = []
    try:
        from ..llm.litellm_client import litellm_client
        resp = await litellm_client.complete(
            model=_MODEL, fallbacks=[], system=_SYSTEM,
            prompt=f"[SPEC]\n{spec}\n\n拆成开发任务 JSON 数组:",
        )
        tasks = _parse_tasks(resp.text)
    except Exception:
        tasks = []
    if not tasks:
        # 兜底: 整个 SPEC 当单任务
        tasks = [{"task_id": "t1", "title": (raw_request or "开发任务")[:120],
                  "kind": "feature", "spec": spec, "files_hint": [], "depends_on": []}]
    return {"spec": spec, "tasks": tasks}
