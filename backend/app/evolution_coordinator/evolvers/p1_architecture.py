"""L4 架构演化器 — 贡献分低的部门提议合并/撤销."""
from __future__ import annotations
from collections import defaultdict
from ._utils import read_recent_decisions, append_log

THRESHOLD_CONFIDENCE = 0.55
MIN_APPEARANCES = 5


def run() -> dict:
    decisions = read_recent_decisions(limit=80)
    if len(decisions) < 10:
        return {"evolver": "p1_architecture", "status": "no_data",
                "summary": f"决策样本 {len(decisions)} 条 < 10, 不评估"}

    appear: dict[tuple[str, str], int] = defaultdict(int)
    conf_sum: dict[tuple[str, str], float] = defaultdict(float)
    for d in decisions:
        mode = d.get("mode_id", "?")
        for r in (d.get("dept_reports") or []):
            dept = str(r.get("dept", ""))
            if not dept:
                continue
            k = (mode, dept)
            appear[k] += 1
            try:
                conf_sum[k] += float(r.get("confidence_score", 0))
            except Exception:
                pass

    weak: list[dict] = []
    for k, n in appear.items():
        if n < MIN_APPEARANCES:
            continue
        avg_conf = conf_sum[k] / n
        if avg_conf < THRESHOLD_CONFIDENCE:
            weak.append({
                "mode_id": k[0], "dept": k[1],
                "appearances": n, "avg_confidence": round(avg_conf, 3),
                "suggestion": "考虑合并/撤销 — 长期低自信度",
            })

    append_log("p1_architecture", {
        "weak_depts": weak,
        "total_depts_evaluated": len([k for k, n in appear.items() if n >= MIN_APPEARANCES]),
        "decisions_scanned": len(decisions),
    })
    return {
        "evolver": "p1_architecture", "status": "done",
        "weak_dept_count": len(weak),
        "summary": (f"评估 {len(appear)} 个 dept, 发现 {len(weak)} 个长期低自信"
                    if weak else f"评估 {len(appear)} 个 dept, 全部健康"),
        "weak_sample": weak[:5],
    }
