"""v3-K 主动交互 HTTP 端点 (修脱节: proactive.py 之前只有函数, 没挂路由).

GET  /api/proactive/pending          列待推送通知
POST /api/proactive/run-checks       手动跑一次 3 个触发器
POST /api/proactive/{nid}/delivered  标记某条已读
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from . import proactive

router = APIRouter(prefix="/api/proactive", tags=["proactive"])


@router.get("/pending")
def list_pending(limit: int = 50) -> dict:
    return {"items": proactive.pending(limit)}


@router.post("/run-checks")
def run_all() -> dict:
    return proactive.run_all_checks()


@router.post("/{nid}/delivered")
def mark(nid: str) -> dict:
    ok = proactive.mark_delivered(nid)
    if not ok:
        raise HTTPException(404, f"notification {nid} not found")
    return {"marked": nid}
