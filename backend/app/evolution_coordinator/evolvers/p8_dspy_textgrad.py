"""L1 Prompt 文本梯度 — 拿低分决策, 用 LLM 出"反向梯度"改进 prompt."""
from __future__ import annotations
from collections import defaultdict
from ._utils import (
    read_recent_decisions, append_log, ask_cheap_llm, parse_json_loose,
)

BAD_CONF = 0.55
MIN_PER_DEPT = 3


def run() -> dict:
    import asyncio
    decisions = read_recent_decisions(limit=50)
    if not decisions:
        return {"evolver": "p8_dspy_textgrad", "status": "no_data",
                "summary": "无决策样本"}

    bad: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for d in decisions:
        for r in d.get("dept_reports") or []:
            if float(r.get("confidence_score", 1.0)) < BAD_CONF:
                bad[(d.get("mode_id", "?"), str(r.get("dept", "")))].append({
                    "task": str(d.get("task", ""))[:200],
                    "consensus": str(r.get("consensus", ""))[:200],
                    "conf": float(r.get("confidence_score", 0)),
                })

    candidates = [(k, v) for k, v in bad.items() if len(v) >= MIN_PER_DEPT][:2]
    if not candidates:
        return {"evolver": "p8_dspy_textgrad", "status": "no_data",
                "summary": f"没有满足 ≥{MIN_PER_DEPT} 次低分的 dept"}

    gradients: list[dict] = []
    for (mode, dept), items in candidates:
        cases = "\n".join(
            f"- 任务: {it['task']}\n  回答(conf={it['conf']:.2f}): {it['consensus']}"
            for it in items[:5]
        )
        prompt = (
            f"部门 {dept} 在场景 {mode} 最近 {len(items)} 次回答都低分:\n{cases}\n\n"
            "扮演 DSPy + TextGrad. 分析根因 + 给出 system prompt 的【反向梯度】改进 (3-5 条具体建议).\n"
            '输出 strict JSON: {"root_cause":"...","gradients":["改进点1","改进点2","改进点3"]}'
        )
        try:
            text = asyncio.run(ask_cheap_llm(prompt))
            obj = parse_json_loose(text)
            if obj and obj.get("gradients"):
                gradients.append({
                    "mode_id": mode, "dept": dept,
                    "low_score_count": len(items),
                    "root_cause": obj.get("root_cause", "")[:300],
                    "gradients": obj["gradients"][:5],
                })
        except Exception:
            pass

    append_log("p8_dspy_textgrad", {
        "low_score_buckets": len(bad), "gradients": gradients,
        "decisions_scanned": len(decisions),
    })
    return {
        "evolver": "p8_dspy_textgrad", "status": "done",
        "gradients_count": len(gradients),
        "summary": f"为 {len(gradients)} 个低分部门生成文本梯度",
    }
