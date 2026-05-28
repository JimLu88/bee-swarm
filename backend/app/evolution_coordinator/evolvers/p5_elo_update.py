"""v3-L ELO 锦标赛 (扩展到 OCEAN 维度).

用昨日数据刷:
1. 模型 ELO         — Top 3 升主路由
2. OCEAN persona    — 哪个激进/保守组合长期更优 (自演化)
3. 思维范式 ELO     — 8 范式 × 任务类型 哪组合最准

K-factor: 24 (折中, 新模型快速收敛, 主路由稳态)。
"""
from __future__ import annotations

import sqlite3, time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "evolution_history.sqlite"
MAIN_DB = Path(__file__).resolve().parents[3] / "data" / "decision_memory.sqlite"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.execute("""
        CREATE TABLE IF NOT EXISTS elo_ratings (
            entity_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            rating REAL DEFAULT 1500,
            n_games INTEGER DEFAULT 0,
            updated_ts INTEGER,
            PRIMARY KEY (entity_id, kind)
        )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_elo_kind ON elo_ratings(kind, rating DESC)")
    c.row_factory = sqlite3.Row
    return c


def _expected(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def _update_pair(c: sqlite3.Connection, kind: str, winner: str, loser: str, k: float = 24) -> None:
    rows = {r["entity_id"]: r for r in c.execute(
        "SELECT entity_id, rating, n_games FROM elo_ratings WHERE kind=? AND entity_id IN (?, ?)",
        (kind, winner, loser),
    ).fetchall()}
    rw = rows.get(winner, {"rating": 1500.0, "n_games": 0})
    rl = rows.get(loser, {"rating": 1500.0, "n_games": 0})

    ew = _expected(rw["rating"], rl["rating"])
    rw_new = rw["rating"] + k * (1 - ew)
    rl_new = rl["rating"] + k * (-(1 - ew))
    now = int(time.time())
    for entity, rating, games in [(winner, rw_new, rw["n_games"] + 1),
                                  (loser, rl_new, rl["n_games"] + 1)]:
        c.execute(
            """INSERT INTO elo_ratings (entity_id, kind, rating, n_games, updated_ts)
                   VALUES (?,?,?,?,?)
               ON CONFLICT(entity_id, kind) DO UPDATE SET
                   rating=excluded.rating, n_games=excluded.n_games, updated_ts=excluded.updated_ts""",
            (entity, kind, rating, games, now),
        )


def _collect_pairs() -> dict[str, list[tuple[str, str]]]:
    """从 decisions 表挑昨日的 (winner, loser) 对."""
    if not MAIN_DB.exists():
        return {}
    try:
        mc = sqlite3.connect(str(MAIN_DB))
        mc.row_factory = sqlite3.Row
        since = int(time.time()) - 86400
        rows = mc.execute(
            "SELECT * FROM decisions WHERE ts > ? ORDER BY ts DESC LIMIT 500", (since,)
        ).fetchall()
        mc.close()
    except sqlite3.OperationalError:
        return {}

    pairs: dict[str, list[tuple[str, str]]] = {"model": [], "ocean": [], "paradigm": []}
    for r in rows:
        row = dict(r)
        feedback = row.get("user_feedback") or ""
        positive = ("好" in feedback or "棒" in feedback) and "驳回" not in feedback

        primary = row.get("model_used") or row.get("ceo_model")
        fallback = row.get("fallback_model_used")
        if primary and fallback and primary != fallback:
            winner = primary if positive else fallback
            loser = fallback if positive else primary
            pairs["model"].append((winner, loser))

        ocean = row.get("ocean_traits")
        alt_ocean = row.get("alt_ocean_traits")
        if ocean and alt_ocean and ocean != alt_ocean:
            w = f"OCEAN:{ocean}" if positive else f"OCEAN:{alt_ocean}"
            l = f"OCEAN:{alt_ocean}" if positive else f"OCEAN:{ocean}"
            pairs["ocean"].append((w, l))

        paradigm = row.get("paradigms_used")
        if paradigm:
            other = "no_paradigm"
            w = paradigm if positive else other
            l = other if positive else paradigm
            pairs["paradigm"].append((w, l))
    return pairs


def run() -> dict:
    now = int(time.time())
    pairs = _collect_pairs()
    total_updates = 0
    with _conn() as c:
        for kind, ps in pairs.items():
            for winner, loser in ps:
                _update_pair(c, kind, winner, loser)
                total_updates += 1
        top = {kind: [dict(r) for r in c.execute(
            "SELECT entity_id, rating, n_games FROM elo_ratings WHERE kind=? "
            "ORDER BY rating DESC LIMIT 5", (kind,)).fetchall()]
            for kind in ("model", "ocean", "paradigm")}
    return {
        "evolver": "p5_elo_update",
        "status": "ok" if total_updates else "no_pairs_found",
        "updates": total_updates,
        "leaderboards": top,
        "ts": now,
    }
