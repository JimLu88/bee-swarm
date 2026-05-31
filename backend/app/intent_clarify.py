"""v6-F 意图澄清节点 (SAGE-Agent EVPI 模式简化版).

策略:
- 任务 <50 字 → 跳过, 直出
- 任务 ≥50 字 但简单关键词命中 → 跳过 (如 '查询/帮我看下/简单问下')
- 否则 → 用便宜模型 (DeepSeek) 生成 1-3 个澄清问题

API:
- POST /api/intent/probe   {task} → {clarify, session_id?, questions?, reason}
- POST /api/intent/resolve {session_id, answers} → {task_final}

session 内存 LRU, 30 分钟过期, 不持久化.
"""
from __future__ import annotations
import os
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/intent", tags=["intent"])

SHORT_THRESHOLD = int(os.environ.get("BEE_CLARIFY_MIN_CHARS", "50"))
SESSION_TTL = 30 * 60
CHEAP_MODEL = os.environ.get("BEE_CLARIFY_MODEL", "deepseek/deepseek-chat")

_SIMPLE_PATTERNS = (
    "查一下", "查下", "帮我看下", "简单问", "一句话", "直接说",
    "what is", "look up", "quick", "tldr",
)

_sessions: dict[str, dict[str, Any]] = {}


def _gc_sessions() -> None:
    now = time.time()
    for k in list(_sessions.keys()):
        if now - _sessions[k]["ts"] > SESSION_TTL:
            _sessions.pop(k, None)


def _needs_clarify(task: str) -> tuple[bool, str]:
    t = (task or "").strip()
    if len(t) < SHORT_THRESHOLD:
        return False, f"短任务 (<{SHORT_THRESHOLD} 字), 跳过澄清"
    low = t.lower()
    if any(p in low for p in _SIMPLE_PATTERNS):
        return False, "命中简单查询关键词, 跳过澄清"
    return True, "长任务, 触发澄清以提升精度"


async def _gen_questions(task: str) -> list[str]:
    try:
        from .llm.litellm_client import litellm_client
        resp = await litellm_client.complete(
            model=CHEAP_MODEL,
            prompt=(
                f"用户问题: {task[:1500]}\n\n"
                "你是 H-SEMAS 意图澄清助手. 在系统真正调用 6 位 AI 顾问之前, "
                "你需要决定: 这个问题里有没有【会显著影响答案方向】的歧义点?\n\n"
                "原则 (SAGE-Agent EVPI):\n"
                "- 只问能改变答案方向的问题; 不问无关紧要的细节\n"
                "- 最多 3 个; 能 1 个就 1 个; 0 个完全没歧义就返空数组\n"
                "- 每个问题要让用户能用一句话或选项回答, 不要开放式\n\n"
                "输出 strict JSON (无 markdown): "
                '{"questions": ["问题1", "问题2"]}'
            ),
        )
        text = (resp.text or "").strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        obj = json.loads(text)
        qs = obj.get("questions") or []
        return [str(q).strip() for q in qs if str(q).strip()][:3]
    except Exception:
        return [
            "你期望的输出形式是: 一句话结论 / 详细方案 / 步骤清单 / 对比表格?",
            "你的时间预算: 想要快速回答 / 还是允许多部门深入辩论?",
        ]


class ProbeRequest(BaseModel):
    task: str


class ProbeResponse(BaseModel):
    clarify: bool
    reason: str
    session_id: str = ""
    questions: list[str] = Field(default_factory=list)


@router.post("/probe", response_model=ProbeResponse)
async def probe(req: ProbeRequest) -> ProbeResponse:
    _gc_sessions()
    need, reason = _needs_clarify(req.task)
    if not need:
        return ProbeResponse(clarify=False, reason=reason)
    questions = await _gen_questions(req.task)
    if not questions:
        return ProbeResponse(clarify=False, reason="LLM 判断无显著歧义")
    sid = "ic-" + uuid.uuid4().hex[:12]
    _sessions[sid] = {"ts": time.time(), "task": req.task, "questions": questions}
    return ProbeResponse(clarify=True, reason=reason, session_id=sid, questions=questions)


class ResolveRequest(BaseModel):
    session_id: str
    answers: list[str] = Field(default_factory=list)


class ResolveResponse(BaseModel):
    task_final: str
    used: int


@router.post("/resolve", response_model=ResolveResponse)
async def resolve(req: ResolveRequest) -> ResolveResponse:
    _gc_sessions()
    s = _sessions.get(req.session_id)
    if not s:
        raise HTTPException(404, f"session {req.session_id} not found or expired")
    qs = s["questions"]
    ans = req.answers[: len(qs)]
    qa = "\n".join(f"Q: {q}\nA: {a}" for q, a in zip(qs, ans) if a.strip())
    final = f"{s['task']}\n\n[澄清回答]\n{qa}" if qa else s["task"]
    _sessions.pop(req.session_id, None)
    return ResolveResponse(task_final=final, used=len([a for a in ans if a.strip()]))
