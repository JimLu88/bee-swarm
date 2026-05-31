"""L6 自蒸馏 — 把高置信决策的 system prompt 蒸馏成更精简版, 提案 gene 更新."""
from __future__ import annotations
from collections import defaultdict
from ._utils import (
    read_recent_decisions, append_log, ask_cheap_llm, parse_json_loose,
)

MIN_PER_DEPT = 5
DISTILL_TOP_K = 2


def run() -> dict:
    import asyncio
    decisions = read_recent_decisions(limit=60)
    if len(decisions) < 10:
        return {"evolver": "p4_self_distill", "status": "no_data",
                "summary": f"决策 {len(decisions)} < 10, 不蒸馏"}

    bucket: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for d in decisions:
        mode = d.get("mode_id", "?")
        for r in d.get("dept_reports") or []:
            dept = str(r.get("dept", ""))
            if not dept:
                continue
            bucket[(mode, dept)].append({
                "consensus": str(r.get("consensus", ""))[:400],
                "conf": float(r.get("confidence_score", 0)),
            })

    ranked = sorted(
        ((k, v) for k, v in bucket.items() if len(v) >= MIN_PER_DEPT),
        key=lambda kv: (sum(x["conf"] for x in kv[1]) / len(kv[1]), len(kv[1])),
        reverse=True,
    )[:DISTILL_TOP_K]

    if not ranked:
        return {"evolver": "p4_self_distill", "status": "no_data",
                "summary": f"没有满足 ≥{MIN_PER_DEPT} 次出现的 dept"}

    proposals: list[dict] = []
    for (mode, dept), items in ranked:
        samples = "\n".join(f"- conf={it['conf']:.2f} | {it['consensus']}" for it in items[:8])
        prompt = (
            f"部门 {dept} 在场景 {mode} 下最近 {len(items)} 次的 consensus 样本:\n{samples}\n\n"
            "提取出该部门最常给出的【优质回答模式】, 总结成一段精简的 system prompt 改进建议 (150-250 字).\n"
            '输出 strict JSON: {"improved_system_prompt":"...","reason":"..."}'
        )
        try:
            text = asyncio.run(ask_cheap_llm(prompt))
            obj = parse_json_loose(text)
            if obj and obj.get("improved_system_prompt"):
                proposals.append({
                    "mode_id": mode, "dept": dept,
                    "improved_system_prompt": obj["improved_system_prompt"][:1500],
                    "reason": obj.get("reason", "")[:300],
                    "sample_count": len(items),
                })
        except Exception:
            pass

    append_log("p4_self_distill", {
        "proposals": proposals, "evaluated_depts": len(bucket),
        "decisions_scanned": len(decisions),
    })
    return {
        "evolver": "p4_self_distill", "status": "done",
        "proposals_count": len(proposals),
        "summary": f"为 top {len(proposals)} 部门提案改进 system prompt (待 p15 接管)",
    }
