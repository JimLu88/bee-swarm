from __future__ import annotations

from typing import Any

_TASK_PREVIEW_CHARS = 180
_CEO_PREVIEW_CHARS = 240


def _trunc(text: str | None, *, max_chars: int) -> str | None:
    if text is None:
        return None
    s = str(text)
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1].rstrip() + "…"


def compact_decision_row(row: dict[str, Any]) -> dict[str, Any]:
    """Strip heavy blobs for list endpoints; client loads full summary via GET .../decision/{{id}}."""
    dsp = row.get("dispatcher") if isinstance(row.get("dispatcher"), dict) else {}
    hm = row.get("heatmap") if isinstance(row.get("heatmap"), list) else []
    slim_hm: list[dict[str, Any]] = []
    for c in hm[:20]:
        if isinstance(c, dict):
            slim_hm.append(
                {
                    "dept": c.get("dept"),
                    "alert": c.get("alert"),
                    "confidence_score": c.get("confidence_score"),
                    "dissent_intensity": c.get("dissent_intensity"),
                }
            )

    ex = row.get("execution") if isinstance(row.get("execution"), dict) else {}
    qa = ex.get("qa_sandbox") if isinstance(ex.get("qa_sandbox"), dict) else {}
    exec_ = ex.get("executor") if isinstance(ex.get("executor"), dict) else {}
    probe = exec_.get("suggested_cli_probe") if isinstance(exec_.get("suggested_cli_probe"), dict) else {}

    slim_probe: dict[str, Any] | None = None
    if probe:
        slim_probe = {"enabled": probe.get("enabled"), "argv": probe.get("argv")}

    execution_slim: dict[str, Any] | None = None
    if ex:
        execution_slim = {
            "qa_sandbox": {"ok": qa.get("ok"), "sandbox": qa.get("sandbox")},
            "executor": {
                "status": exec_.get("status"),
                "blocked_reason": exec_.get("blocked_reason"),
                "version": exec_.get("version"),
                "suggested_cli_probe": slim_probe,
            },
        }

    dept_reports = row.get("dept_reports") if isinstance(row.get("dept_reports"), list) else []
    depts = [r.get("dept") for r in dept_reports if isinstance(r, dict)]

    task_full = row.get("task")
    ceo_full = row.get("ceo_decision")

    return {
        "decision_id": row.get("decision_id"),
        "task": _trunc(task_full, max_chars=_TASK_PREVIEW_CHARS),
        "task_truncated": bool(task_full is not None and len(str(task_full)) > _TASK_PREVIEW_CHARS),
        "created_at": row.get("created_at"),
        "mode_id": row.get("mode_id"),
        "mode_label": row.get("mode_label"),
        "ceo_decision": _trunc(ceo_full if ceo_full is None else str(ceo_full), max_chars=_CEO_PREVIEW_CHARS),
        "ceo_decision_truncated": bool(ceo_full is not None and len(str(ceo_full)) > _CEO_PREVIEW_CHARS),
        "red_team_risks": (row.get("red_team_risks") or [])[:5],
        "dispatcher": {
            "level": dsp.get("level"),
            "urgency": dsp.get("urgency"),
            "notes": dsp.get("notes"),
        },
        "heatmap": slim_hm,
        "execution": execution_slim,
        "dept_reports_preview": {"count": len(dept_reports), "depts": depts},
        "_compact": True,
    }
