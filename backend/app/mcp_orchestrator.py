"""mcp_orchestrator — v13 #1 第②步: 决策前的"实时资料采集".

决策主链路在跑部门之前, 先看这个场景挂了哪些 MCP 工具(白名单, 已配 Key/URL),
让一个便宜模型判断"这道题要不要查、查什么", 真去调用, 把结果作为
「## 实时资料」拼进 task —— 这样所有部门 + CEO 都能看到最新事实, 而不用
把每个部门 prompt 改成 function-calling 循环 (provider 无关, 稳).

纪律:
- 整段 best-effort: 任一步失败都静默跳过, 绝不阻断决策 (env HSEMAS_MCP_FACTS=0 全关).
- 工具数受 mcp_tools.MAX_TOOLS_PER_SCENE 限 (防变笨); 实际调用再限 MAX_CALLS.
- 整体时间盒 (TOTAL_TIMEOUT), 超时就用已拿到的部分.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from . import mcp_client, mcp_tools

MAX_CALLS = 3            # 单次决策最多真调几次工具
PER_CALL_TIMEOUT = 20.0  # 单个工具调用超时
TOTAL_TIMEOUT = 35.0     # 采集总时间盒
_PLANNER_MODEL = os.environ.get("BEE_MCP_PLANNER_MODEL", "deepseek/deepseek-chat")


def enabled() -> bool:
    return os.environ.get("HSEMAS_MCP_FACTS", "1") != "0"


async def _candidate_tools(mode_id: str) -> list[dict[str, Any]]:
    """该场景白名单内、已启用且配齐的服务 → 展开成可调用工具清单 (附 server_id)."""
    servers = mcp_tools.tools_for_scene(mode_id)  # 已截到 MAX_TOOLS_PER_SCENE
    out: list[dict[str, Any]] = []
    for rt in servers:
        sid = rt.get("id", "")
        try:
            tools = await asyncio.wait_for(mcp_client.list_tools(sid), timeout=PER_CALL_TIMEOUT)
        except Exception:
            continue
        for t in tools:
            if not t.get("name"):
                continue
            out.append({
                "server": sid,
                "server_name": rt.get("name", sid),
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("input_schema") or {},
            })
    # 工具总量再设个软上限, 别把 planner 的上下文撑爆
    return out[:24]


def _build_planner_prompt(task: str, tools: list[dict[str, Any]]) -> str:
    lines = [
        "你是工具调度员。下面是一道用户任务和一批可用的实时工具。",
        "判断: 要回答好这道题, 需要调用哪些工具拿实时数据? (天气/股价/网页/文献/代码等)",
        "规则:",
        f"- 最多选 {MAX_CALLS} 个调用; 不需要实时数据就返回空数组 []。",
        "- 只能用下面列出的工具; 参数必须符合其 input_schema。",
        "- 只输出 JSON 数组, 形如 "
        '[{"server":"weather","tool":"get_weather","args":{"location":"Shanghai"}}], 不要任何解释。',
        "",
        f"用户任务: {task[:1200]}",
        "",
        "可用工具:",
    ]
    for t in tools:
        schema = json.dumps(t.get("input_schema", {}), ensure_ascii=False)[:400]
        lines.append(f'- server="{t["server"]}" tool="{t["name"]}" : {t.get("description","")[:160]} | 参数schema: {schema}')
    return "\n".join(lines)


def _parse_plan(text: str, valid: set[tuple[str, str]]) -> list[dict[str, Any]]:
    """从模型输出里抠出 JSON 数组, 过滤掉非法 (server,tool)."""
    s = (text or "").strip()
    a = s.find("[")
    b = s.rfind("]")
    if a == -1 or b == -1 or b < a:
        return []
    try:
        arr = json.loads(s[a:b + 1])
    except Exception:
        return []
    plan: list[dict[str, Any]] = []
    for it in arr if isinstance(arr, list) else []:
        if not isinstance(it, dict):
            continue
        srv = str(it.get("server", ""))
        tool = str(it.get("tool", ""))
        if (srv, tool) not in valid:
            continue
        args = it.get("args") if isinstance(it.get("args"), dict) else {}
        plan.append({"server": srv, "tool": tool, "args": args})
        if len(plan) >= MAX_CALLS:
            break
    return plan


async def gather_facts(*, mode_id: str, task: str) -> tuple[str, list[dict[str, Any]]]:
    """返回 (facts_block, calls_meta). facts_block 为空串=没采集到/未启用."""
    if not enabled():
        return "", []
    try:
        return await asyncio.wait_for(_gather_inner(mode_id, task), timeout=TOTAL_TIMEOUT)
    except Exception:
        return "", []


async def _gather_inner(mode_id: str, task: str) -> tuple[str, list[dict[str, Any]]]:
    tools = await _candidate_tools(mode_id)
    if not tools:
        return "", []
    valid = {(t["server"], t["name"]) for t in tools}

    # 让便宜模型挑工具+定参数
    from .llm.litellm_client import litellm_client
    plan_resp = await litellm_client.complete(
        model=_PLANNER_MODEL,
        fallbacks=[],
        prompt=_build_planner_prompt(task, tools),
        system="你只输出 JSON 数组, 不要任何多余文字。",
    )
    plan = _parse_plan(plan_resp.text, valid)
    if not plan:
        return "", []

    # 并行真调用
    async def _one(call: dict[str, Any]) -> dict[str, Any]:
        try:
            res = await asyncio.wait_for(
                mcp_client.call_tool(call["server"], call["tool"], call["args"]),
                timeout=PER_CALL_TIMEOUT,
            )
            return {**call, "ok": True, "result": str(res)[:1500]}
        except Exception as e:
            return {**call, "ok": False, "result": f"{type(e).__name__}: {str(e)[:120]}"}

    results = await asyncio.gather(*[_one(c) for c in plan])
    good = [r for r in results if r.get("ok") and r.get("result")]
    if not good:
        return "", results

    name_by_sid = {t["server"]: t["server_name"] for t in tools}
    lines = ["## 实时资料 (MCP 工具采集, 已是最新)"]
    for r in good:
        label = name_by_sid.get(r["server"], r["server"])
        lines.append(f"- 【{label} · {r['tool']}】{r['result']}")
    lines.append("(以上为实时查询结果, 比记忆中的旧数据优先采信。)")
    return "\n".join(lines), results
