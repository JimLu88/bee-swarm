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
from . import planner, executor, verify, worktree, dev_bandit, records
from ..notify import wecom

SELF_HEAL_MAX = 3
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


async def _run_one(dev_id: str, task: dict[str, Any], *, repo_root: str, workdir: str,
                   test_cmd: list[str] | None, code_model: str) -> dict[str, Any]:
    """单任务: 选打法 → claude 写 → 测试 → 评审 → 自愈重试 → 记录。返回结果 dict。"""
    from . import constraints
    kind = task.get("kind", "feature")
    rec_variant = dev_bandit.recommend(kind)
    variant = rec_variant["variant"]
    hint = _sop_hint(variant)
    constraint_text = constraints.build_constraint_text(repo_root)  # CLAUDE.md+rules+learnings 注入
    spec = task["spec"]
    _emit(dev_id, "dev_task_started", task_id=task["task_id"], title=task.get("title"), variant=variant)

    code_out, test_res, rev = {}, {}, {}
    attempt = 0
    while attempt < SELF_HEAL_MAX:
        attempt += 1
        code_out = await executor.run_task(spec=spec, sop_hint=hint, constraint_text=constraint_text,
                                           workdir=workdir, model=code_model)
        test_res = await executor.run_tests(workdir=workdir, test_cmd=test_cmd)
        rev = await verify.review(spec=task["spec"], code_output=code_out.get("output", ""), test_result=test_res)
        _emit(dev_id, "dev_task_attempt", task_id=task["task_id"], attempt=attempt,
              tests_passed=test_res.get("passed"), review_score=rev.get("score"), verdict=rev.get("verdict"))
        ok = code_out.get("ok") and (not test_res.get("ran") or test_res.get("passed")) and rev.get("verdict") != "fail"
        if ok:
            break
        # 自愈: 把失败信息回喂下一轮
        fail_note = (f"\n\n[上一轮未通过, 请修复]\n测试: {test_res.get('summary','')[:1500]}\n"
                     f"评审问题: {'; '.join(rev.get('issues', []))[:800]}")
        spec = task["spec"] + fail_note

    reward = records.compute_reward(tests_passed=bool(test_res.get("passed")),
                                    review_score=float(rev.get("score", 0) or 0), human_qa=None)
    dev_bandit.record(kind, variant, reward)
    # M4: 失败/低分的教训追加进 learnings.md (只记录, 满 8 次后 p19 才提议晋升 rules, 经审批)
    if reward < 0.6 and (rev.get("issues") or not test_res.get("passed")):
        note = f"[{kind}] {task.get('title','')}: " + ("; ".join(rev.get("issues", [])[:2]) or str(test_res.get("summary", ""))[:160])
        constraints.append_learning(repo_root, note)
    rec = records.append_run(
        dev_id=dev_id, task_id=task["task_id"], title=task.get("title", ""), kind=kind,
        sop_variant=variant, tests_passed=bool(test_res.get("passed")),
        test_summary=str(test_res.get("summary", "")), review_score=float(rev.get("score", 0) or 0),
        human_qa=None, files_changed=[])
    result = {
        "task_id": task["task_id"], "title": task.get("title", ""), "kind": kind,
        "variant": variant, "attempts": attempt,
        "code_ok": bool(code_out.get("ok")), "code_error": code_out.get("error", ""),
        "tests_passed": bool(test_res.get("passed")), "test_summary": str(test_res.get("summary", ""))[:1500],
        "review_score": float(rev.get("score", 0) or 0), "verdict": rev.get("verdict"),
        "issues": rev.get("issues", []), "reward": rec["reward"], "branch": task.get("branch", ""),
    }
    _emit(dev_id, "dev_task_done", **{k: result[k] for k in ("task_id", "tests_passed", "review_score", "reward", "verdict")})
    return result


def _ready(task: dict[str, Any], done_ids: set[str]) -> bool:
    return all(d in done_ids for d in (task.get("depends_on") or []))


async def run_dev_session(*, raw_request: str, repo_root: str, test_cmd: list[str] | None = None,
                          use_worktree: bool = True, code_model: str = "",
                          qa_points: list[str] | None = None,
                          dev_id: str = "") -> dict[str, Any]:
    """开发模式主入口。返回 summary(含 pending_change_id, 等人 PR 审批)。"""
    dev_id = dev_id or ("dv-" + uuid.uuid4().hex[:12])
    _emit(dev_id, "dev_started", task=raw_request[:400], repo_root=repo_root)

    plan_res = await planner.plan(raw_request)
    tasks = plan_res["tasks"]
    _emit(dev_id, "dev_planned", spec=plan_res["spec"][:1200], task_count=len(tasks),
          tasks=[{"task_id": t["task_id"], "title": t["title"], "kind": t["kind"]} for t in tasks])

    sem = asyncio.Semaphore(max(1, _DEFAULT_PARALLEL))
    results: dict[str, dict[str, Any]] = {}
    by_id = {t["task_id"]: t for t in tasks}

    async def _guarded(task: dict[str, Any]) -> None:
        async with sem:
            wd = repo_root
            if use_worktree:
                wt = await worktree.create(repo_root, task["task_id"])
                if wt.get("ok"):
                    wd = wt["path"]
                    task["branch"] = wt.get("branch", "")
                else:
                    _emit(dev_id, "dev_worktree_fallback", task_id=task["task_id"], error=wt.get("error", ""))
            res = await _run_one(dev_id, task, repo_root=repo_root, workdir=wd,
                                 test_cmd=test_cmd, code_model=code_model)
            if use_worktree and task.get("branch"):
                await worktree.commit(repo_root, task["task_id"], f"[dev] {task.get('title','')}")
            results[task["task_id"]] = res

    # 按依赖分批并行: 依赖已完成的任务可同批跑
    remaining = list(by_id.keys())
    while remaining:
        batch = [by_id[tid] for tid in remaining if _ready(by_id[tid], set(results.keys()))]
        if not batch:  # 依赖成环兜底: 全跑
            batch = [by_id[tid] for tid in remaining]
        await asyncio.gather(*[_guarded(t) for t in batch])
        remaining = [tid for tid in remaining if tid not in results]

    ordered = [results[t["task_id"]] for t in tasks if t["task_id"] in results]
    passed = sum(1 for r in ordered if r["tests_passed"])
    avg_score = round(sum(r["review_score"] for r in ordered) / max(1, len(ordered)), 3)

    # verify 第三路: 人类测试员肉眼+鼠标走查 (仅当用户给了测试点 + PC 应用已起). best-effort.
    human_qa: dict[str, Any] | None = None
    if qa_points:
        try:
            from . import human_tester
            human_qa = await human_tester.run_human_test(test_points=qa_points, dev_id=dev_id)
        except Exception as e:
            _emit(dev_id, "dev_human_qa_error", error=repr(e))

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
