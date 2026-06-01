"""自学习闭环 HTTP 端点 — 挂 /api/learning/**.

GET  /api/learning/inbox/stats              收件箱统计 (pending/digested 各多少)
POST /api/learning/digest/run               立即跑一次 20:00 梳理 (手动触发, 不等明天)
GET  /api/learning/lazy-seed/status/{mode}  某后台场景懒加载灌书进度
POST /api/learning/lazy-seed/run/{mode}     立即触发某场景懒加载灌书 (手动)
GET  /api/learning/overview                 总览 (收件箱 + 调度器状态)
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter

from . import inbox, lazy_seed

router = APIRouter(prefix="/api/learning", tags=["auto_learning"])


@router.get("/inbox/stats")
def inbox_stats() -> dict[str, Any]:
    return inbox.stats()


@router.post("/digest/run")
async def digest_run(max_groups: int = 12) -> dict[str, Any]:
    """手动跑梳理. run_digest 内部用 asyncio.run, 必须丢线程跑 (否则与本 loop 冲突)."""
    from . import digest
    return await asyncio.to_thread(digest.run_digest, max_groups)


@router.get("/lazy-seed/status/{mode_id}")
def lazy_seed_status(mode_id: str) -> dict[str, Any]:
    return lazy_seed.get_status(mode_id)


@router.post("/lazy-seed/run/{mode_id}")
async def lazy_seed_run(mode_id: str) -> dict[str, Any]:
    """手动触发某场景懒加载灌书 (后台异步, 立即返回 scheduled)."""
    if mode_id in lazy_seed.FRONT_STAGE_SEEDED:
        return {"scheduled": False, "reason": "front_stage_seeded",
                "note": "前台场景已手写灌满, 无需懒加载"}
    asyncio.get_running_loop().create_task(lazy_seed.run_lazy_seed(mode_id))
    lazy_seed._set_status(mode_id, status="scheduled")
    return {"scheduled": True, "mode_id": mode_id,
            "note": "已丢后台灌书, 用 GET /api/learning/lazy-seed/status/{mode} 看进度"}


@router.get("/overview")
def overview() -> dict[str, Any]:
    out: dict[str, Any] = {"inbox": inbox.stats()}
    try:
        from ..evolution_coordinator.coordinator import scheduler_status
        out["scheduler"] = scheduler_status()
    except Exception as e:
        out["scheduler"] = {"error": repr(e)}
    out["front_stage_seeded"] = sorted(lazy_seed.FRONT_STAGE_SEEDED)
    return out
