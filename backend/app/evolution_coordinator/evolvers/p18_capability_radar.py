"""p18 能力雷达 (Capability Radar) — 比 p12(修 bug) 高一层: 主动盯世界前沿, 找出本系统
「落后 / 可加插件 / 可加功能 / 该升框架」的地方, 生成**大白话**升级提案 → 全部进待审池, 你同意才动.

闭环:
  ① 自我能力快照 (capability_manifest)
  ② 扫前沿 (复用 p17 趋势 + p14 已发现未采纳的 skill + p13 模型候选)
  ③ LLM 差距分析 → 结构化升级提案 (类型/通俗解释/收益/工作量/风险/方案)
  ④ 每条 submit_change 进 /api/pending 待审池 (kind=capability_*), 去重避免天天刷屏

全部 best-effort: 无网/无 Key/抽取失败 → 返回 no_op, 绝不抛异常. 永远只提案, 绝不自动改代码.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path
from typing import Any

_APP = Path(__file__).resolve().parents[2]          # backend/app
_EVO_DB = _APP / "evolution_coordinator" / "data" / "evolution_history.sqlite"
_PENDING_DB = _APP / "data" / "pending_changes.sqlite"

_MODEL = "openai/deepseek-v4-pro"  # 差距分析要点推理力, 用 pro (比 opus 省, 比 flash 强)
_MAX_PROPOSALS = 5


def _frontier() -> str:
    """汇总前沿信号: 趋势(p17) + 已发现未采纳的插件(p14) + 模型候选(p13)."""
    parts: list[str] = []

    # 1) 趋势 (复用 p17 的抓取)
    try:
        from .p17_trend_monitor import _fetch_trends  # type: ignore
        trends = _fetch_trends() or {}
        for src, items in trends.items():
            titles = [str(it.get("title") or it.get("name") or "")[:80] for it in (items or [])][:6]
            titles = [t for t in titles if t]
            if titles:
                parts.append(f"[{src} 趋势] " + " | ".join(titles))
    except Exception:
        pass

    # 2) p14 已发现但未采纳的 skill/MCP 插件
    try:
        c = sqlite3.connect(str(_EVO_DB))
        rows = c.execute(
            "SELECT repo, stars, description FROM skill_candidates "
            "WHERE status NOT IN ('active','adopted','rejected') ORDER BY stars DESC LIMIT 8"
        ).fetchall()
        c.close()
        for repo, stars, desc in rows:
            parts.append(f"[候选插件 ★{stars}] {repo}: {str(desc or '')[:80]}")
    except Exception:
        pass

    # 3) p13 模型候选
    try:
        c = sqlite3.connect(str(_EVO_DB))
        rows = c.execute(
            "SELECT model_id, source FROM model_candidates WHERE status='candidate' LIMIT 6"
        ).fetchall()
        c.close()
        for mid, src in rows:
            parts.append(f"[新模型候选] {mid} (来源 {src})")
    except Exception:
        pass

    return "\n".join(parts)


_PROMPT = (
    "你是一名资深技术战略顾问。下面是一套 AI 决策系统的【当前能力快照】和【世界前沿信号】。\n"
    "请判断这套系统有没有**落后、可加的插件、可加的新功能、值得升级的框架**, 给出最多 "
    f"{_MAX_PROPOSALS} 条**具体、可执行**的升级建议。\n\n"
    "要求每条:\n"
    "- type: 只能是 plugin(插件) / feature(新功能) / framework(框架升级) / model(换模型) 之一\n"
    "- title: 简短标题\n"
    "- plain: **用完全的大白话**解释这是什么、能带来什么好处 (给非技术用户看, 不许堆术语)\n"
    "- benefit: 一句话收益\n"
    "- effort: 低/中/高\n"
    "- risk: 低/中/高\n"
    "- detail: 给开发者看的落地要点 (怎么接, 影响哪里)\n"
    "重要: **即使下方「前沿信号」为空, 也要基于你对 2025-2026 年最新 AI/Agent 框架、插件(MCP)生态、"
    "RAG/记忆/多智能体工程实践的了解**, 主动找出这套系统可升级或可追加的点。\n"
    "默认给出 **3-5 条** 高价值建议; 只有当系统确实已非常完善、实在挑不出时, 才返回少于 3 条。\n"
    "严格只输出 JSON:\n"
    '{"proposals":[{"type":"plugin","title":"...","plain":"...","benefit":"...","effort":"中","risk":"低","detail":"..."}]}\n\n'
    "【当前能力快照】\n{manifest}\n\n【世界前沿信号】\n{frontier}\n"
)


async def _analyze(manifest_txt: str, frontier_txt: str) -> list[dict[str, Any]]:
    try:
        from app.llm.litellm_client import litellm_client
        from app.llm.router import router as llm_router
        from app.llm.parsing import _extract_json
        prompt = _PROMPT.replace("{manifest}", manifest_txt[:6000]).replace("{frontier}", (frontier_txt or "(暂无前沿信号)")[:4000])
        resp = await litellm_client.complete(
            model=_MODEL, fallbacks=llm_router.fallbacks(),
            system="你只输出严格 JSON, 不要解释或 markdown 代码块标记。",
            prompt=prompt,
        )
        obj = _extract_json(resp.text or "") or {}
    except Exception:
        return []
    raw = obj.get("proposals") if isinstance(obj, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for p in raw:
        if isinstance(p, dict) and p.get("title") and p.get("plain"):
            out.append(p)
        if len(out) >= _MAX_PROPOSALS:
            break
    return out


def _already_pending(titles: set[str]) -> set[str]:
    """已在待审池里的 capability 提案标题 (去重, 避免天天刷屏)."""
    seen: set[str] = set()
    try:
        c = sqlite3.connect(str(_PENDING_DB))
        rows = c.execute(
            "SELECT target FROM pending_changes WHERE evolver='p18_capability_radar' AND status='pending'"
        ).fetchall()
        c.close()
        seen = {str(r[0]) for r in rows}
    except Exception:
        pass
    return seen & titles


_TYPE_CN = {"plugin": "🧩 加插件", "feature": "✨ 加功能", "framework": "🏗 升框架", "model": "🧠 换模型"}


def run() -> dict[str, Any]:
    now = int(time.time())
    try:
        from app.capability_manifest import build_manifest, manifest_text
        manifest = build_manifest()
        mtext = manifest_text(manifest)
    except Exception as e:
        return {"evolver": "p18_capability_radar", "status": "manifest_failed", "error": str(e), "ts": now}

    frontier = _frontier()

    try:
        proposals = asyncio.run(_analyze(mtext, frontier))
    except Exception as e:
        return {"evolver": "p18_capability_radar", "status": "analyze_failed", "error": str(e), "ts": now}

    if not proposals:
        return {"evolver": "p18_capability_radar", "status": "no_op", "reason": "无值得升级的建议", "ts": now}

    # 去重
    titles = {str(p.get("title")) for p in proposals}
    dup = _already_pending(titles)

    submitted = 0
    try:
        from app.pending_changes import submit_change
    except Exception as e:
        return {"evolver": "p18_capability_radar", "status": "submit_unavailable", "error": str(e),
                "proposals": len(proposals), "ts": now}

    for p in proposals:
        title = str(p.get("title"))
        if title in dup:
            continue
        ptype = str(p.get("type") or "feature")
        tag = _TYPE_CN.get(ptype, "✨ 升级建议")
        # description = 给你看的大白话 (审批抽屉直接显示这段)
        desc = (
            f"{tag}：{title}\n"
            f"💡 {p.get('plain', '')}\n"
            f"✅ 收益：{p.get('benefit', '-')}　|　🔧 工作量：{p.get('effort', '?')}　|　⚠️ 风险：{p.get('risk', '?')}"
        )
        try:
            submit_change(
                evolver="p18_capability_radar",
                kind=f"capability_{ptype}",
                target=title,
                description=desc,
                proposal=p,
            )
            submitted += 1
        except Exception:
            continue

    return {
        "evolver": "p18_capability_radar",
        "status": "proposed" if submitted else "all_duplicates",
        "proposed": submitted,
        "analyzed": len(proposals),
        "skipped_dup": len(dup),
        "ts": now,
    }
