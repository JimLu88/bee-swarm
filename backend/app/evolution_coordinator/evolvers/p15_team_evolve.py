"""v6-B 主管自演化器.

每周一次 (建议 02:00 周一 cron):
  1. 扫 ELO 滚动 14 天 < 1400 的 persona_role / model_role
  2. 用 Opus 写 retrospective: 这个主管为什么不行?
  3. 归因: 模型问题 (model_role 也低) → 换模型; 人设问题 (persona_role 低但 model_role 正常) → 换人设
  4. 启动 14 天 Shadow: 新主管影子跑 (写 team_evolution_log shadow_until_ts)
  5. 14 天后另一次 run 会检查 shadow ELO vs 旧主管: 谁高谁上 → 自动 promote 或 rollback

存表: backend/app/evolution_coordinator/data/evolution_history.sqlite
  team_evolution_log:
    id TEXT PK, mode_id TEXT, dept_id TEXT, persona_id TEXT,
    ts INT, action TEXT, attribution TEXT, retrospective TEXT,
    new_persona_id TEXT, shadow_until_ts INT, status TEXT
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "evolution_history.sqlite"
SHADOW_DAYS = 14
ELO_FAIL_THRESHOLD = 1400
ELO_BASELINE = 1500

# v6-G: 默认要求用户审批; 设 BEE_P15_AUTO_APPROVE=1 才走老的"自动 shadow"
AUTO_APPROVE = os.environ.get("BEE_P15_AUTO_APPROVE", "0") == "1"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.execute("""
        CREATE TABLE IF NOT EXISTS team_evolution_log (
            id TEXT PRIMARY KEY,
            mode_id TEXT, dept_id TEXT, persona_id TEXT,
            ts INTEGER, action TEXT, attribution TEXT,
            retrospective TEXT, new_persona_id TEXT,
            shadow_until_ts INTEGER,
            status TEXT
        )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_team_evo_mode ON team_evolution_log(mode_id, status)")
    c.row_factory = sqlite3.Row
    return c


def _find_failing_personas() -> list[dict[str, Any]]:
    """从 elo_ratings 找 ELO 滚动 14 天 < 1400 的主管 (persona_role kind)."""
    with _conn() as c:
        rows = c.execute(
            "SELECT entity_id, rating, n_games FROM elo_ratings "
            "WHERE kind='persona_role' AND rating < ? AND n_games >= 3",
            (ELO_FAIL_THRESHOLD,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        eid = str(r["entity_id"])
        if "@" not in eid:
            continue
        pid, role = eid.split("@", 1)
        if role != "head":
            continue  # MVP: 只演化 head, staff 留给后期
        out.append({"persona_id": pid, "role": role, "elo": float(r["rating"]),
                    "n_games": int(r["n_games"])})
    return out


def _find_persona_in_teams(persona_id: str) -> tuple[str, str] | None:
    """从所有 team.yaml 反查 persona_id 属于哪个 (mode_id, dept_id)."""
    teams_dir = Path(__file__).resolve().parents[3] / "scenarios" / "teams"
    if not teams_dir.exists():
        return None
    import yaml as _yaml
    for f in teams_dir.glob("*.yaml"):
        try:
            data = _yaml.safe_load(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        mode_id = str(data.get("mode_id") or f.stem)
        for d in data.get("departments") or []:
            head = d.get("head") or {}
            if str(head.get("persona_id")) == persona_id:
                return (mode_id, str(d.get("dept_id")))
    return None


def _attribute_cause(role: str, model: str) -> str:
    """归因: 模型问题还是人设问题? 看 model_role 的 ELO 配对."""
    with _conn() as c:
        m_row = c.execute(
            "SELECT rating FROM elo_ratings WHERE kind='model_role' AND entity_id=?",
            (f"{model}@{role}",),
        ).fetchone()
    model_elo = float(m_row["rating"]) if m_row else ELO_BASELINE
    if model_elo < ELO_FAIL_THRESHOLD:
        return "model_issue"
    return "persona_issue"


async def _write_retrospective(mode_id: str, dept_id: str, persona_id: str,
                                attribution: str) -> str:
    try:
        from ...llm.litellm_client import litellm_client
    except Exception:
        return f"(retrospective unavailable, attribution={attribution})"

    cause = "模型能力问题" if attribution == "model_issue" else "人设/方法论问题"
    prompt = f"""你是 H-SEMAS 自演化系统的【失败回溯员】。

数据:
- 场景: {mode_id}
- 部门: {dept_id}
- 失败的主管 persona_id: {persona_id}
- 归因分析判定: {attribution} ({cause})
- ELO 滚动 14 天 < 1400 (基线 1500)

请用 100-200 字写一段 retrospective, 假设你查阅了这个主管最近的失败记录:
- 主要错在哪类问题 (类型, 不要瞎编具体案例)
- 应该往哪个方向改 (换模型族 / 调 OCEAN / 换 sub_specialty)
- 给重生指令一句话方向性建议

只输出 retrospective 正文, 不要 JSON, 不要标题。
"""
    try:
        resp = await litellm_client.complete(
            model="anthropic/claude-opus-4-7",
            fallbacks=["anthropic/claude-sonnet-4-6"],
            prompt=prompt,
            system="你写简短中文 retrospective, 不展开案例, 不超过 200 字。",
        )
        return resp.text.strip()
    except Exception as e:
        return f"(retrospective LLM failed: {e}; attribution={attribution})"


async def _start_shadow(mode_id: str, dept_id: str, persona_id: str, attribution: str,
                        retrospective: str) -> dict[str, Any]:
    """生成候选新主管, 写 team_evolution_log 'shadow_running'.

    MVP: 不真的并行跑业务流量 (那要改 LangGraph), 这里只 generate 新候选 + 标记。
    14 天后 second-run check shadow 结束, 比较 ELO 决定升降。
    """
    try:
        from ...persona import team_generator
        await team_generator.regenerate_persona(mode_id, dept_id, persona_id)
    except Exception as e:
        return {"status": "shadow_failed", "error": str(e)}

    now = int(time.time())
    rid = "te-" + uuid.uuid4().hex[:12]
    new_pid = f"shadow_{persona_id}_{now}"

    with _conn() as c:
        c.execute(
            """INSERT INTO team_evolution_log
               (id, mode_id, dept_id, persona_id, ts, action, attribution, retrospective,
                new_persona_id, shadow_until_ts, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (rid, mode_id, dept_id, persona_id, now, "start_shadow", attribution,
             retrospective, new_pid, now + SHADOW_DAYS * 86400, "shadow_running"),
        )
    return {
        "status": "shadow_started", "run_id": rid, "mode_id": mode_id, "dept_id": dept_id,
        "old_persona": persona_id, "new_persona": new_pid, "attribution": attribution,
        "shadow_until_ts": now + SHADOW_DAYS * 86400,
    }


def _check_shadow_outcomes() -> list[dict[str, Any]]:
    """到期的 shadow_running → 比 ELO 决定 promote / rollback."""
    now = int(time.time())
    out: list[dict[str, Any]] = []
    with _conn() as c:
        due = c.execute(
            "SELECT * FROM team_evolution_log WHERE status='shadow_running' AND shadow_until_ts <= ?",
            (now,),
        ).fetchall()
    for row in due:
        r = dict(row)
        old_pid = r["persona_id"]
        new_pid = r["new_persona_id"]
        with _conn() as c:
            old_row = c.execute(
                "SELECT rating FROM elo_ratings WHERE kind='persona_role' AND entity_id=?",
                (f"{old_pid}@head",),
            ).fetchone()
            new_row = c.execute(
                "SELECT rating FROM elo_ratings WHERE kind='persona_role' AND entity_id=?",
                (f"{new_pid}@head",),
            ).fetchone()
        old_elo = float(old_row["rating"]) if old_row else ELO_BASELINE
        new_elo = float(new_row["rating"]) if new_row else ELO_BASELINE
        decision = "promoted" if new_elo > old_elo else "rolled_back"
        with _conn() as c:
            c.execute(
                "UPDATE team_evolution_log SET status=? WHERE id=?",
                (decision, r["id"]),
            )
        out.append({
            "run_id": r["id"], "mode_id": r["mode_id"], "dept_id": r["dept_id"],
            "decision": decision, "old_elo": old_elo, "new_elo": new_elo,
        })
    return out


def run() -> dict[str, Any]:
    """主入口: 先结算到期 shadow, 再扫新的失败主管启 shadow."""
    now = int(time.time())
    shadow_outcomes = _check_shadow_outcomes()

    failing = _find_failing_personas()
    started: list[dict[str, Any]] = []
    for f in failing:
        with _conn() as c:
            existing = c.execute(
                "SELECT 1 FROM team_evolution_log "
                "WHERE persona_id=? AND status='shadow_running' LIMIT 1",
                (f["persona_id"],),
            ).fetchone()
        if existing:
            continue
        loc = _find_persona_in_teams(f["persona_id"])
        if not loc:
            continue
        mode_id, dept_id = loc

        import yaml as _yaml
        teams_dir = Path(__file__).resolve().parents[3] / "scenarios" / "teams"
        tf = teams_dir / f"{mode_id}.yaml"
        head_model = ""
        if tf.exists():
            try:
                team_data = _yaml.safe_load(tf.read_text(encoding="utf-8")) or {}
                for d in team_data.get("departments") or []:
                    if str(d.get("dept_id")) == dept_id:
                        head_model = str((d.get("head") or {}).get("model_modeA") or "")
                        break
            except Exception:
                pass

        attribution = _attribute_cause(f["role"], head_model)
        retrospective = asyncio.run(_write_retrospective(mode_id, dept_id, f["persona_id"], attribution))

        if AUTO_APPROVE:
            # 旧行为: 直接起 shadow (不需要审批)
            result = asyncio.run(_start_shadow(mode_id, dept_id, f["persona_id"], attribution, retrospective))
            started.append(result)
        else:
            # 新默认: 入 pending_changes 待审批; 用户在 ⚖️待审 抽屉 approve 后才真 regenerate
            try:
                from ...pending_changes import submit_change
                pc_id = submit_change(
                    evolver="p15_team_evolve",
                    kind="persona_regenerate",
                    target=f"{mode_id}/{dept_id}/{f['persona_id']}",
                    description=(
                        f"主管 {f['persona_id']} 在 {mode_id}/{dept_id} 表现持续偏低 "
                        f"(归因={attribution}). 建议重新生成. 14天 shadow 由你 approve 后启动."
                    ),
                    proposal={
                        "attribution": attribution,
                        "retrospective": retrospective[:1500],
                        "mode_id": mode_id, "dept_id": dept_id,
                        "persona_id": f["persona_id"],
                    },
                )
                started.append({"status": "pending_approval", "pending_id": pc_id,
                                "mode_id": mode_id, "dept_id": dept_id,
                                "persona_id": f["persona_id"], "attribution": attribution})
            except Exception as e:
                started.append({"status": "submit_failed", "error": repr(e)[:200]})

    return {
        "evolver": "p15_team_evolve",
        "status": "ok",
        "ts": now,
        "failing_found": len(failing),
        "shadow_started": started,
        "shadow_outcomes": shadow_outcomes,
        "shadow_days": SHADOW_DAYS,
    }
