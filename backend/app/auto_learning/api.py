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


@router.post("/seed-all")
async def seed_all_run(only_missing: bool = True) -> dict[str, Any]:
    """全场景预灌书 (一次性, 取代"首问才懒加载"). 后台跑, 立即返回; 量大耗时较长。

    only_missing=True: 跳过已 done 的场景 (可反复调用续灌, 直到全部 done)。
    """
    from . import seed_all as _sa
    if _sa.seed_all_progress().get("running"):
        return {"started": False, "reason": "already_running", **_sa.seed_all_progress()}
    asyncio.get_running_loop().create_task(_sa.seed_all_modes(only_missing=only_missing))
    return {"started": True, "note": "全场景灌书已在后台开始, 用 GET /api/learning/seed-all/status 看进度"}


@router.get("/seed-all/status")
def seed_all_status() -> dict[str, Any]:
    from . import seed_all as _sa
    return _sa.seed_all_progress()


@router.post("/seed-corpus")
async def seed_corpus_run(force: bool = False) -> dict[str, Any]:
    """把手写知识库语料(corpus, 礼物+15产业)幂等灌进 bee-memory。

    开机已自动灌一次; 此端点供手动重灌/补灌 (DB 级去重, 已存在的自动跳过)。
    """
    from ..seed_knowledge.loader import seed_sync
    res = await asyncio.to_thread(seed_sync, force)
    return {"inserted": res, "note": "已灌入 (幂等, 已存在的自动跳过)"}


@router.get("/seed-corpus/status")
def seed_corpus_status() -> dict[str, Any]:
    """查看手写知识库已灌入进度 (各场景已灌条数 vs 语料总数)。"""
    from ..seed_knowledge.loader import seed_status
    from ..seed_knowledge.corpus import CORPUS
    seeded = seed_status()
    total = {m: sum(len(e) for e in depts.values()) for m, depts in CORPUS.items()}
    return {
        "seeded": seeded,
        "corpus_total": total,
        "all_done": all(seeded.get(m, 0) >= n for m, n in total.items()),
    }


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
