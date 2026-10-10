"""answer_lane — 轻型问答车道: 联网搜索 → 带引用直答 (不开部门/不爬媒体/不绕多轮).

借 AEO 思路(search → 综合 → 带来源 + 查无可靠来源就明说, 不编), 走单次搜索+单次合成,
比走 ceo_only(会带 KB/书/高德/媒体爬虫)更轻更快。
panse-aeo 的结构化合成/事实校验后续可 vendor 进来做更强版本(跨项目, 暂不硬依赖)。
"""
from __future__ import annotations

import json

from .models import DecisionSummary, StreamEvent
from .tools import execute_tool
from .llm.litellm_client import litellm_client
from .llm.router import router as llm_router
from .stream_bus import bus


async def run_answer(*, decision_id: str, task: str, mode_id: str, mode_label: str) -> DecisionSummary:
    """问答车道主链路: 联网搜索 → 带引用简洁直答(查无可靠来源就明说)."""
    bus.publish(StreamEvent(type="decision_started", decision_id=decision_id,
                            payload={"task": task, "mode_id": mode_id, "mode_label": mode_label, "lane": "answer"}))
    bus.publish(StreamEvent(type="dispatcher_ready", decision_id=decision_id,
                            payload={"level": "answer", "note": "联网快答", "department_count": 0, "route": "answer"}))

    # 0) 书库优先 (功能#3): 1735 本真书已灌, 免费且权威 — 先查书, 再上网
    books_text, books_refs = "", []
    try:
        from .books_rag.pipeline import retrieve_context_with_refs
        books_text, books_refs = retrieve_context_with_refs(task, scenario=None, k=3, max_chars=1000)
        if books_text:
            bus.publish(StreamEvent(type="answer_books", decision_id=decision_id,
                                    payload={"refs": len(books_refs)}))
    except Exception:
        books_text, books_refs = "", []

    # 1) 联网搜索 (只读, 失败/无 key 自动降级到纯模型答)
    digest = ""
    try:
        res = execute_tool("web_search", {"query": task}, allow_sensitive=False)
        if res.get("ok"):
            digest = json.dumps(res.get("result") or {}, ensure_ascii=False)[:6000]
            bus.publish(StreamEvent(type="answer_searched", decision_id=decision_id,
                                    payload={"ok": True, "chars": len(digest)}))
    except Exception:
        digest = ""

    # 2) 合成 (带来源 + 可信度刹车; 书库片段优先于网页)
    books_block = f"\n\n[书库命中(已灌入的真书, 优先采用并以《书名》标注)]:\n{books_text}" if books_text else ""
    if digest or books_text:
        prompt = (
            "根据下面的资料, 用中文简洁回答用户问题(直给结论, 一般 3-8 句)。"
            "引用真书的事实用《书名》标注, 引用网页的用 [来源] 标注链接; "
            "若资料不足以可靠回答, 明确说\"没查到足够可靠的来源\", 不要编造。"
            f"{books_block}\n\n"
            f"联网搜索结果(JSON):\n{digest or '(无)'}\n\n用户问题: {task}"
        )
    else:
        prompt = (
            "用中文简洁回答用户问题(当前没有联网资料, 仅凭常识; 不确定就直说不确定, 不要编造)。\n\n"
            f"用户问题: {task}"
        )
    try:
        choice = llm_router.pick_for_dept("ceo") if hasattr(llm_router, "pick_for_dept") else None
        model = getattr(choice, "model", "") if choice else ""
        ans = (await litellm_client.complete(model=model, fallbacks=llm_router.fallbacks(), prompt=prompt)).text or ""
    except Exception as e:
        ans = f"[问答失败: {type(e).__name__}: {e}]"
    ans = ans.strip() or "(没有产出)"
    if not digest:
        ans += "\n\n> ⚠ 未联网取到资料(可能未配搜索 key 或搜索失败), 以上为模型常识回答, 请自行核实。"

    summary = DecisionSummary(
        decision_id=decision_id, task=task, mode_id=mode_id, mode_label=mode_label,
        ceo_decision=ans,
        dispatcher={"level": "answer", "lane": "answer", "department_count": 0, "route": "answer"},
        books_refs=books_refs,
    )
    bus.publish(StreamEvent(type="decision_done", decision_id=decision_id,
                            payload={"summary": summary.model_dump()}))
    return summary
