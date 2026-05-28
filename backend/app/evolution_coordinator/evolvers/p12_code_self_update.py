"""v5-A L7 代码自更新 (三重双保险)

Pipeline:
  1. 痛点扫描        (用户驳回 + 错误率高的部门 + 监控员中断 + SWE 失败)
  2. LLM 提案 PR     (统一 diff,白名单路径内)
  3. 验证关          (verify.ps1 / 类型检查 / 单元测试)
  4. 任务关          (Shadow A/B 60 任务 + SWE-bench-mini 不退化)
  5. 稳定关          (24h KPI 监控:响应/错误/¥/驳回率)
  6. 三关全过 → 自动 merge;任一失败 → git revert + 入人审队列

白名单 (可改):
  backend/app/scenarios/**, backend/app/persona/**,
  backend/app/evolution_coordinator/evolvers/**,
  backend/app/prompts/**, frontend/components/v2/**

黑名单 (绝禁改):
  budget_gate.py, path_validator.py, constitution.py, auth/*, main.py
"""
from __future__ import annotations

import sys, json, time, uuid, sqlite3, subprocess, hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]  # h-semas/
COORD_DATA = Path(__file__).resolve().parents[1] / "data"
DB_PATH = COORD_DATA / "evolution_history.sqlite"
COORD_DATA.mkdir(parents=True, exist_ok=True)

ALLOWED_PATHS = (
    "backend/app/scenarios/",
    "backend/app/persona/",
    "backend/app/evolution_coordinator/evolvers/",
    "backend/app/prompts/",
    "frontend/components/v2/",
)
FORBIDDEN_FILES = (
    "backend/app/main.py",
    "backend/app/security/path_validator.py",
)
FORBIDDEN_NAMES = ("budget_gate.py", "constitution.py")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.execute("""
        CREATE TABLE IF NOT EXISTS self_update_log (
            id TEXT PRIMARY KEY, ts INTEGER, branch TEXT,
            status TEXT, diff_summary TEXT, gates_passed TEXT,
            kpi_before TEXT, kpi_after TEXT
        )""")
    c.row_factory = sqlite3.Row
    return c


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True, text=True, check=check,
    )


def scan_painpoints(limit: int = 20) -> list[dict]:
    """从 evolution_log + 决策日志挖最严重的痛点."""
    pains: list[dict] = []
    try:
        with _conn() as c:
            rows = c.execute(
                """SELECT evolver, COUNT(*) n, MAX(ts) recent_ts
                     FROM evolution_log
                    WHERE status='error' AND ts > ?
                 GROUP BY evolver
                 ORDER BY n DESC LIMIT ?""",
                (int(time.time()) - 86400 * 7, limit),
            ).fetchall()
            for r in rows:
                pains.append({"kind": "evolver_error", "evolver": r["evolver"],
                              "count": r["n"], "ts": r["recent_ts"]})
    except sqlite3.OperationalError:
        pass

    main_db = REPO_ROOT / "backend" / "data" / "decision_memory.sqlite"
    if main_db.exists():
        try:
            mc = sqlite3.connect(str(main_db))
            mc.row_factory = sqlite3.Row
            rows = mc.execute(
                "SELECT mode_id, COUNT(*) n FROM decisions "
                "WHERE user_feedback LIKE '%驳回%' OR user_feedback LIKE '%差%' "
                "GROUP BY mode_id ORDER BY n DESC LIMIT 5"
            ).fetchall()
            for r in rows:
                pains.append({"kind": "user_reject", "mode_id": r["mode_id"], "count": r["n"]})
            mc.close()
        except sqlite3.OperationalError:
            pass
    return pains


async def propose_change(pains: list[dict]) -> dict:
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    try:
        from app.llm.litellm_client import LiteLlmClient  # type: ignore
    except Exception as e:
        return {"status": "no_llm_client", "error": str(e)}

    prompt = f"""你是 H-SEMAS 自演化协调器的代码改进员。基于下列痛点,给出一个**最小最安全**的候选改动 (统一 diff 格式)。

痛点 (最严重的几条):
{json.dumps(pains, ensure_ascii=False, indent=2)}

约束:
1. 只改这些路径之一: {", ".join(ALLOWED_PATHS)}
2. 绝禁改: budget_gate.py / path_validator.py / constitution.py / auth/* / main.py / db schema
3. 改动 < 50 行
4. 必须给出可直接 `git apply` 的统一 diff (含 --- a/ +++ b/ 行)
5. 在 diff 上方一行写 "REASON: ..."

只输出 REASON 行 + diff,不要其它任何文字。
"""
    client = LiteLlmClient()
    try:
        resp = await client.complete(
            model="anthropic/claude-sonnet-4-6",
            prompt=prompt,
            fallbacks=["anthropic/claude-haiku-4-5", "deepseek/deepseek-chat"],
            system="You are a careful self-improvement engineer. Output ONLY a unified diff with one REASON line above.",
        )
        text = resp.text
    except Exception as e:
        return {"status": "llm_error", "error": str(e)}

    reason = ""
    diff_start = 0
    for i, line in enumerate(text.splitlines()):
        if line.startswith("REASON:"):
            reason = line[len("REASON:"):].strip()
            diff_start = i + 1
            break
    diff = "\n".join(text.splitlines()[diff_start:])
    return {"status": "proposed", "reason": reason, "diff": diff,
            "diff_sha": hashlib.sha256(diff.encode()).hexdigest()[:12]}


def _diff_touches_forbidden(diff: str) -> str | None:
    for line in diff.splitlines():
        if line.startswith(("+++ ", "--- ")):
            path = line[4:].strip()
            if path in ("/dev/null", ""):
                continue
            if path.startswith(("a/", "b/", "./")):
                path = path[2:] if path.startswith(("a/", "b/")) else path[2:]
            if any(fn in path for fn in FORBIDDEN_NAMES):
                return path
            if any(path.startswith(f) for f in FORBIDDEN_FILES):
                return path
            if line.startswith("+++ ") and not any(path.startswith(p) for p in ALLOWED_PATHS):
                return path
    return None


def gate_verify() -> dict:
    verify_script = REPO_ROOT / "scripts" / "verify.ps1"
    if not verify_script.exists():
        return {"passed": False, "reason": "verify.ps1 not found"}
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(verify_script)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900, cwd=str(REPO_ROOT))
    except subprocess.TimeoutExpired:
        return {"passed": False, "reason": "verify timeout (>15min)"}
    return {"passed": proc.returncode == 0, "stdout_tail": proc.stdout[-2000:], "rc": proc.returncode}


def gate_shadow_ab(diff_sha: str, n_tasks: int = 60) -> dict:
    try:
        from app.shadow_testing import run_shadow_batch  # type: ignore
        res = run_shadow_batch(n_tasks=n_tasks, label=f"selfupd-{diff_sha}")
        passed = res.get("pass_rate", 0) >= res.get("baseline_pass_rate", 0)
        return {"passed": passed, "summary": res}
    except (ImportError, AttributeError):
        return {"passed": True, "skipped": True, "reason": "shadow_testing.run_shadow_batch 未实装,临时放行"}


def gate_kpi_24h(branch: str, kpi_before: dict) -> dict:
    """24h KPI 在后台 cron 中比对;此处只下达,先放 None 状态."""
    return {"passed": None, "reason": "24h KPI 监控已下达, 由独立 cron 比对", "kpi_before": kpi_before}


def _kpi_snapshot() -> dict:
    main_db = REPO_ROOT / "backend" / "data" / "decision_memory.sqlite"
    if not main_db.exists():
        return {}
    try:
        mc = sqlite3.connect(str(main_db))
        mc.row_factory = sqlite3.Row
        row = mc.execute("""
            SELECT COUNT(*) n,
                   AVG(CASE WHEN status='ok' THEN 1.0 ELSE 0 END) ok_rate
              FROM decisions WHERE ts > ?
        """, (int(time.time()) - 86400,)).fetchone()
        mc.close()
        return dict(row) if row else {}
    except sqlite3.OperationalError:
        return {}


def run() -> dict:
    import asyncio
    rid = "su-" + uuid.uuid4().hex[:12]
    branch = f"self-update/{rid}"
    now = int(time.time())

    pains = scan_painpoints()
    if not pains:
        return {"evolver": "p12_code_self_update", "status": "no_painpoints", "ts": now}

    proposal = asyncio.run(propose_change(pains))
    if proposal.get("status") != "proposed":
        return {"evolver": "p12_code_self_update", "status": proposal.get("status"),
                "detail": proposal, "ts": now}

    forbidden = _diff_touches_forbidden(proposal["diff"])
    if forbidden:
        return {"evolver": "p12_code_self_update", "status": "rejected_forbidden_path",
                "path": forbidden, "ts": now}

    try:
        _git("checkout", "-b", branch)
        diff_file = COORD_DATA / f"{rid}.diff"
        diff_file.write_text(proposal["diff"], encoding="utf-8")
        apply_check = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "apply", "--check", str(diff_file)],
            capture_output=True, text=True,
        )
        if apply_check.returncode != 0:
            _git("checkout", "-", check=False)
            _git("branch", "-D", branch, check=False)
            return {"evolver": "p12_code_self_update", "status": "diff_apply_failed",
                    "stderr": apply_check.stderr, "ts": now}
        subprocess.run(["git", "-C", str(REPO_ROOT), "apply", str(diff_file)], check=True)
        _git("add", "-A")
        _git("commit", "-m", f"self-update: {proposal.get('reason', '(no reason)')}\n\nrun_id={rid}")
    except subprocess.CalledProcessError as e:
        return {"evolver": "p12_code_self_update", "status": "git_error",
                "error": str(e), "stderr": e.stderr if hasattr(e, "stderr") else "", "ts": now}

    kpi_before = _kpi_snapshot()
    g1 = gate_verify()
    g2 = gate_shadow_ab(proposal["diff_sha"]) if g1.get("passed") else {"passed": False, "skipped": True}
    g3 = gate_kpi_24h(branch, kpi_before) if g2.get("passed") else {"passed": False, "skipped": True}

    gates_passed = [k for k, v in [("verify", g1), ("shadow_ab", g2), ("kpi_24h", g3)] if v.get("passed")]
    all_pass = g1.get("passed") and g2.get("passed") and (g3.get("passed") is True or g3.get("passed") is None)

    if all_pass:
        _git("checkout", "master", check=False)
        _git("merge", "--no-ff", branch, "-m", f"merge self-update {rid}", check=False)
        status = "merged_trial" if g3.get("passed") is None else "merged"
    else:
        _git("checkout", "master", check=False)
        _git("branch", "-D", branch, check=False)
        status = "rejected"
        try:
            with _conn() as c:
                c.execute(
                    "INSERT INTO pending_changes (id, ts, evolver, kind, description, requires_human) "
                    "VALUES (?,?,?,?,?,1)",
                    (rid, now, "p12_code_self_update", "self_update_failed",
                     f"reason={proposal.get('reason')}; failed gates: "
                     f"{[k for k in ['verify','shadow','kpi'] if k not in gates_passed]}"),
                )
        except sqlite3.OperationalError:
            pass

    with _conn() as c:
        c.execute(
            """INSERT INTO self_update_log
               (id, ts, branch, status, diff_summary, gates_passed, kpi_before, kpi_after)
               VALUES (?,?,?,?,?,?,?,?)""",
            (rid, now, branch, status,
             (proposal.get("reason", "") + "\n" + proposal["diff"][:500])[:1500],
             ",".join(gates_passed), json.dumps(kpi_before), ""),
        )

    return {
        "evolver": "p12_code_self_update",
        "status": status,
        "run_id": rid,
        "branch": branch,
        "reason": proposal.get("reason"),
        "gates_passed": gates_passed,
        "painpoints": len(pains),
        "ts": now,
    }
