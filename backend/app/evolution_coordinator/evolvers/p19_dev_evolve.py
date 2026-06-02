"""p19_dev_evolve — 开发模式自进化器 (满 8 次成功跑批才提议, 全部经 pending_changes 审批).

夜间 cron 调 run():
- 闸门: records.can_auto_evolve() (≥8 次成功跑批) 才动, 否则只回报进度。
- 提案 A (dev_rule_promote): 每个 repo 把未晋升 learnings(≤5)提议晋升为 rules → 待审。
- 提案 B (dev_sop_tweak): 分析 dev_runs 里哪种打法(sop_variant)长期低分 → 提议调整 dev_sop → 待审。
全部走 pending_changes.submit_change, 你在「待审通道」点头才生效 (dev_rule_promote 审批后自动写 rules)。
纯数据分析, 不需 LLM; sync run() 供 coordinator importlib 调用。
"""

from __future__ import annotations

from typing import Any


def _analyze_variants(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    agg: dict[str, dict[str, float]] = {}
    for r in runs:
        v = str(r.get("sop_variant") or "?")
        a = agg.setdefault(v, {"n": 0.0, "reward_sum": 0.0, "fail": 0.0})
        a["n"] += 1
        a["reward_sum"] += float(r.get("reward", 0) or 0)
        if not r.get("tests_passed"):
            a["fail"] += 1
    out = []
    for v, a in agg.items():
        n = a["n"] or 1
        out.append({"variant": v, "n": int(a["n"]), "avg_reward": round(a["reward_sum"] / n, 3),
                    "fail_rate": round(a["fail"] / n, 3)})
    return sorted(out, key=lambda x: x["avg_reward"])


def run() -> dict[str, Any]:
    from app.dev_mode import records, constraints
    from app import pending_changes

    if not records.can_auto_evolve():
        return {"status": "skipped", "reason": "successful runs < threshold",
                "successful_count": records.successful_count(), "need": records.EVOLVE_THRESHOLD}

    proposals: list[str] = []

    # 提案 A: learnings → rules (每个 repo)
    for rk in constraints.list_repos():
        _, learns = constraints.learnings_for_key(rk)
        if learns:
            pc = pending_changes.submit_change(
                evolver="p19_dev_evolve", kind="dev_rule_promote", target=rk,
                description=f"开发模式: 把 {len(learns)} 条踩坑教训晋升为固定规则 ({rk})",
                proposal={"repo_key": rk, "rules": learns})
            proposals.append(pc)

    # 提案 B: dev_sop 打法分析 (长期低分的打法 → 提议调整)
    runs = records.read_runs(1000)
    variants = _analyze_variants(runs)
    weak = [v for v in variants if v["n"] >= 3 and v["avg_reward"] < 0.5]
    if weak:
        analysis = "; ".join(f"{v['variant']}(n={v['n']},均分={v['avg_reward']},失败率={v['fail_rate']})" for v in variants)
        pc = pending_changes.submit_change(
            evolver="p19_dev_evolve", kind="dev_sop_tweak", target="prompts/dev_sop.yaml",
            description=f"开发模式: 打法表现分析, 建议复盘低分打法 — {analysis}",
            proposal={"variants": variants, "weak": [v["variant"] for v in weak]})
        proposals.append(pc)

    return {"status": "done", "proposals": len(proposals), "proposal_ids": proposals,
            "successful_count": records.successful_count(), "variants": variants}
