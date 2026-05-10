"""Sanitized LangGraph checkpoint payload for optional debug HTTP surface."""

from __future__ import annotations

from typing import Any


def sanitize_checkpoint_values(values: dict[str, Any] | None) -> dict[str, Any]:
    """Strip heavy fields; keep structure useful for operators."""
    if not values:
        return {"empty": True}
    reports = values.get("reports") or []
    dept_list: list[str] = []
    if isinstance(reports, list):
        for r in reports:
            if isinstance(r, dict) and r.get("dept"):
                dept_list.append(str(r["dept"]))
    summary = values.get("summary")
    summary_brief: dict[str, Any] | None = None
    if isinstance(summary, dict):
        summary_brief = {
            "decision_id": summary.get("decision_id"),
            "task_preview": str(summary.get("task") or "")[:240],
            "ceo_preview": str(summary.get("ceo_decision") or "")[:240],
            "dept_reports_count": len(summary.get("dept_reports") or []),
        }
    dsp_meta = values.get("dsp_meta")
    dsp_keys = list(dsp_meta.keys()) if isinstance(dsp_meta, dict) else None
    return {
        "decision_id": values.get("decision_id"),
        "task_preview": str(values.get("task") or "")[:400],
        "mode_id": values.get("mode_id"),
        "mode_label": values.get("mode_label"),
        "departments": values.get("departments"),
        "dispatcher_meta_keys": dsp_keys,
        "reports_count": len(reports) if isinstance(reports, list) else 0,
        "report_depts_order": dept_list,
        "summary_brief": summary_brief,
    }
