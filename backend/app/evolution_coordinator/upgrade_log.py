"""v5-F 升级日志 + 一键回滚 — 给协调器加端点.

GET  /coordinator/upgrades                   — 本周自动升级日志
POST /coordinator/upgrades/{run_id}/rollback — 一键回滚
GET  /coordinator/upgrades/weekly-report     — 演化周报 (markdown)
"""
from __future__ import annotations

import sqlite3, subprocess, time
from pathlib import Path
from fastapi import APIRouter, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = Path(__file__).parent / "data" / "evolution_history.sqlite"

router = APIRouter()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


@router.get("/upgrades")
def list_upgrades(days: int = 7, limit: int = 100) -> dict:
    since = int(time.time()) - days * 86400
    with _conn() as c:
        try:
            rows = c.execute(
                "SELECT id, ts, branch, status, diff_summary, gates_passed, kpi_before, kpi_after "
                "FROM self_update_log WHERE ts > ? ORDER BY ts DESC LIMIT ?",
                (since, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return {"items": [], "note": "self_update_log 表尚未创建 (p12 未跑过)"}
    return {"items": [dict(r) for r in rows], "since_ts": since}


@router.post("/upgrades/{run_id}/rollback")
def rollback(run_id: str) -> dict:
    with _conn() as c:
        row = c.execute("SELECT branch, status FROM self_update_log WHERE id=?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(404, "run_id not found")
    if row["status"] not in ("merged", "merged_trial"):
        raise HTTPException(400, f"run is {row['status']}, no merge to revert")
    log_proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "log", "--all", f"--grep={run_id}", "--format=%H", "-n", "1"],
        capture_output=True, text=True,
    )
    sha = log_proc.stdout.strip()
    if not sha:
        raise HTTPException(404, "merge commit not found in git log")
    revert = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "revert", "--no-edit", "-m", "1", sha],
        capture_output=True, text=True,
    )
    if revert.returncode != 0:
        raise HTTPException(500, f"git revert failed: {revert.stderr}")
    with _conn() as c:
        c.execute(
            "UPDATE self_update_log SET status='rolled_back', kpi_after=? WHERE id=?",
            (f"rolled_back_at_{int(time.time())}", run_id),
        )
    return {"run_id": run_id, "reverted_sha": sha, "status": "rolled_back"}


@router.get("/upgrades/weekly-report")
def weekly_report() -> dict:
    week_ago = int(time.time()) - 7 * 86400
    with _conn() as c:
        try:
            rows = c.execute(
                "SELECT status, COUNT(*) n FROM self_update_log WHERE ts > ? GROUP BY status",
                (week_ago,),
            ).fetchall()
            totals = {r["status"]: r["n"] for r in rows}
            recent = c.execute(
                "SELECT id, status, diff_summary FROM self_update_log "
                "WHERE ts > ? ORDER BY ts DESC LIMIT 20",
                (week_ago,),
            ).fetchall()
        except sqlite3.OperationalError:
            return {"markdown": "# 本周演化周报\n\n暂无数据 (p12 尚未运行)。"}

    lines = ["# 本周演化周报", ""]
    lines.append(f"- 总尝试: {sum(totals.values())}")
    for s, n in totals.items():
        lines.append(f"  - {s}: {n}")
    lines.append("")
    lines.append("## 最近 20 条")
    for r in recent:
        first_line = (r["diff_summary"] or "").splitlines()[0] if r["diff_summary"] else "(no summary)"
        lines.append(f"- [{r['id']}] **{r['status']}** — {first_line[:100]}")
    return {"markdown": "\n".join(lines), "totals": totals}
