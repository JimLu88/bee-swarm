from __future__ import annotations

import re
from typing import Any

from ..models import DeptLeadReport
from ..vision_scope import VISION_DEPTS


def _split_action_fragments(text: str, *, limit: int = 6) -> list[str]:
    t = text.strip()
    if not t:
        return []
    # Chinese / ASCII sentence boundaries
    parts = re.split(r"(?<=[。；;.?!])\s+|\s*[；;]\s*", t)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if len(p) < 8:
            continue
        out.append(p)
        if len(out) >= limit:
            break
    if not out and t:
        out = [t[:400] + ("…" if len(t) > 400 else "")]
    return out


def build_executor_plan(
    *,
    task: str,
    ceo_decision: str,
    dept_reports: list[DeptLeadReport],
    qa_hard_ok: bool,
) -> dict[str, Any]:
    """
    MVP \"Executor\" — produces a structured, human-executable checklist.
    Does not run shell commands or eval user code.
    """
    fragments = _split_action_fragments(ceo_decision)

    dept_snips: list[dict[str, str]] = []
    for r in dept_reports:
        if r.dept in VISION_DEPTS:
            dept_snips.append({"dept": r.dept, "highlight": str(r.consensus)[:280]})

    steps = []
    for i, frag in enumerate(fragments[:5], start=1):
        steps.append({"id": str(i), "kind": "ceo_synthesis", "text": frag})

    if qa_hard_ok and dept_snips:
        steps.append(
            {
                "id": str(len(steps) + 1),
                "kind": "cross_check_vision",
                "text": "对照 benchmark / xlab 的视野结论，验证 CEO 摘要是否遗漏关键外链或破局假设。",
                "refs": dept_snips,
            }
        )

    status = "ready" if qa_hard_ok else "blocked"
    return {
        "version": "phase3-mvp",
        "status": status,
        "blocked_reason": None if qa_hard_ok else "qa_sandbox_hard_failed",
        "task_excerpt": task[:500] + ("…" if len(task) > 500 else ""),
        "steps": steps,
    }

