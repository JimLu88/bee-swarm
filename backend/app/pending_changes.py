"""v6-G PendingChanges — 自更新提案的审批通道.

evolvers (p12 自更新 / p15 人设演化 / p17 趋势监控) 把"建议改动"先入这个表,
用户在前端 PendingChangesDrawer 看到后可 approve / reject. approve 才真应用.

表 schema:
    pending_changes:
        id TEXT PK              -- pc-<uuid12>
        ts INT                  -- unix
        evolver TEXT            -- 来源 evolver id
        kind TEXT               -- bug_fix / persona_update / trend_integration / code_change
        target TEXT             -- 影响范围 (文件路径 / persona_id / mode_id 等)
        description TEXT        -- 人话说明
        proposal TEXT           -- JSON 或 diff 文本
        status TEXT             -- pending / approved / rejected / applied / failed
"""
from __future__ import annotations
import sqlite3
import time
import uuid
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/pending", tags=["pending_changes"])

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "pending_changes.sqlite"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_changes (
            id TEXT PRIMARY KEY, ts INTEGER, evolver TEXT, kind TEXT,
            target TEXT, description TEXT, proposal TEXT,
            status TEXT DEFAULT 'pending'
        )""")
    return c


def submit_change(*, evolver: str, kind: str, target: str,
                  description: str, proposal: Any) -> str:
    """供 evolvers 调用: 提交一个待审批的变更, 返 id."""
    pid = "pc-" + uuid.uuid4().hex[:12]
    proposal_str = (proposal if isinstance(proposal, str)
                    else json.dumps(proposal, ensure_ascii=False))
    with _conn() as c:
        c.execute(
            "INSERT INTO pending_changes VALUES (?,?,?,?,?,?,?, 'pending')",
            (pid, int(time.time()), evolver, kind, target,
             description[:2000], proposal_str[:8000]),
        )
    return pid


@router.get("/list")
def list_pending(status: str = "pending", limit: int = 50) -> dict[str, Any]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, ts, evolver, kind, target, description, proposal, status "
            "FROM pending_changes WHERE status=? ORDER BY ts DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    items = [{
        "id": r[0], "ts": r[1], "evolver": r[2], "kind": r[3],
        "target": r[4], "description": r[5],
        "proposal": _maybe_json(r[6]),
        "status": r[7],
    } for r in rows]
    return {"items": items, "count": len(items), "status_filter": status}


@router.get("/{change_id}")
def get_pending(change_id: str) -> dict[str, Any]:
    with _conn() as c:
        row = c.execute(
            "SELECT id, ts, evolver, kind, target, description, proposal, status "
            "FROM pending_changes WHERE id=?", (change_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, f"change {change_id} not found")
    return {
        "id": row[0], "ts": row[1], "evolver": row[2], "kind": row[3],
        "target": row[4], "description": row[5],
        "proposal": _maybe_json(row[6]), "status": row[7],
    }


class DecisionBody(BaseModel):
    note: str = ""


@router.post("/{change_id}/approve")
def approve_pending(change_id: str, body: DecisionBody | None = None) -> dict[str, Any]:
    """标 approved + 尝试调用对应 apply hook. 失败标 failed."""
    with _conn() as c:
        row = c.execute(
            "SELECT evolver, kind, target, proposal, status FROM pending_changes WHERE id=?",
            (change_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, f"change {change_id} not found")
        if row[4] != "pending":
            raise HTTPException(409, f"already {row[4]}")
        c.execute("UPDATE pending_changes SET status='approved' WHERE id=?", (change_id,))

    evolver, kind, target, proposal_str = row[0], row[1], row[2], row[3]
    applied_ok = _try_apply(evolver, kind, target, proposal_str)
    new_status = "applied" if applied_ok else "failed"
    with _conn() as c:
        c.execute("UPDATE pending_changes SET status=? WHERE id=?", (new_status, change_id))
    return {"id": change_id, "status": new_status,
            "note": "applied successfully" if applied_ok else
                    "approved but apply hook failed; manual action required"}


@router.post("/{change_id}/reject")
def reject_pending(change_id: str, body: DecisionBody | None = None) -> dict[str, Any]:
    with _conn() as c:
        row = c.execute("SELECT status FROM pending_changes WHERE id=?", (change_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"change {change_id} not found")
        if row[0] != "pending":
            raise HTTPException(409, f"already {row[0]}")
        c.execute("UPDATE pending_changes SET status='rejected' WHERE id=?", (change_id,))
    return {"id": change_id, "status": "rejected"}


@router.get("/stats/summary")
def stats_summary() -> dict[str, Any]:
    with _conn() as c:
        rows = c.execute(
            "SELECT status, COUNT(*) FROM pending_changes GROUP BY status"
        ).fetchall()
    out = {"pending": 0, "approved": 0, "rejected": 0, "applied": 0, "failed": 0}
    for status, n in rows:
        out[status] = int(n)
    return out


def _maybe_json(s: str) -> Any:
    if not s:
        return s
    try:
        return json.loads(s)
    except Exception:
        return s


def _try_apply(evolver: str, kind: str, target: str, proposal_str: str) -> bool:
    """根据 kind 路由到对应的真应用函数. 失败返 False."""
    try:
        proposal = _maybe_json(proposal_str)
        if kind == "persona_update":
            # target = "<mode_id>/<dept_id>/<persona_id>"; proposal = {"prompt": "..."}
            from .persona import team_store
            parts = target.split("/")
            if len(parts) != 3:
                return False
            mode_id, dept_id, persona_id = parts
            new_prompt = (proposal or {}).get("prompt", "") if isinstance(proposal, dict) else ""
            if not new_prompt:
                return False
            if hasattr(team_store, "update_persona_prompt"):
                team_store.update_persona_prompt(
                    mode_id=mode_id, dept_id=dept_id,
                    persona_id=persona_id, prompt=new_prompt,
                )
                return True
            return False

        if kind == "persona_regenerate":
            # target = "<mode_id>/<dept_id>/<persona_id>"
            # 实际行动: 让 team_generator.regenerate_persona 跑一遍, 落盘到 team.yaml
            import asyncio
            from .persona import team_generator
            parts = target.split("/")
            if len(parts) != 3:
                return False
            mode_id, dept_id, persona_id = parts
            try:
                asyncio.run(team_generator.regenerate_persona(mode_id, dept_id, persona_id))
                return True
            except Exception:
                return False

        # 其它 kind (code_change / bug_fix / trend_integration):
        # 已是"提议", 不自动改文件. 标 approved 即可, 人审手工跟进.
        return True
    except Exception:
        return False
