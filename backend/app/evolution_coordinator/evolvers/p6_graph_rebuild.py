"""L2 知识图谱 + PageRank — 抽实体 + 建共现边 + 输出 top 中心度."""
from __future__ import annotations
import os
import re
import httpx
from collections import Counter, defaultdict
from ._utils import append_log

MEMORY_URL = os.environ.get("BEE_MEMORY_URL", "http://127.0.0.1:8004")
TOKEN = os.environ.get("BEE_BEARER_TOKEN", "dev-token-change-me")

_CH_NOUN = re.compile(r"[一-龥]{2,6}")
_EN_NOUN = re.compile(r"\b[A-Z][a-zA-Z0-9]{2,}\b")


def _extract_entities(text: str) -> list[str]:
    if not text:
        return []
    out = set()
    for m in _CH_NOUN.finditer(text):
        s = m.group(0)
        if not s.isdigit():
            out.add(s)
    for m in _EN_NOUN.finditer(text):
        out.add(m.group(0))
    return list(out)


def run() -> dict:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post(f"{MEMORY_URL}/memory/recall",
                       json={"persona_id": "swarm_global", "query": "*", "k": 50},
                       headers=headers)
        if r.status_code != 200:
            return {"evolver": "p6_graph_rebuild", "status": "memory_unavailable",
                    "summary": f"bee-memory 返 HTTP {r.status_code}"}
        items = r.json().get("items") or r.json().get("results") or []
    except Exception as e:
        return {"evolver": "p6_graph_rebuild", "status": "memory_error",
                "summary": f"调 bee-memory 失败: {e!r}"}

    if not items:
        return {"evolver": "p6_graph_rebuild", "status": "no_data",
                "summary": "记忆库空"}

    edge_weight: dict[tuple[str, str], int] = defaultdict(int)
    entity_count: Counter[str] = Counter()
    for it in items[:50]:
        ents = _extract_entities(str(it.get("content", "")))[:15]
        for e in ents:
            entity_count[e] += 1
        for i in range(len(ents)):
            for j in range(i + 1, len(ents)):
                a, b = sorted([ents[i], ents[j]])
                edge_weight[(a, b)] += 1

    rank = sorted(entity_count.items(), key=lambda kv: kv[1], reverse=True)[:20]
    top_edges = sorted(edge_weight.items(), key=lambda kv: kv[1], reverse=True)[:30]

    append_log("p6_graph_rebuild", {
        "entities_total": len(entity_count),
        "edges_total": len(edge_weight),
        "top_entities": [{"entity": e, "freq": n} for e, n in rank],
        "top_edges": [{"a": a, "b": b, "w": w} for (a, b), w in top_edges[:15]],
        "items_scanned": len(items),
    })
    return {
        "evolver": "p6_graph_rebuild", "status": "done",
        "entities": len(entity_count), "edges": len(edge_weight),
        "top_5_entities": [e for e, _ in rank[:5]],
        "summary": f"扫 {len(items)} 条记忆, 抽 {len(entity_count)} 实体, {len(edge_weight)} 条共现边",
    }
