"""v3-H 任务队列 + 云端推理 — RQ (Redis Queue) 接入.

本地起 redis-server (~100MB); 4 worker pool; WebSocket task.progress 流式回传。
未装 rq 或 Redis 不可用时 → 优雅降级到 sync 执行,接口一致。
"""
from __future__ import annotations

import os, time, uuid
from typing import Callable, Any


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
QUEUE_NAME = "bee-tasks"


def get_queue():
    """返回 RQ Queue 或 None (Redis 不可用时)."""
    try:
        from redis import Redis  # type: ignore
        from rq import Queue  # type: ignore
        conn = Redis.from_url(REDIS_URL, socket_connect_timeout=2)
        conn.ping()
        return Queue(QUEUE_NAME, connection=conn)
    except Exception:
        return None


def enqueue(func: Callable[..., Any], *args, job_id: str | None = None, **kwargs) -> dict:
    """异步入队; 无 Redis 时同步执行, 接口一致."""
    q = get_queue()
    if q is None:
        jid = job_id or f"sync-{uuid.uuid4().hex[:8]}"
        try:
            result = func(*args, **kwargs)
            return {"id": jid, "status": "finished", "result": result, "sync_fallback": True}
        except Exception as e:
            return {"id": jid, "status": "failed", "error": str(e), "sync_fallback": True}

    job = q.enqueue(func, *args, **kwargs, job_id=job_id, job_timeout="1h")
    return {"id": job.id, "status": "queued", "enqueued_ts": int(time.time())}


def job_status(job_id: str) -> dict:
    try:
        from redis import Redis  # type: ignore
        from rq.job import Job  # type: ignore
        conn = Redis.from_url(REDIS_URL, socket_connect_timeout=2)
        job = Job.fetch(job_id, connection=conn)
        return {
            "id": job.id,
            "status": job.get_status(),
            "result": job.result if job.is_finished else None,
            "error": str(job.exc_info)[:1000] if job.is_failed else None,
            "enqueued_at": job.enqueued_at.isoformat() if job.enqueued_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "ended_at": job.ended_at.isoformat() if job.ended_at else None,
        }
    except Exception as e:
        return {"id": job_id, "status": "unknown", "error": str(e)}


def queue_stats() -> dict:
    q = get_queue()
    if q is None:
        return {"redis_ok": False, "queued": 0, "fallback": "sync"}
    return {
        "redis_ok": True,
        "queued": len(q),
        "failed_count": q.failed_job_registry.count if hasattr(q, "failed_job_registry") else 0,
    }
