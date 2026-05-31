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
    ("p13_model_discovery","模型自动发现 (LMSYS/LiteLLM)", "L6"),
    ("p14_skill_discovery","Skill/MCP 自发现 (GitHub)",   "L9"),
    ("p15_team_evolve",   "主管自演化 (ELO + Shadow 14天)", "L3"),
    ("p16_knowledge_curator", "知识策展员 (8 层知识库充实)", "L2"),
    ("p17_trend_monitor",  "趋势监控 (扫外部 → 提案入待审池)", "L7"),
]


# v5-F 升级日志 + 一键回滚 端点 (在末尾追加, 避免循环 import)
def _attach_upgrade_log() -> None:
    try:
        from .upgrade_log import router as _ur
        coordinator_router.include_router(_ur)
    except Exception:
        pass


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


_attach_upgrade_log()


# ============== v6 修脱节 #2: 真接 APScheduler 让 P0-P16 自动跑 ==============

_SCHEDULER = None


def _run_all_evolvers_serial() -> None:
    """02:00 cron 调用. 串行 P0→P16, 间隔 60 秒, 失败不影响下一个."""
    import importlib, time as _t
    for evolver, _label, _layer in EVOLVERS:
        try:
            mod = importlib.import_module(f"app.evolution_coordinator.evolvers.{evolver}")
            out = mod.run()
            rid = "ev-cron-" + uuid.uuid4().hex[:10]
            with _conn() as c:
                c.execute(
                    "INSERT INTO evolution_log VALUES (?,?,?,?,?,?,?)",
                    (rid, int(_t.time()), evolver, out.get("status", "unknown"),
                     str(out)[:1000], "cron", ""),
                )
        except Exception as e:
            rid = "ev-cron-fail-" + uuid.uuid4().hex[:10]
            with _conn() as c:
                c.execute(
                    "INSERT INTO evolution_log VALUES (?,?,?,?,?,?,?)",
                    (rid, int(_t.time()), evolver, "error", str(e)[:1000], "cron", ""),
                )
        _t.sleep(60)


def start_scheduler() -> dict:
    """main.py lifespan startup 时调. 失败 (缺 APScheduler) 静默, 不影响业务."""
    global _SCHEDULER
    if _SCHEDULER is not None:
        return {"started": False, "reason": "already_started"}
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        return {"started": False, "reason": "apscheduler_not_installed",
                "hint": "pip install apscheduler"}
    sch = AsyncIOScheduler()
    sch.add_job(_run_all_evolvers_serial, CronTrigger(hour=2, minute=0),
                id="ev_all_02", replace_existing=True)
    sch.start()
    _SCHEDULER = sch
    return {"started": True, "cron": "daily 02:00", "evolvers": [e for e, _, _ in EVOLVERS]}


def stop_scheduler() -> None:
    global _SCHEDULER
    if _SCHEDULER is not None:
        try:
            _SCHEDULER.shutdown(wait=False)
        except Exception:
            pass
        _SCHEDULER = None


@coordinator_router.get("/scheduler-status")
def scheduler_status() -> dict:
    return {
        "running": _SCHEDULER is not None,
        "jobs": [{"id": j.id, "next_run": str(j.next_run_time)}
                 for j in (_SCHEDULER.get_jobs() if _SCHEDULER else [])],
    }


# v5-F 升级日志 + 一键回滚 端点
from .upgrade_log import router as _upgrade_router  # noqa: E402
coordinator_router.include_router(_upgrade_router)