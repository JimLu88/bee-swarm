"""L3 Voyager 技能繁殖 — 从成功决策蒸馏 SOP 写入 skill registry."""
from __future__ import annotations
import json
from ._utils import (
    DATA_ROOT, read_recent_decisions, append_log,
    ask_cheap_llm, parse_json_loose,
)

SKILLS_FILE = DATA_ROOT / "skills_registry.jsonl"
GOOD_CONF = 0.75
MAX_DISTILL = 8  # 每轮蒸馏上限 (技能现已被 skills_store 接进决策路由, 放宽产出)


def run() -> dict:
    import asyncio
    decisions = read_recent_decisions(limit=40)
    good = []
    for d in decisions:
        reports = d.get("dept_reports") or []
        if not reports:
            continue
        avg_conf = sum(float(r.get("confidence_score", 0)) for r in reports) / len(reports)
        if avg_conf >= GOOD_CONF:
            good.append(d)

    if len(good) < 3:
        return {"evolver": "p3_skill_breed", "status": "no_data",
                "summary": f"高置信决策 {len(good)} < 3, 不蒸馏"}

    candidates = good[:MAX_DISTILL]
    distilled = 0
    errors: list[str] = []
    for d in candidates:
        task = str(d.get("task", ""))[:400]
        ceo = str(d.get("ceo_decision", ""))[:600]
        prompt = (
            f"以下是一个成功的 AI 决策案例:\n\n"
            f"任务: {task}\n\n"
            f"答案: {ceo}\n\n"
            "请提取这次成功的【可复用 SOP】, 写成一个 skill. 输出 strict JSON:\n"
            '{"skill_id":"<snake_case>","trigger":"什么样的任务该用","steps":["1...","2..."],"applies_to":"mode_id 或 *"}'
        )
        try:
            text = asyncio.run(ask_cheap_llm(prompt))
            obj = parse_json_loose(text)
            if obj and obj.get("skill_id"):
                obj["source_decision_id"] = d.get("decision_id", "")
                with SKILLS_FILE.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(obj, ensure_ascii=False) + "\n")
                distilled += 1
        except Exception as e:
            errors.append(repr(e)[:200])

    append_log("p3_skill_breed", {
        "good_decisions": len(good), "distilled": distilled,
        "errors": errors[:3], "skills_file": str(SKILLS_FILE),
    })
    return {
        "evolver": "p3_skill_breed", "status": "done",
        "distilled_skills": distilled, "good_decisions": len(good),
        "summary": f"从 {len(good)} 个高置信决策中蒸馏 {distilled} 个 skill",
    }
