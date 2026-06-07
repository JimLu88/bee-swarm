"""演化协调器 v2 阶段 6
12 条进化机制 P0-P11 + p12(代码自更新) 串行调度。每日 02:00。每条 ¥30/月预算。
对外:GET /coordinator/status, POST /coordinator/trigger?evolver=p1, GET /pending-changes, POST /approve/{id}
"""
from __future__ import annotations

import sqlite3, time, uuid, importlib, json, os
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
    # v15: p16_knowledge_curator 已停用 (它用 LLM 自动生成/充实知识库 = 自动灌书, 会产生模型花费)。
    ("p17_trend_monitor",  "趋势监控 (扫外部 → 提案入待审池)", "L7"),
    ("p18_capability_radar", "能力雷达 (扫前沿→差距分析→升级提案, 全部待审)", "L8"),
    ("p19_dev_evolve",     "开发模式自进化 (满8次→提议改dev_sop/晋升learnings, 全待审)", "L7"),
]


# ===== 自演化跑动频率 (设置页可点选, 存挂载目录 → 改了实时生效, 不用重建镜像) =====
def _sched_config_path() -> Path:
    """优先存进挂载的 backend/data (实时/持久); 取不到则退回本模块 data 目录."""
    try:
        from ..runtime_paths import backend_data_dir
        return backend_data_dir() / "schedule_config.json"
    except Exception:
        return DB_PATH.parent / "schedule_config.json"


def _load_interval_days() -> int:
    """读自动跑间隔(天). 优先 schedule_config.json, 再退环境变量, 默认 3. 夹在 1..30."""
    p = _sched_config_path()
    try:
        if p.is_file():
            n = int(json.loads(p.read_text(encoding="utf-8")).get("evolver_interval_days", 3))
            return min(30, max(1, n))
    except Exception:
        pass
    try:
        return min(30, max(1, int(os.environ.get("BEE_EVOLVER_INTERVAL_DAYS", "3"))))
    except Exception:
        return 3


def _save_interval_days(n: int) -> None:
    p = _sched_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"evolver_interval_days": int(n)}, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def _interval_trigger(n: int):
    """n=1 每天 02:00; n>1 每 n 天 02:00."""
    from apscheduler.triggers.cron import CronTrigger
    return (CronTrigger(hour=2, minute=0) if n <= 1
            else CronTrigger(day=f"*/{n}", hour=2, minute=0))


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


def _run_knowledge_digest() -> None:
    """v9 每天 20:00 cron: CEO 梳理今天联网搜到的新知 → 写进 bee-memory.
    run_digest 内部 asyncio.run; AsyncIOScheduler 把 sync job 丢线程池跑, 安全."""
    import time as _t
    try:
        from app.auto_learning.digest import run_digest
        out = run_digest()
        status = out.get("status", "unknown")
        detail = str(out)[:1000]
    except Exception as e:
        status, detail = "error", str(e)[:1000]
    try:
        rid = "kd-cron-" + uuid.uuid4().hex[:10]
        with _conn() as c:
            c.execute(
                "INSERT INTO evolution_log VALUES (?,?,?,?,?,?,?)",
                (rid, int(_t.time()), "knowledge_digest", status, detail, "cron", ""),
            )
    except Exception:
        pass


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
    _days = _load_interval_days()   # 设置页可点选的频率(天), 默认每 3 天 02:00
    sch.add_job(_run_all_evolvers_serial, _interval_trigger(_days),
                id="ev_all_02", replace_existing=True)
    # v15: 已移除 20:00 知识梳理 cron (它用 LLM 把联网新知写进 bee-memory = 自动灌书, 有花费)。
    sch.start()
    _SCHEDULER = sch
    return {"started": True, "cron": f"evolvers@02:00 每{_days}天",
            "interval_days": _days,
            "evolvers": [e for e, _, _ in EVOLVERS]}


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


def _ev_next_run() -> str | None:
    if _SCHEDULER is None:
        return None
    for j in _SCHEDULER.get_jobs():
        if j.id == "ev_all_02":
            return str(j.next_run_time)
    return None


@coordinator_router.get("/schedule-config")
def get_schedule_config() -> dict:
    """设置页读取: 当前自动跑频率(天) + 下次时间 + 可选项."""
    return {"interval_days": _load_interval_days(), "next_run": _ev_next_run(),
            "options": [1, 3, 7], "hour_utc": 2}


class ScheduleConfigIn(BaseModel):
    interval_days: int


@coordinator_router.post("/schedule-config")
def set_schedule_config(req: ScheduleConfigIn) -> dict:
    """设置页保存: 写配置 + 动态重排已运行的调度(立即生效, 不用重启容器)."""
    n = min(30, max(1, int(req.interval_days)))
    _save_interval_days(n)
    rescheduled = False
    if _SCHEDULER is not None:
        try:
            _SCHEDULER.reschedule_job("ev_all_02", trigger=_interval_trigger(n))
            rescheduled = True
        except Exception:
            try:
                _SCHEDULER.add_job(_run_all_evolvers_serial, _interval_trigger(n),
                                   id="ev_all_02", replace_existing=True)
                rescheduled = True
            except Exception:
                rescheduled = False
    return {"saved": True, "interval_days": n, "rescheduled": rescheduled,
            "next_run": _ev_next_run()}


# v5-F 升级日志 + 一键回滚 端点
from .upgrade_log import router as _upgrade_router  # noqa: E402
coordinator_router.include_router(_upgrade_router)