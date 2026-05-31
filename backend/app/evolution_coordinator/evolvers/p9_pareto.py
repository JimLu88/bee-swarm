"""多目标 Pareto — 按 (mode, dept) 三轴 (quality/cost/speed) 找 Pareto 前沿."""
from __future__ import annotations
from collections import defaultdict
from ._utils import read_recent_decisions, append_log


def run() -> dict:
    decisions = read_recent_decisions(limit=80)
    if len(decisions) < 10:
        return {"evolver": "p9_pareto", "status": "no_data",
                "summary": f"决策 {len(decisions)} < 10, 不评估"}

    bucket: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for d in decisions:
        for r in d.get("dept_reports") or []:
            dept = str(r.get("dept", ""))
            if not dept:
                continue
            bucket[(d.get("mode_id", "?"), dept)].append({
                "quality": float(r.get("confidence_score", 0.5)),
                "cost": len(str(r.get("consensus", ""))),
                "speed_proxy": 1.0 / max(1, int(
                    (r.get("rag_retrieval_meta") or {}).get("total_chunks", 1)
                )),
            })

    points = []
    for (mode, dept), arr in bucket.items():
        if len(arr) < 3:
            continue
        q = sum(x["quality"] for x in arr) / len(arr)
        c = sum(x["cost"] for x in arr) / len(arr)
        s = sum(x["speed_proxy"] for x in arr) / len(arr)
        points.append({
            "mode_id": mode, "dept": dept, "n": len(arr),
            "quality": round(q, 3), "cost": round(c, 1), "speed": round(s, 3),
        })

    if not points:
        return {"evolver": "p9_pareto", "status": "no_data",
                "summary": "没有满足 ≥3 次出现的 dept"}

    for a in points:
        dominated_by = 0
        for b in points:
            if a is b:
                continue
            if (b["quality"] >= a["quality"] and b["cost"] <= a["cost"]
                    and b["speed"] >= a["speed"] and
                    (b["quality"] > a["quality"] or b["cost"] < a["cost"]
                     or b["speed"] > a["speed"])):
                dominated_by += 1
        a["dominated_by"] = dominated_by
        a["on_frontier"] = dominated_by == 0

    frontier = [p for p in points if p["on_frontier"]]
    append_log("p9_pareto", {
        "frontier": frontier, "total_points": len(points),
        "decisions_scanned": len(decisions),
    })
    return {
        "evolver": "p9_pareto", "status": "done",
        "frontier_size": len(frontier), "total_points": len(points),
        "frontier_sample": frontier[:5],
        "summary": f"评估 {len(points)} 部门, Pareto 前沿 {len(frontier)} 个",
    }
