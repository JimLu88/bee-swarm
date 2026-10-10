"""action_lane — 执行(act)车道 v2: CEO 监督的有界工具执行环.

设计:
- 多步循环(上限 MAX_ITERS): 每步 LLM(执行官) 看"任务 + 已做步骤与结果" → 只规划【下一步】.
  只读工具(SAFE)自动执行, 结果回灌给下一步 = "每步返回 CEO 给新意见"的监督循环.
- 有副作用工具(SENSITIVE: 发消息/点击/输入/派 worker)永不自动执行, 跨步收集为"待你确认".
- 循环结束做一次最终综合(CEO 收尾结论). 返回 DecisionSummary, 复用结果面板; 经 bus 驱动前端流.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from .models import DecisionSummary, StreamEvent
from .tools import list_tools, execute_tool, extract_tool_calls
from .llm.litellm_client import litellm_client
from .llm.router import router as llm_router
from .stream_bus import bus

# 只读工具(自动执行); 其余(有副作用)默认列为待确认, 不自动跑
SAFE_TOOLS = {"scrape", "web_search", "office", "ocr", "describe", "healthcheck", "locate", "uia_find"}
# 执行层#1 收敛化: 上限 env 可调(默认6, 原死磕3轮); 靠"自然完成(空tool_calls)/卡死检测"提前停
MAX_ITERS = int(os.environ.get("BEE_ACT_MAX_ITERS", "6"))
_RESULT_CLIP = 1500    # 回灌给下一步的单条结果截断


def _exec_with_retry(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """执行层#5: SAFE 工具失败自动重试一次(0.5s 退避), 吸收偶发网络抖动; rate_limited 不重试。"""
    res = execute_tool(name, args, allow_sensitive=False)
    if not res.get("ok") and not res.get("rate_limited"):
        time.sleep(0.5)
        res = execute_tool(name, args, allow_sensitive=False)
    return res


def _tools_brief() -> str:
    lines: list[str] = []
    for t in list_tools(include_sensitive=True):
        flag = "只读" if t.get("safety") == "safe" else "⚠副作用(需确认)"
        lines.append(f"- {t['name']} ({flag}): {t['description']}")
    return "\n".join(lines)


def _ceo_model() -> str:
    try:
        choice = llm_router.pick_for_dept("ceo") if hasattr(llm_router, "pick_for_dept") else None
        return getattr(choice, "model", "") if choice else ""
    except Exception:
        return ""


async def _llm(prompt: str) -> str:
    try:
        return (await litellm_client.complete(model=_ceo_model(), fallbacks=llm_router.fallbacks(), prompt=prompt)).text or ""
    except Exception as e:
        return f"[LLM 调用失败: {type(e).__name__}: {e}]"


def _history_block(history: list[dict[str, Any]]) -> str:
    if not history:
        return "(还没执行任何步骤)"
    out: list[str] = []
    for i, h in enumerate(history, 1):
        out.append(f"步骤{i} 思路: {str(h.get('thought', ''))[:300]}")
        for r in h.get("ran", []):
            out.append(f"  · {r['name']} {'成功' if r['ok'] else '失败'}: {r['digest']}")
    return "\n".join(out)


async def run_action(*, decision_id: str, task: str, mode_id: str, mode_label: str) -> DecisionSummary:
    bus.publish(StreamEvent(type="decision_started", decision_id=decision_id,
                            payload={"task": task, "mode_id": mode_id, "mode_label": mode_label, "lane": "act"}))
    bus.publish(StreamEvent(type="dispatcher_ready", decision_id=decision_id,
                            payload={"level": "act", "note": "执行车道(CEO监督循环)", "department_count": 0, "route": "act"}))

    tools_text = _tools_brief()
    history: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    last_sig: str | None = None   # 执行层: 卡死检测(连续两轮规划同一组动作 = 原地踏步)

    for it in range(MAX_ITERS):
        prompt = (
            "你是「执行官」, 用工具一步步完成用户的操作类任务。每轮只规划【下一步】, 看到上一步结果再决定下一步。\n"
            "可用工具:\n" + tools_text + "\n\n"
            f"用户任务: {task}\n\n"
            f"已执行步骤与结果:\n{_history_block(history)}\n\n"
            "请输出:\n"
            "1) 一句话说清【这一步】要做什么(中文)。\n"
            '2) 末尾给严格 JSON: {"tool_calls":[{"tool":"工具名","args":{...}}]}。\n'
            "若任务已做完/无需更多动作, tool_calls 给空数组 []。标「副作用」的工具会被列给用户确认, 不会自动执行。\n"
        )
        text = await _llm(prompt)
        thought = text.split('{"tool_calls"', 1)[0].strip()
        calls = extract_tool_calls(text)

        # 卡死检测: 本轮规划的动作签名与上一轮完全相同 → 原地踏步, 提前停
        sig = json.dumps([[str(c.get("tool", "")), c.get("args") or {}] for c in calls],
                         ensure_ascii=False, sort_keys=True)
        if calls and sig == last_sig:
            bus.publish(StreamEvent(type="act_step", decision_id=decision_id,
                                    payload={"iter": it + 1, "thought": "(检测到重复动作, 提前收尾)", "ran": 0}))
            break
        last_sig = sig

        ran: list[dict[str, Any]] = []
        any_safe = False
        for c in calls:
            name = str(c.get("tool", ""))
            args = c.get("args") or {}
            if not isinstance(args, dict):
                args = {}
            if name in SAFE_TOOLS:
                any_safe = True
                res = _exec_with_retry(name, args)
                ok = bool(res.get("ok"))
                digest = ("成功 " + json.dumps(res.get("result") or {}, ensure_ascii=False)) if ok else str(res.get("error", ""))
                ran.append({"name": name, "ok": ok, "digest": digest[:_RESULT_CLIP]})
                bus.publish(StreamEvent(type="act_tool", decision_id=decision_id,
                                        payload={"tool": name, "ok": ok, "iter": it + 1}))
            elif name:
                pending.append({"tool": name, "args": args})

        history.append({"thought": thought, "ran": ran})
        bus.publish(StreamEvent(type="act_step", decision_id=decision_id,
                                payload={"iter": it + 1, "thought": thought[:200], "ran": len(ran)}))
        if not any_safe:
            break  # 没有可自动跑的下一步(完成 / 只剩待确认) → 结束监督循环

    # 最终 CEO 综合收尾
    final = await _llm(
        "你是「执行官」, 给用户一个简洁收尾报告(中文): 做了什么、结果如何、还差什么。不要客套, 不要 markdown 标题。\n\n"
        f"任务: {task}\n\n已执行步骤与结果:\n{_history_block(history)}\n\n"
        + (f"还有待用户确认的副作用动作: {json.dumps(pending, ensure_ascii=False)[:800]}\n" if pending else "")
    )

    parts = [final.strip() or "（执行完成）"]
    step_lines: list[str] = []
    for i, h in enumerate(history, 1):
        for r in h.get("ran", []):
            step_lines.append(f"- 步骤{i} `{r['name']}` {'✅' if r['ok'] else '❌'}")
    if step_lines:
        parts.append(f"\n## 🛠 已执行(只读, 共 {len(history)} 轮)\n" + "\n".join(step_lines))
    if pending:
        plines = [f"- `{p['tool']}` args={json.dumps(p['args'], ensure_ascii=False)[:160]}" for p in pending]
        parts.append("\n## ⏸ 待你确认(有副作用, 未自动执行)\n" + "\n".join(plines)
                     + "\n\n> 这些动作会真的对外产生影响(发消息/点击/输入/派 worker), 默认不自动跑; HITL 一键确认→真执行下一版接入。")
    if not step_lines and not pending:
        parts.append("\n(没有产生具体动作 — 可能更像问答, 试试「🔎 问答」车道。)")

    summary = DecisionSummary(
        decision_id=decision_id, task=task, mode_id=mode_id, mode_label=mode_label,
        ceo_decision="\n".join(parts),
        dispatcher={"level": "act", "lane": "act", "department_count": 0, "route": "act", "iters": len(history)},
    )
    bus.publish(StreamEvent(type="decision_done", decision_id=decision_id,
                            payload={"summary": summary.model_dump()}))
    return summary
