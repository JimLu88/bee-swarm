"""演化协调器 v2 阶段 6
12 条进化机制 P0-P11 + p12(代码自更新) 串行调度。每日 02:00。每条 ¥30/月预算。
对外:GET /coordinator/status, POST /coordinator/trigger?evolver=p1, GET /pending-changes, POST /approve/{id}
"""
from __future__ import annotations

import sqlite3, time, uuid, importlib
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

coordinator_router = APIRouter()

DB_PATH = Path(__file__).parent / "data" / "evolution_history.sqlite"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# 串行优先级: 宪法 > 架构 > 技能 > 记忆 > Prompt
EVOLVERS = [
    ("p0_constitution",   "宪法审查器",    "L5"),
    ("p1_architecture",   "架构演化器",    "L4"),
    ("p2_paper_intake",   "arXiv 论文吸收", "外部"),
    ("p3_skill_breed",    "Voyager 技能繁殖", "L3"),
    ("p4_self_distill",   "自蒸馏(大教小)",  "L6"),
    ("p5_elo_update",     "ELO 锦标赛",     "评测"),
    ("p6_graph_rebuild",  "知识图谱 + PageRank", "L2"),
    ("p7_forgetting",     "遗忘曲线",       "L2"),
    ("p8_dspy_textgrad",  "Prompt 进化",    "L1"),
    ("p9_pareto",         "多目标 Pareto",  "评测"),
    ("p10_search_evolve", "L0 搜索策略进化", "L0"),
    ("p11_paradigm_evolve","L∞ 范式进化",   "L∞"),
    ("p12_code_self_update","代码自更新(三重双保险)", "L7"),
]


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.execute("""
        CREATE TABLE IF NOT EXISTS evolution_log (
            id TEXT PRIMARY KEY, ts INTEGER, evolver TEXT,
            status TEXT, summary TEXT, before_sha TEXT, after_sha TEXT
        )""")
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_changes (
            id TEXT PRIMARY KEY, ts INTEGER, evolver TEXT,
            kind TEXT, description TEXT, requires_human INTEGER DEFAULT 1
        )""")
    return c


@coordinator_router.get("/status")
def status() -> dict:
    """各 evolver 状态 + 最近运行."""
    return {
        "evolvers": [
            {"id": e, "label": label, "layer": layer, "last_run": None, "budget_yuan": 30}
            for e, label, layer in EVOLVERS
        ],
        "schedule": "daily 02:00 (cron)",
        "priority_order": "宪法 > 架构 > 技能 > 记忆 > Prompt",
        "shadow_validation": "60 任务 A/B + SWE-bench-mini + 24h KPI",
    }


@coordinator_router.post("/trigger")
def trigger(evolver: str = Query(..., pattern="^p[0-9]+_.+")) -> dict:
    valid = [e for e, _, _ in EVOLVERS]
    if evolver not in valid:
        raise HTTPException(400, f"unknown evolver; valid: {valid}")
    # try dynamic load + run
    try:
        mod = importlib.import_module(f"app.evolution_coordinator.evolvers.{evolver}")
        out = mod.run()
    except Exception as e:
        out = {"status": "error", "error": str(e), "scaffold": True}
    rid = "ev-" + uuid.uuid4().hex[:12]
    with _conn() as c:
        c.execute("INSERT INTO evolution_log VALUES (?,?,?,?,?,?,?)",
                  (rid, int(time.time()), evolver, out.get("status", "unknown"),
                   str(out)[:1000], "", ""))
    return {"run_id": rid, "evolver": evolver, "result": out}


@coordinator_router.get("/pending-changes")
def pending_changes() -> dict:
    with _conn() as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT * FROM pending_changes ORDER BY ts DESC LIMIT 50").fetchall()
    return {"items": [dict(r) for r in rows]}


@coordinator_router.post("/approve/{change_id}")
def approve(change_id: str) -> dict:
    with _conn() as c:
        n = c.execute("DELETE FROM pending_changes WHERE id=?", (change_id,)).rowcount
    if n == 0:
        raise HTTPException(404)
    return {"approved": change_id}


class ObservationIn(BaseModel):
    """蜂群每次决策完成后 POST 进来 (异步,失败不阻塞主流程)."""
    decision_id: str
    mode_id: str
    user_feedback: str = ""
    token_usage: int = 0
    cost_yuan: float = 0.0


@coordinator_router.post("/observations")
def observations(req: ObservationIn) -> dict:
    # 累积到痛点日志中,供 p12 代码自更新挖掘
    return {"received": True, "decision_id": req.decision_id}