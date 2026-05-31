"""v6-M 收藏功能 — 决策默认只留 100 条; 点 ⭐ 收藏的永久保留."""
from __future__ import annotations
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/favorites", tags=["favorites"])

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "favorites.sqlite"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

HISTORY_RETENTION = 100


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            decision_id TEXT PRIMARY KEY, ts INTEGER,
            mode_id TEXT, note TEXT DEFAULT ''
        )""")
    return c


class FavRequest(BaseModel):
    decision_id: str
    mode_id: str = ""
    note: str = ""


@router.post("/star")
def star(req: FavRequest) -> dict[str, Any]:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO favorites VALUES (?,?,?,?)",
            (req.decision_id, int(time.time()), req.mode_id, req.note[:500]),
        )
    return {"starred": True, "decision_id": req.decision_id}


@router.delete("/{decision_id}")
def unstar(decision_id: str) -> dict[str, Any]:
    with _conn() as c:
        n = c.execute("DELETE FROM favorites WHERE decision_id=?", (decision_id,)).rowcount
    return {"unstarred": n > 0, "decision_id": decision_id}


@router.get("/list")
def list_favorites() -> dict[str, Any]:
    with _conn() as c:
        rows = c.execute(
            "SELECT decision_id, ts, mode_id, note FROM favorites ORDER BY ts DESC"
        ).fetchall()
    return {"items": [
        {"decision_id": r[0], "ts": r[1], "mode_id": r[2], "note": r[3]}
        for r in rows
    ]}


@router.get("/check/{decision_id}")
def check(decision_id: str) -> dict[str, Any]:
    with _conn() as c:
        row = c.execute(
            "SELECT 1 FROM favorites WHERE decision_id=?", (decision_id,)
        ).fetchone()
    return {"starred": bool(row), "decision_id": decision_id}


def is_starred(decision_id: str) -> bool:
    try:
        with _conn() as c:
            return bool(c.execute(
                "SELECT 1 FROM favorites WHERE decision_id=?", (decision_id,)
            ).fetchone())
    except Exception:
        return False


def all_starred_ids() -> set[str]:
    try:
        with _conn() as c:
            return {r[0] for r in c.execute("SELECT decision_id FROM favorites").fetchall()}
    except Exception:
        return set()
