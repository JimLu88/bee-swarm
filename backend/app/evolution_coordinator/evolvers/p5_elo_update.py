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
# v6 修脱节: decision_memory 实际是 JSONL 不是 SQLite. 读 backend/data/<mode_id>/decisions.jsonl
DATA_ROOT = Path(__file__).resolve().parents[3] / "data"


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


def _read_recent_decisions_jsonl(since_ts: int, per_mode_limit: int = 200) -> list[dict]:
    """v6 修脱节: 从 backend/data/<mode>/decisions.jsonl 读最近的决策记录."""
    import json as _json
    import datetime as _dt
    if not DATA_ROOT.exists():
        return []
    rows: list[dict] = []
    for mode_dir in DATA_ROOT.iterdir():
        if not mode_dir.is_dir():
            continue
        jsonl = mode_dir / "decisions.jsonl"
        if not jsonl.exists():
            continue
        try:
            lines = jsonl.read_text(encoding="utf-8").splitlines()[-per_mode_limit:]
        except Exception:
            continue
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                row = _json.loads(ln)
            except Exception:
                continue
            # 解析 created_at "YYYY-MM-DD HH:MM:SS" → ts
            try:
                ts = int(_dt.datetime.strptime(row.get("created_at", ""), "%Y-%m-%d %H:%M:%S").timestamp())
            except Exception:
                ts = int(time.time())
            if ts < since_ts:
                continue
            row["_ts"] = ts
            rows.append(row)
    return rows


def _collect_pairs() -> dict[str, list[tuple[str, str]]]:
    """从 decisions.jsonl 挑最近的 (winner, loser) 对."""
    since = int(time.time()) - 86400 * 14  # 滚动 14 天
    rows = _read_recent_decisions_jsonl(since)
    if not rows:
        return {"model": [], "ocean": [], "paradigm": [], "persona_role": [], "model_role": []}

    import json as _json

    pairs: dict[str, list[tuple[str, str]]] = {
        "model": [], "ocean": [], "paradigm": [],
        "persona_role": [], "model_role": [],   # v6-B: 主管/职员 ELO 维度
    }
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

        # v6-B: persona_role + model_role ELO — 用户反馈映射到 head/staff/ceo 的 ELO
        # decisions 表预期有列 team_personas_used (JSON 字符串):
        #   [{"persona_id": "...", "role": "head|staff|ceo", "model": "anthropic/..."}]
        # 该列不存在时 row.get 返回 None, 这段直接跳过 (向后兼容)
        team_used_raw = row.get("team_personas_used")
        if team_used_raw:
            try:
                used = _json.loads(team_used_raw) if isinstance(team_used_raw, str) else team_used_raw
            except Exception:
                used = []
            for p in used or []:
                if not isinstance(p, dict):
                    continue
                pid = str(p.get("persona_id") or "")
                role = str(p.get("role") or "")
                model = str(p.get("model") or "")
                if not pid or not role:
                    continue
                baseline = f"baseline@{role}"
                if positive:
                    pairs["persona_role"].append((f"{pid}@{role}", baseline))
                else:
                    pairs["persona_role"].append((baseline, f"{pid}@{role}"))
                if model:
                    if positive:
                        pairs["model_role"].append((f"{model}@{role}", baseline))
                    else:
                        pairs["model_role"].append((baseline, f"{model}@{role}"))
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
            for kind in ("model", "ocean", "paradigm", "persona_role", "model_role")}
    return {
        "evolver": "p5_elo_update",
        "status": "ok" if total_updates else "no_pairs_found",
        "updates": total_updates,
        "leaderboards": top,
        "ts": now,
    }
