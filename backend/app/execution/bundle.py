from __future__ import annotations

from typing import Any

from ..models import DeptLeadReport, HeatmapCell
from .plan_builder import build_executor_plan
from .qa_sandbox import run_qa_sandbox


def _suggested_cli_probe() -> dict[str, Any]:
    """Non-executing hint: safe argv templates that match allow-list stems."""
    from ..settings import settings
    from .safe_shell import sandbox_allowlist

    if not settings.hsemas_sandbox_exec_enabled:
        return {"enabled": False, "reason": "sandbox_disabled"}
    stems = sorted(sandbox_allowlist())
    if not stems:
        return {"enabled": False, "reason": "allowlist_empty"}
    templates: dict[str, list[str]] = {
        "pytest": ["pytest", "--version"],
        "ruff": ["ruff", "--version"],
        "mypy": ["mypy", "--version"],
        "python": ["python", "-V"],
        "python3": ["python3", "-V"],
        "py": ["py", "-V"],
    }
    for s in stems:
        if s in templates:
            return {
                "enabled": True,
                "argv": templates[s],
                "matched_stem": s,
                "note": "仅建议：复制到 UI 或 POST /api/sandbox/exec，不自动执行",
            }
    return {
        "enabled": True,
        "argv": None,
        "allowed_stems": stems,
        "note": "无预置 --version 模板，请自行拼 argv（首项须在白名单）",
    }


def build_execution_bundle(
    *,
    expected_depts: list[str],
    task: str,
    ceo_decision: str,
    dept_reports: list[DeptLeadReport],
    heatmap: list[HeatmapCell],
) -> dict[str, Any]:
    qa = run_qa_sandbox(expected_depts=expected_depts, dept_reports=dept_reports, heatmap=heatmap)
    plan = build_executor_plan(
        task=task,
        ceo_decision=ceo_decision,
        dept_reports=dept_reports,
        qa_hard_ok=bool(qa.get("ok")),
    )
    return {"qa_sandbox": qa, "executor": {**plan, "suggested_cli_probe": _suggested_cli_probe()}}
