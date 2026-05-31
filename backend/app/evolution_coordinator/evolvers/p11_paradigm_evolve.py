"""L∞ 思维范式进化 — 统计 v3-B 模板被采用率, 推荐 prune/boost."""
from __future__ import annotations
from collections import Counter
from ._utils import (
    BACKEND_ROOT, read_recent_decisions, append_log, list_teams,
)


def run() -> dict:
    decisions = read_recent_decisions(limit=80)
    teams = list_teams()

    templates_dir = BACKEND_ROOT / "app" / "persona" / "function_templates"
    templates = []
    if templates_dir.is_dir():
        for f in templates_dir.glob("*.json"):
            templates.append(f.stem)

    paradigm_usage: Counter[str] = Counter()
    for d in decisions:
        for r in d.get("dept_reports") or []:
            for db in r.get("raw_debate") or []:
                content = str(db.get("content", "")).lower()
                for t in templates:
                    if t.lower() in content:
                        paradigm_usage[t] += 1

    if not templates:
        return {"evolver": "p11_paradigm_evolve", "status": "no_data",
                "summary": "未发现 function_templates"}

    total_chances = max(1, len(decisions))
    recommendations = []
    for t in templates:
        n = paradigm_usage.get(t, 0)
        rate = n / total_chances
        verdict = ("boost" if rate >= 0.3
                   else "keep" if rate >= 0.05
                   else "consider_prune")
        recommendations.append({
            "template": t, "uses": n, "rate": round(rate, 3),
            "verdict": verdict,
        })

    append_log("p11_paradigm_evolve", {
        "paradigm_usage": dict(paradigm_usage),
        "recommendations": recommendations,
        "decisions_scanned": len(decisions),
        "teams_loaded": len(teams),
    })
    boost = sum(1 for r in recommendations if r["verdict"] == "boost")
    prune = sum(1 for r in recommendations if r["verdict"] == "consider_prune")
    return {
        "evolver": "p11_paradigm_evolve", "status": "done",
        "templates_total": len(templates),
        "boost_count": boost, "prune_count": prune,
        "summary": f"扫 {len(templates)} 模板, 建议 boost {boost} 个, prune {prune} 个",
    }
