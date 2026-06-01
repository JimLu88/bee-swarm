"""每天 20:00 CEO 梳理 — 读知识收件箱 → 去重/提炼 → 写进 bee-memory.

流程:
  1. 按 (mode_id, persona_id) 分组 pending 收件
  2. 每组喂给 CEO/便宜模型: 去广告/去重/提炼成 N 条"可长期记的知识点"
  3. 留下的写进 bee-memory layer=trend (importance 1-3, 会随遗忘曲线衰减,
     kind_priority 低于 book — 联网新知是"次级知识", 不盖过人设的经典书)
  4. 全部处理过的收件标记 digested

成本: 每组 1 次 LLM 调用 (deepseek ~¥0.5). 单次 run 限 MAX_GROUPS 组.
模型: 默认 deepseek-chat 省钱; BEE_DIGEST_MODEL env 可改 (用户的 CEO 旗舰).

为什么用 layer=trend 而非 book:
  联网搜来的是"时效新知", 不是经过验证的经典. 给它 trend 层 (importance 2, 90 天衰减),
  既能被召回用上, 又不会永久占据知识库、不会盖过人设手灌的 30/50/80 本经典书.
  CEO 若判定某条特别重要 (importance=3) 会衰减得慢一些.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
import uuid
from typing import Any

from . import inbox

# 单次 run 限流
MAX_GROUPS = 12
MAX_ITEMS_PER_GROUP = 12
MAX_KEEP_PER_GROUP = 6


def _digest_conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(inbox.DB_PATH))
    c.execute(
        """CREATE TABLE IF NOT EXISTS digest_log (
            id TEXT PRIMARY KEY, ts INTEGER, mode_id TEXT, persona_id TEXT,
            raw_in INTEGER, kept INTEGER, note TEXT
        )"""
    )
    c.row_factory = sqlite3.Row
    return c


def _log(mode_id: str, persona_id: str, raw_in: int, kept: int, note: str = "") -> None:
    try:
        with _digest_conn() as c:
            c.execute(
                "INSERT INTO digest_log VALUES (?,?,?,?,?,?,?)",
                (f"dg-{uuid.uuid4().hex[:10]}", int(time.time()), mode_id, persona_id,
                 raw_in, kept, note[:500]),
            )
    except Exception:
        pass


def _parse_json_loose(text: str) -> dict[str, Any] | None:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
        t = t.strip()
    try:
        return json.loads(t)
    except Exception:
        s, e = t.find("{"), t.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(t[s:e + 1])
            except Exception:
                return None
    return None


async def _ceo_distill(mode_id: str, persona_id: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    model = os.environ.get("BEE_DIGEST_MODEL", "deepseek/deepseek-chat")
    fb = os.environ.get(
        "BEE_DIGEST_FALLBACK",
        "anthropic/claude-sonnet-4-6,ollama/deepseek-r1:8b",
    ).split(",")
    try:
        from ..llm.litellm_client import litellm_client
    except Exception:
        return None

    snippets = []
    for i, it in enumerate(items[:MAX_ITEMS_PER_GROUP], 1):
        snippets.append(
            f"[{i}] 标题: {it.get('title', '')}\n"
            f"    来源: {it.get('source_url', '') or it.get('domain', '')}\n"
            f"    内容: {str(it.get('content', ''))[:1200]}"
        )
    raw_block = "\n\n".join(snippets)

    prompt = f"""你是 H-SEMAS 的 CEO 知识策展员。下面是「{mode_id}」场景今天联网搜索抓回的原始片段。
请你梳理: 去广告/导航/重复/无信息量的, 把**真正有价值的新知识**提炼成可长期记忆的知识点。

原始片段 (共 {len(items)} 条):
{raw_block}

要求:
- 最多保留 {MAX_KEEP_PER_GROUP} 条最有价值的知识点 (宁缺毋滥, 没价值就少留甚至 0 条)
- 每条 title 一句话概括, content 150-350 字提炼精华 (事实/数据/方法, 不要套话)
- importance: 1=一般时效信息 2=较有用 3=重要且较持久 (大多数给 1-2)
- 合并讲同一件事的多个片段为 1 条

只输出 strict JSON:
{{
  "points": [
    {{"title": "<一句话>", "content": "<150-350字>", "importance": 2, "source_url": "<最相关来源,可空>"}}
  ]
}}
没有任何值得留的就输出 {{"points": []}}。只输出 JSON。
"""
    try:
        resp = await litellm_client.complete(model=model, fallbacks=fb, prompt=prompt,
                                              system="Output ONLY valid JSON.")
    except Exception:
        return None
    return _parse_json_loose(resp.text)


def _process_group(mode_id: str, dept_id: str, persona_id: str,
                   items: list[dict[str, Any]]) -> int:
    """提炼一组 → 写 bee-memory. 返回写入条数."""
    data = asyncio.run(_ceo_distill(mode_id, persona_id, items))
    ids = [str(it["id"]) for it in items]
    if data is None:
        # LLM 失败: 不标记 digested, 留着下次再试 (但记一条失败日志)
        _log(mode_id, persona_id, len(items), 0, "llm_failed")
        return 0
    points = data.get("points") or []
    try:
        from ..persona.knowledge_store import add_knowledge
    except Exception:
        inbox.mark(ids, "digested")
        return 0
    written = 0
    today = time.strftime("%Y-%m-%d")
    for p in points[:MAX_KEEP_PER_GROUP]:
        title = str(p.get("title") or "").strip()
        content = str(p.get("content") or "").strip()
        if not title or len(content) < 20:
            continue
        try:
            imp = int(p.get("importance") or 2)
        except Exception:
            imp = 2
        imp = max(1, min(imp, 3))
        result = add_knowledge(
            layer="trend",
            mode_id=mode_id,
            persona_id=persona_id,
            dept_id=dept_id,
            title=title,
            content=content,
            source_url=str(p.get("source_url") or ""),
            importance=imp,
            extra_meta={"source": "web", "auto_learned": True, "digest_date": today},
        )
        if "error" not in result:
            written += 1
    inbox.mark(ids, "digested")
    _log(mode_id, persona_id, len(items), written, f"points={len(points)}")
    return written


def run_digest(max_groups: int = MAX_GROUPS) -> dict[str, Any]:
    """主入口. 20:00 cron + 手动触发都调这个 (sync, 内部 asyncio.run 调 LLM).

    把 pending 收件按 (mode_id, persona_id) 分组, 逐组让 CEO 提炼入库.
    """
    now = int(time.time())
    pending = inbox.list_pending(limit=400)
    if not pending:
        return {"task": "knowledge_digest", "status": "empty", "ts": now,
                "groups": 0, "written": 0}

    # 按 (mode_id, persona_id) 分组
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    dept_of: dict[tuple[str, str], str] = {}
    for it in pending:
        key = (str(it.get("mode_id")), str(it.get("persona_id")))
        groups.setdefault(key, []).append(it)
        dept_of.setdefault(key, str(it.get("dept_id") or ""))

    processed = 0
    total_written = 0
    results: list[dict[str, Any]] = []
    for (mode_id, persona_id), items in groups.items():
        if processed >= max_groups:
            break
        dept_id = dept_of.get((mode_id, persona_id), "")
        written = _process_group(mode_id, dept_id, persona_id, items)
        total_written += written
        processed += 1
        results.append({
            "mode_id": mode_id, "persona_id": persona_id,
            "raw": len(items), "written": written,
        })

    return {
        "task": "knowledge_digest",
        "status": "ok",
        "ts": now,
        "groups_total": len(groups),
        "groups_processed": processed,
        "written": total_written,
        "results": results,
    }
