"""L2 知识图谱 + PageRank — 触发 bee-memory 全库重建概念图 + 记忆↔记忆共现边.

v4 修断路: 旧版在本进程抽实体/算共现后**只写日志**, 从不把边写回 bee-memory,
导致 memory._spread_activation 的 edges 表恒空 (扩散激活无边可走).
现在改为调 bee-memory 的 /memory/reindex-concepts, 由引擎侧真正落库概念/边.
"""
from __future__ import annotations
import os
import httpx
from ._utils import append_log

MEMORY_URL = os.environ.get("BEE_MEMORY_URL", "http://127.0.0.1:8004")
TOKEN = os.environ.get("BEE_BEARER_TOKEN", "dev-token-change-me")


def run() -> dict:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post(f"{MEMORY_URL}/memory/reindex-concepts",
                       json={"rebuild_edges": True, "limit": 0},
                       headers=headers)
        if r.status_code != 200:
            return {"evolver": "p6_graph_rebuild", "status": "memory_unavailable",
                    "summary": f"bee-memory 返 HTTP {r.status_code}"}
        idx = r.json()
    except Exception as e:
        return {"evolver": "p6_graph_rebuild", "status": "memory_error",
                "summary": f"调 bee-memory reindex 失败: {e!r}"}

    if idx.get("status") == "empty":
        return {"evolver": "p6_graph_rebuild", "status": "no_data", "summary": "记忆库空"}

    append_log("p6_graph_rebuild", idx)
    return {
        "evolver": "p6_graph_rebuild", "status": "done",
        "concepts": idx.get("concepts", 0),
        "cooccur_edges": idx.get("cooccur_edges", 0),
        "hub_concepts": idx.get("hub_concepts", 0),
        "summary": (f"扫 {idx.get('scanned', 0)} 条, 建 {idx.get('concepts', 0)} 概念, "
                    f"{idx.get('cooccur_edges', 0)} 记忆共现边 "
                    f"(hub {idx.get('hub_concepts', 0)}, 桶截断 {idx.get('buckets_capped', 0)})"),
    }
