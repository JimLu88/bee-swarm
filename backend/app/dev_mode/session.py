"""session — 开发模式 dev-loop 状态机主入口.

INTENT → OPTIMIZE_SPEC → PLAN_TASKS → [并行]PER_TASK{ WORKTREE → CODE(claude) →
  VERIFY(测试+评审) →(失败)SELF_HEAL↺ } → AGGREGATE → PR_GATE(审批+企业微信) → RECORD → END
每阶段经 stream_bus 推 dev_* 事件给前端。合并由 /api/dev/{id}/approve 调 merge_session 真执行。
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Any

import yaml

from ..stream_bus import bus
from ..models import StreamEvent
from ..tools.seven_clients import bee_clients
from . import planner, executor, verify, worktree, dev_bandit, records, dev_state
from ..notify import wecom

# 成功率收敛(替代固定轮数 SELF_HEAL_MAX=3):
# - reward >= TARGET_REWARD 且测试/评审过关 → 成功停
# - 连续 PLATEAU_PATIENCE 轮 reward 不再上升 → 收敛停滞 → 停(尽力而为)
# - 到 MAX_ATTEMPTS 硬上限 → 停(防烧 claude 配额)
TARGET_REWARD = float(os.environ.get("BEE_DEV_TARGET_REWARD", "0.85"))
MAX_ATTEMPTS = int(os.environ.get("BEE_DEV_MAX_ATTEMPTS", "8"))
PLATEAU_PATIENCE = int(os.environ.get("BEE_DEV_PLATEAU", "2"))
_DEFAULT_PARALLEL = int(os.environ.get("DEV_MAX_PARALLEL", "3"))


def _emit(dev_id: str, type_: str, **payload: Any) -> None:
    try:
        bus.publish(StreamEvent(type=type_, decision_id=dev_id, payload=payload))
    except Exception:
        pass


def _sop_hint(variant: str) -> str:
    try:
        p = Path(__file__).resolve().parent.parent / "prompts" / "dev_sop.yaml"
        sop = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return str((sop.get("sop_variants") or {}).get(variant, ""))
    except Exception:
        return ""


async def _human_gate(dev_id: str, qa_points: list[str]) -> dict[str, Any] | None:
    """真机门: human_tester 截屏+真点击走查测试点。best-effort, 失败返回 None 不阻断。"""
    try:
        from . import human_tester
        return await human_tester.run_human_test(test_points=qa_points, dev_id=dev_id)
    except Exception as e:
        _emit(dev_id, "dev_human_qa_error", error=repr(e))
        return None


async def _run_one(dev_id: str, task: dict[str, Any], *, repo_root: str, workdir: str,
                   test_cmd: list[str] | None, code_model: str,
                   qa_points: list[str] | None = None) -> dict[str, Any]:
    """单任务成功率收敛环: claude 写→测试→评审, reward 达标/停滞/卡死/上限即停;
    达标后过一次真机门(human_tester), 真机 fail 回炉一轮; 全程响应 STOP / 配额暂停。"""
    from . import constraints
    kind = task.get("kind", "feature")
    rec_variant = dev_bandit.recommend(kind)
    variant = rec_variant["variant"]
    hint = _sop_hint(variant)
    constraint_text = constraints.build_constraint_text(repo_root)  # CLAUDE.md+rules+learnings 注入
    base_spec = task["spec"]
    spec = base_spec
    _emit(dev_id, "dev_task_started", task_id=task["task_id"], title=task.get("title"), variant=variant)

    code_out, test_res, rev = {}, {}, {}
    human_qa: dict[str, Any] | None = None
    best_reward, plateau, last_sig, attempt = -1.0, 0, None, 0
    outcome = "fail"   # success|plateau|stuck|fail|stopped|paused
    while attempt < MAX_ATTEMPTS:
        if dev_state.is_stopped():
            outcome = "stopped"; break
        attempt += 1
        code_out = await executor.run_task(spec=spec, sop_hint=hint, constraint_text=constraint_text,
                                           workdir=workdir, model=code_model, dev_id=dev_id)
        if code_out.get("stopped"):
            outcome = "stopped"; break
        if code_out.get("paused"):
            outcome = "paused"; break
        test_res = await executor.run_tests(workdir=workdir, test_cmd=test_cmd)
        rev = await verify.review(spec=base_spec, code_output=code_out.get("output", ""), test_result=test_res)
        reward = records.compute_reward(tests_passed=bool(test_res.get("passed")),
                                        review_score=float(rev.get("score", 0) or 0), human_qa=None)
        _emit(dev_id, "dev_task_attempt", task_id=task["task_id"], attempt=attempt,
              tests_passed=test_res.get("passed"), review_score=rev.get("score"),
              verdict=rev.get("verdict"), reward=reward)
        gate = (code_out.get("ok") and (not test_res.get("ran") or test_res.get("passed"))
                and rev.get("verdict") != "fail" and reward >= TARGET_REWARD)
        if gate:
            outcome = "success"; break
        # 卡死检测: 改动+测试+评审完全没变 = 原地踏步
        sig = (str(code_out.get("output", ""))[:400], str(test_res.get("summary", ""))[:300], rev.get("verdict"))
        if sig == last_sig:
            outcome = "stuck"; break
        last_sig = sig
        # 收敛停滞: reward 连续不再上升
        if reward > best_reward + 0.01:
            best_reward, plateau = reward, 0
        else:
            plateau += 1
            if plateau >= PLATEAU_PATIENCE:
                outcome = "plateau"; break
        spec = base_spec + (f"\n\n[上一轮 reward={reward}, 未达标, 请针对性修复]\n"
                            f"测试: {str(test_res.get('summary',''))[:1500]}\n"
                            f"评审问题: {'; '.join(rev.get('issues', []))[:800]}")

    # 真机门: 仅 success 且给了测试点且未被停 → 跑一次人工走查; fail 回炉一轮
    if outcome == "success" and qa_points and not dev_state.is_stopped():
        human_qa = await _human_gate(dev_id, qa_points)
        if human_qa and int(human_qa.get("failed", 0) or 0) > 0 and not dev_state.is_stopped():
            fails = "; ".join(str(p.get("note", "")) for p in human_qa.get("points", []) if p.get("result") == "fail")
            spec = base_spec + f"\n\n[真机走查发现问题, 请修复]\n{fails[:800]}"
            redo = await executor.run_task(spec=spec, sop_hint=hint, constraint_text=constraint_text,
                                           workdir=workdir, model=code_model, dev_id=dev_id)
            if redo.get("paused"):
                outcome = "paused"
            elif not redo.get("stopped"):
                code_out = redo
                test_res = await executor.run_tests(workdir=workdir, test_cmd=test_cmd)
                rev = await verify.review(spec=base_spec, code_output=code_out.get("output", ""), test_result=test_res)
                human_qa = await _human_gate(dev_id, qa_points)

    reward = records.compute_reward(tests_passed=bool(test_res.get("passed")),
                                    review_score=float(rev.get("score", 0) or 0), human_qa=human_qa)
    dev_bandit.record(kind, variant, reward)
    # M4: 失败/低分的教训追加进 learnings.md (只记录, 满 8 次后 p19 才提议晋升 rules, 经审批)
    if reward < 0.6 and (rev.get("issues") or not test_res.get("passed")):
        note = f"[{kind}] {task.get('title','')}: " + ("; ".join(rev.get("issues", [])[:2]) or str(test_res.get("summary", ""))[:160])
        constraints.append_learning(repo_root, note)
    rec = records.append_run(
        dev_id=dev_id, task_id=task["task_id"], title=task.get("title", ""), kind=kind,
        sop_variant=variant, tests_passed=bool(test_res.get("passed")),
        test_summary=str(test_res.get("summary", "")), review_score=float(rev.get("score", 0) or 0),
        human_qa=human_qa, files_changed=[])
    result = {
        "task_id": task["task_id"], "title": task.get("title", ""), "kind": kind,
        "variant": variant, "attempts": attempt, "outcome": outcome,
        "code_ok": bool(code_out.get("ok")), "code_error": code_out.get("error", ""),
        "tests_passed": bool(test_res.get("passed")), "test_summary": str(test_res.get("summary", ""))[:1500],
        "review_score": float(rev.get("score", 0) or 0), "verdict": rev.get("verdict"),
        "issues": rev.get("issues", []), "reward": rec["reward"], "branch": task.get("branch", ""),
        "human_qa": human_qa or {},
    }
    _emit(dev_id, "dev_task_done", outcome=outcome,
          **{k: result[k] for k in ("task_id", "tests_passed", "review_score", "reward", "verdict")})
    return result


def _ready(task: dict[str, Any], done_ids: set[str]) -> bool:
    return all(d in done_ids for d in (task.get("depends_on") or []))


async def run_dev_session(*, raw_request: str, repo_root: str, test_cmd: list[str] | None = None,
                          use_worktree: bool = True, code_model: str = "",
                          qa_points: list[str] | None = None,
                          dev_id: str = "") -> dict[str, Any]:
    """开发模式主入口。返回 summary(含 pending_change_id, 等人 PR 审批)。"""
    dev_id = dev_id or ("dv-" + uuid.uuid4().hex[:12])
    dev_state.clear_stop()  # 新 session 清除上次残留的 STOP 信号
    _emit(dev_id, "dev_started", task=raw_request[:400], repo_root=repo_root)

    plan_res = await planner.plan(raw_request)
    tasks = plan_res["tasks"]
    _emit(dev_id, "dev_planned", spec=plan_res["spec"][:1200], task_count=len(tasks),
          tasks=[{"task_id": t["task_id"], "title": t["title"], "kind": t["kind"]} for t in tasks])

    sem = asyncio.Semaphore(max(1, _DEFAULT_PARALLEL))
    results: dict[str, dict[str, Any]] = {}
    by_id = {t["task_id"]: t for t in tasks}
    halt = {"reason": ""}  # paused(配额) / stopped(STOP) → 停止派新批次

    async def _guarded(task: dict[str, Any]) -> None:
        async with sem:
            if dev_state.is_stopped():
                halt["reason"] = "stopped"
                results[task["task_id"]] = {
                    "task_id": task["task_id"], "title": task.get("title", ""), "outcome": "stopped",
                    "tests_passed": False, "review_score": 0.0, "reward": 0.0,
                    "verdict": "", "issues": [], "branch": task.get("branch", ""), "human_qa": {}}
                return
            wd = repo_root
            if use_worktree:
                wt = await worktree.create(repo_root, task["task_id"])
                if wt.get("ok"):
                    wd = wt["path"]
                    task["branch"] = wt.get("branch", "")
                else:
                    _emit(dev_id, "dev_worktree_fallback", task_id=task["task_id"], error=wt.get("error", ""))
            res = await _run_one(dev_id, task, repo_root=repo_root, workdir=wd,
                                 test_cmd=test_cmd, code_model=code_model, qa_points=qa_points)
            if use_worktree and task.get("branch"):
                await worktree.commit(repo_root, task["task_id"], f"[dev] {task.get('title','')}")
            results[task["task_id"]] = res
            if res.get("outcome") in ("paused", "stopped"):
                halt["reason"] = res["outcome"]

    # 按依赖分批并行: 依赖已完成的任务可同批跑; STOP/配额暂停则停止派新批次
    remaining = list(by_id.keys())
    while remaining and not halt["reason"] and not dev_state.is_stopped():
        batch = [by_id[tid] for tid in remaining if _ready(by_id[tid], set(results.keys()))]
        if not batch:  # 依赖成环兜底: 全跑
            batch = [by_id[tid] for tid in remaining]
        await asyncio.gather(*[_guarded(t) for t in batch])
        remaining = [tid for tid in remaining if tid not in results]

    ordered = [results[t["task_id"]] for t in tasks if t["task_id"] in results]
    passed = sum(1 for r in ordered if r.get("tests_passed"))
    avg_score = round(sum(r.get("review_score", 0) for r in ordered) / max(1, len(ordered)), 3)
    # 真机门已下放 _run_one(达标后跑一次, fail 回炉); 这里聚合各任务真机结果
    hq_pass = sum(int((r.get("human_qa") or {}).get("passed", 0) or 0) for r in ordered)
    hq_fail = sum(int((r.get("human_qa") or {}).get("failed", 0) or 0) for r in ordered)
    human_qa: dict[str, Any] | None = {"passed": hq_pass, "failed": hq_fail} if (hq_pass or hq_fail) else None

    # 配额暂停: 存档进度 + 通知, 提前返回(不进 PR 闸门, 待恢复续跑)
    if halt["reason"] == "paused":
        dev_state.save_pause(dev_id, {
            "raw_request": raw_request, "repo_root": repo_root, "test_cmd": test_cmd,
            "use_worktree": use_worktree, "code_model": code_model, "qa_points": qa_points,
            "spec": plan_res["spec"], "done_task_ids": list(results.keys()),
            "remaining_task_ids": remaining, "tasks_done": ordered})
        _emit(dev_id, "dev_paused", reason="quota", done=len(ordered), remaining=len(remaining))
        try:
            wecom.notify_markdown(
                f"**⏸ 开发暂停(配额用尽) {dev_id}**\n已完成 {len(ordered)} 任务, 剩 {len(remaining)} 个待续。\n"
                f"> 配额恢复后自动续跑(也可在前端手动点继续)。")
        except Exception:
            pass
        return {"dev_id": dev_id, "status": "paused_quota", "done": len(ordered),
                "remaining": len(remaining), "tasks": ordered, "spec": plan_res["spec"]}

    # STOP: 用户手动停止, 提前返回(已完成的任务保留, 可单独审批合并)
    if halt["reason"] == "stopped" or dev_state.is_stopped():
        _emit(dev_id, "dev_stopped", done=len(ordered))
        try:
            wecom.notify_markdown(f"**⏹ 开发已停止 {dev_id}**\n用户手动停止, 已完成 {len(ordered)} 任务。")
        except Exception:
            pass
        return {"dev_id": dev_id, "status": "stopped", "done": len(ordered), "tasks": ordered}

    # PR 人类闸门: 提交 pending_changes + 企业微信提醒
    branches = [r["branch"] for r in ordered if r.get("branch")]
    pc_id = ""
    try:
        from .. import pending_changes
        desc = (f"开发模式 {dev_id}: {len(ordered)} 任务, 测试通过 {passed}/{len(ordered)}, "
                f"评审均分 {avg_score}。审批后合并分支: {', '.join(branches) or '(直接在工作区)'}")
        proposal = {"dev_id": dev_id, "repo_root": repo_root, "branches": branches,
                    "tasks": ordered, "spec": plan_res["spec"]}
        pc_id = pending_changes.submit_change(
            evolver="dev_mode", kind="dev_pr", target=repo_root,
            description=desc, proposal=proposal)
    except Exception as e:
        _emit(dev_id, "dev_pr_gate_error", error=repr(e))

    try:
        wecom.notify_markdown(
            f"**🛠 开发待审 {dev_id}**\n任务 {len(ordered)} 个 · 测试 {passed}/{len(ordered)} 通过 · 评审 {avg_score}\n"
            f"> 去 H-SEMAS「待审通道」批准后合并 (change: {pc_id or '提交失败'})")
    except Exception:
        pass

    summary = {"dev_id": dev_id, "spec": plan_res["spec"], "tasks": ordered,
               "passed": passed, "total": len(ordered), "avg_score": avg_score,
               "branches": branches, "pending_change_id": pc_id, "human_qa": human_qa,
               "status": "awaiting_pr_approval"}
    _emit(dev_id, "dev_pr_gate", pending_change_id=pc_id, passed=passed, total=len(ordered),
          avg_score=avg_score, branches=branches, repo_root=repo_root)
    return summary


async def resume_dev_session(dev_id: str) -> dict[str, Any]:
    """配额恢复后续跑一个暂停的 dev session。读存档→清暂停态→用原需求重跑(已完成任务幂等快速通过)。"""
    st = dev_state.load_pause(dev_id)
    if not st:
        return {"ok": False, "error": f"无暂停存档: {dev_id}"}
    dev_state.clear_pause(dev_id)
    _emit(dev_id, "dev_resumed", remaining=len(st.get("remaining_task_ids", [])))
    return await run_dev_session(
        raw_request=st.get("raw_request", ""), repo_root=st.get("repo_root", ""),
        test_cmd=st.get("test_cmd"), use_worktree=bool(st.get("use_worktree", True)),
        code_model=st.get("code_model", ""), qa_points=st.get("qa_points"), dev_id=dev_id)


async def merge_session(*, repo_root: str, branches: list[str], dev_id: str = "") -> dict[str, Any]:
    """PR 批准后真合并各分支到当前分支, 并清理 worktree。经 agent_exec 跑 git。"""
    merged, failed = [], []
    for br in branches:
        res = await asyncio.to_thread(bee_clients.agent_exec, ["git", "merge", "--no-edit", br],
                                      workdir=repo_root, timeout=120)
        (merged if res.get("ok") else failed).append({"branch": br, "detail": (res.get("stderr") or res.get("error") or "")[:300]})
    # 清理 worktree (task_id = 分支去掉 dev/ 前缀)
    for br in branches:
        tid = br.split("/", 1)[1] if "/" in br else br
        try:
            await worktree.remove(repo_root, tid)
        except Exception:
            pass
    if dev_id:
        _emit(dev_id, "dev_merged", merged=[m["branch"] for m in merged], failed=[f["branch"] for f in failed])
    return {"ok": not failed, "merged": merged, "failed": failed}
