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

SHORT_THRESHOLD = int(os.environ.get("BEE_CLARIFY_MIN_CHARS", "12"))  # 短问题也常值得澄清(如"父亲节送啥礼物"); 真无歧义 LLM 会返空
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


# 前端可渲染的控件类型
_ALLOWED_TYPES = {"chips", "slider", "segmented", "range", "rank", "quick", "text"}

# AI 生成失败时的兜底结构化问题(通用, 任何场景可用)
_FALLBACK_QUESTIONS: list[dict[str, Any]] = [
    {"id": "focus", "type": "segmented", "prompt": "你更看重哪一面?",
     "why": "决定整体方向", "options": ["实用 / 效果", "情感 / 体验"]},
    {"id": "prefs", "type": "chips", "prompt": "有哪些偏好或限制?(可多选)",
     "why": "缩小范围", "options": ["预算有限", "时间紧", "新手友好", "追求品质", "越简单越好"],
     "multi": True},
    {"id": "depth", "type": "segmented", "prompt": "想要的回答形式?",
     "why": "控制深度", "options": ["快速结论", "详细方案"]},
]


def _normalize_q(raw: dict[str, Any], idx: int) -> dict[str, Any] | None:
    """把 LLM 产出的一条问题清洗成前端安全结构 (缺字段给默认, 非法类型纠正/丢弃)."""
    if not isinstance(raw, dict):
        return None
    qtype = str(raw.get("type") or "").strip().lower()
    if qtype not in _ALLOWED_TYPES:
        qtype = "chips" if raw.get("options") else "text"
    prompt = str(raw.get("prompt") or raw.get("question") or "").strip()
    if not prompt:
        return None
    q: dict[str, Any] = {
        "id": (str(raw.get("id") or f"q{idx}").strip() or f"q{idx}")[:40],
        "type": qtype,
        "prompt": prompt[:120],
        "why": str(raw.get("why") or "").strip()[:60],
    }
    opts = raw.get("options")
    if isinstance(opts, list):
        q["options"] = [str(o).strip()[:30] for o in opts if str(o).strip()][:8]
    if qtype == "chips":
        q["multi"] = bool(raw.get("multi", True))
    if qtype in ("slider", "range"):
        try:
            q["min"] = int(raw.get("min", 0))
            q["max"] = int(raw.get("max", 100))
            q["default"] = int(raw.get("default", (q["min"] + q["max"]) // 2))
        except Exception:
            q["min"], q["max"], q["default"] = 0, 100, 50
        q["min_label"] = str(raw.get("min_label") or "").strip()[:12]
        q["max_label"] = str(raw.get("max_label") or "").strip()[:12]
        q["unit"] = str(raw.get("unit") or "").strip()[:6]
    # 需要 options 的控件却没给 → 无意义, 丢弃
    if qtype in ("chips", "segmented", "rank", "quick") and not q.get("options"):
        return None
    return q


async def _gen_questions(task: str) -> list[dict[str, Any]]:
    """让便宜模型产出【结构化】澄清问题 (带控件 type), 0-5 个; 失败回退兜底."""
    try:
        from .llm.litellm_client import litellm_client
        resp = await litellm_client.complete(
            model=CHEAP_MODEL,
            prompt=(
                f"用户问题: {task[:1500]}\n\n"
                "你是 H-SEMAS 意图澄清助手. 在系统调用 8 位 AI 顾问深入回答前, "
                "你要设计几个【结构化小问题】让用户快速点选, 把模糊问题变精准.\n\n"
                "可用控件 type:\n"
                "- chips: 多选标签(给 options, multi=true) — 兴趣/属性, 如喜欢的类型\n"
                "- segmented: 二到四选一(给 options) — 快速取向, 如 实用 vs 情感\n"
                "- slider: 程度滑杆(min/max/min_label/max_label/default) — 如 对新潮的接受度 0-100\n"
                "- range: 数值/预算(min/max/default/unit) — 如 预算 ¥\n"
                "- rank: 优先级排序(给 options) — 让用户排重要度\n"
                "- quick: 开放追问+建议答(给 options 当快捷答, 用户也可自填)\n\n"
                "原则:\n"
                "- 只问【会显著改变答案方向】的; 默认 3 个, 最多 5 个; 完全没歧义则空数组\n"
                "- 每条配最贴合的控件; chips/quick 给 4-7 个 options; slider 给两端 label\n"
                "- options 用中文短词; 每条加 why(为什么问, 一句话)\n\n"
                "严格输出 JSON(无 markdown): "
                '{"questions":[{"id":"interests","type":"chips","prompt":"爸爸平时喜欢哪些?",'
                '"why":"决定礼物方向","options":["钓鱼","喝茶","书法","数码","养生"],"multi":true}]}'
            ),
        )
        text = (resp.text or "").strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        obj = json.loads(text)
        raw_qs = obj.get("questions") if isinstance(obj, dict) else None
        if not isinstance(raw_qs, list):
            return _FALLBACK_QUESTIONS
        out: list[dict[str, Any]] = []
        for i, rq in enumerate(raw_qs[:5]):
            nq = _normalize_q(rq, i)
            if nq:
                out.append(nq)
        return out or _FALLBACK_QUESTIONS
    except Exception:
        return _FALLBACK_QUESTIONS


class ProbeRequest(BaseModel):
    task: str


class ProbeResponse(BaseModel):
    clarify: bool
    reason: str
    session_id: str = ""
    # 结构化问题: 每项 {id,type,prompt,why,options?,multi?,min?,max?,default?,...}
    questions: list[dict[str, Any]] = Field(default_factory=list)


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
    answers: list[str] = Field(default_factory=list)  # 每条 = 该问题已格式化好的可读答案串(前端拼)
    extra: str = ""  # 末尾固定"还有什么补充想说的"自由文本


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
    parts: list[str] = []
    for q, a in zip(qs, ans):
        a = (a or "").strip()
        if not a:
            continue
        prompt = q.get("prompt", "") if isinstance(q, dict) else str(q)
        parts.append(f"Q: {prompt}\nA: {a}")
    extra = (req.extra or "").strip()
    if extra:
        parts.append(f"补充: {extra}")
    qa = "\n".join(parts)
    final = f"{s['task']}\n\n[澄清回答]\n{qa}" if qa else s["task"]
    _sessions.pop(req.session_id, None)
    return ResolveResponse(task_final=final, used=len(parts))
