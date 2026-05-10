from __future__ import annotations

from typing import Any

from ..models import DeptLeadReport, HeatmapCell


def run_qa_sandbox(
    *,
    expected_depts: list[str],
    dept_reports: list[DeptLeadReport],
    heatmap: list[HeatmapCell],
) -> dict[str, Any]:
    """
    Deterministic QA gate — no subprocess / no arbitrary code execution.
    Hard checks block the executor \"go\" signal; soft checks are warnings only.
    """
    got = [r.dept for r in dept_reports]
    missing = sorted(set(expected_depts) - set(got))

    hard: list[dict[str, Any]] = []
    hard.append({"name": "all_depts_present", "passed": len(missing) == 0, "detail": {"missing": missing, "got": got}})

    empty: list[str] = []
    for r in dept_reports:
        if not str(r.consensus or "").strip():
            empty.append(r.dept)
    hard.append({"name": "consensus_non_empty", "passed": len(empty) == 0, "detail": {"empty_depts": empty}})

    duplicates = sorted({d for d in got if got.count(d) > 1})
    hard.append({"name": "single_report_per_dept", "passed": len(duplicates) == 0, "detail": {"duplicates": duplicates}})

    soft: list[dict[str, Any]] = []
    reds = [c.dept for c in heatmap if c.alert == "red"]
    if reds:
        soft.append({"name": "heatmap_red_escalation", "passed": True, "detail": {"red_depts": reds, "note": "需人工复盘热力图红色单元"}})

    yellows = [c.dept for c in heatmap if c.alert == "yellow"]
    if yellows:
        soft.append({"name": "heatmap_yellow_watch", "passed": True, "detail": {"yellow_depts": yellows}})

    low_conf = [(c.dept, c.confidence_score) for c in heatmap if c.confidence_score < 0.55]
    if low_conf:
        soft.append({"name": "low_confidence_cells", "passed": True, "detail": {"cells": low_conf}})

    hard_ok = bool(all(h["passed"] for h in hard))
    return {
        "ok": hard_ok,
        "sandbox": "deterministic-v1",
        "hard_checks": hard,
        "soft_warnings": soft,
    }

