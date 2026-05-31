"""L2 遗忘曲线 — 低激活记忆标记衰减, 超低删除 (走 bee-memory /forget 端点)."""
from __future__ import annotations
import os
import httpx
from ._utils import append_log

MEMORY_URL = os.environ.get("BEE_MEMORY_URL", "http://127.0.0.1:8004")
TOKEN = os.environ.get("BEE_BEARER_TOKEN", "dev-token-change-me")

LOW_ACT_THRESHOLD = 0.15
DELETE_THRESHOLD = 0.05


def run() -> dict:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        with httpx.Client(timeout=15) as c:
            r = c.get(f"{MEMORY_URL}/memory/stats", headers=headers)
            stats = r.json() if r.status_code == 200 else {}
            r2 = c.post(f"{MEMORY_URL}/memory/recall",
                        json={"persona_id": "swarm_global", "query": "*", "k": 200,
                              "strategy": "activation"},
                        headers=headers)
            items = r2.json().get("items") or [] if r2.status_code == 200 else []
    except Exception as e:
        return {"evolver": "p7_forgetting", "status": "memory_error",
                "summary": f"调 bee-memory 失败: {e!r}"}

    if not items:
        return {"evolver": "p7_forgetting", "status": "no_data",
                "summary": "记忆库空", "stats": stats}

    decay_cands = [it for it in items
                   if float(it.get("activation", 0)) < LOW_ACT_THRESHOLD]
    delete_cands = [it for it in items
                    if float(it.get("activation", 0)) < DELETE_THRESHOLD]

    forgotten = 0
    delete_errors: list[str] = []
    if delete_cands:
        for it in delete_cands[:20]:
            mid = it.get("id") or it.get("memory_id")
            if not mid:
                continue
            try:
                with httpx.Client(timeout=10) as c:
                    r = c.post(f"{MEMORY_URL}/memory/forget",
                               json={"memory_id": mid}, headers=headers)
                if r.status_code in (200, 204):
                    forgotten += 1
                elif r.status_code == 404:
                    delete_errors.append("endpoint /memory/forget not implemented")
                    break
            except Exception as e:
                delete_errors.append(repr(e)[:200])

    append_log("p7_forgetting", {
        "scanned": len(items),
        "decay_candidates": len(decay_cands),
        "delete_candidates": len(delete_cands),
        "forgotten": forgotten,
        "errors": delete_errors[:3],
        "memory_stats": stats,
    })
    return {
        "evolver": "p7_forgetting", "status": "done",
        "scanned": len(items), "decay_candidates": len(decay_cands),
        "delete_candidates": len(delete_cands), "forgotten": forgotten,
        "summary": (f"扫 {len(items)} 条, 标 {len(decay_cands)} 衰减, "
                    f"删 {forgotten} 条 (候选 {len(delete_cands)})"),
    }
