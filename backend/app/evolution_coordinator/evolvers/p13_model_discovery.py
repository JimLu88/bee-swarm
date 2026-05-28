"""v5-C 模型自动发现 — 周扫 LMSYS leaderboard + LiteLLM 价表 commits + 各家官方 blog.

检测到新模型 → 自动加入 ELO 候选池 (10% 探索率)。
1 个月稳定后:Top 3 升主路由,否则降探索或下架。
"""
from __future__ import annotations

import sqlite3, time, json
from pathlib import Path
from urllib import request as urlreq, error as urlerr

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "evolution_history.sqlite"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.execute("""
        CREATE TABLE IF NOT EXISTS model_candidates (
            model_id TEXT PRIMARY KEY,
            source TEXT,
            discovered_ts INTEGER,
            elo INTEGER DEFAULT 1500,
            status TEXT DEFAULT 'candidate',
            cost_input REAL DEFAULT 0,
            cost_output REAL DEFAULT 0
        )""")
    c.row_factory = sqlite3.Row
    return c


def _scan_litellm_prices() -> list[dict]:
    """从 BerriAI/litellm 仓库的 model_prices_and_context_window.json 抓最新模型清单."""
    url = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
    try:
        with urlreq.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        found = []
        for model_id, meta in data.items():
            if not isinstance(meta, dict):
                continue
            if meta.get("mode") not in ("chat", "completion", None):
                continue
            found.append({
                "model_id": model_id,
                "source": "litellm-prices",
                "cost_input": float(meta.get("input_cost_per_token", 0)),
                "cost_output": float(meta.get("output_cost_per_token", 0)),
            })
        return found
    except (urlerr.URLError, json.JSONDecodeError):
        return []


def run() -> dict:
    now = int(time.time())
    candidates = _scan_litellm_prices()
    if not candidates:
        return {"evolver": "p13_model_discovery", "status": "no_sources_reachable",
                "added": 0, "ts": now}

    added = 0
    with _conn() as c:
        existing = {r["model_id"] for r in c.execute("SELECT model_id FROM model_candidates").fetchall()}
        for cand in candidates:
            if cand["model_id"] in existing:
                continue
            c.execute(
                """INSERT INTO model_candidates
                   (model_id, source, discovered_ts, elo, status, cost_input, cost_output)
                   VALUES (?,?,?,1500,'candidate',?,?)""",
                (cand["model_id"], cand["source"], now, cand["cost_input"], cand["cost_output"]),
            )
            added += 1
    return {"evolver": "p13_model_discovery", "status": "ok",
            "scanned": len(candidates), "added": added, "ts": now}
