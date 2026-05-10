from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class DispatcherState(TypedDict, total=False):
    """Shape of run_dispatcher() output; mirrors API / persistence."""

    level: str
    urgency: str
    task_chars: int
    notes: str
    version: str
    dept_briefs: dict[str, str]


class DispatcherPersistedMeta(TypedDict, total=False):
    """Stored on DecisionSummary.dispatcher (not full dept_briefs)."""

    dept_brief_lens: dict[str, int]
    dept_brief_preview: dict[str, str]
    department_count: int


class DecisionFanoutState(TypedDict, total=False):
    """Planned shared state if/when migrating run_decision() to LangGraph."""

    decision_id: str
    task: str
    mode_id: str
    mode_label: NotRequired[str]
    departments: list[str]
    dispatcher: dict[str, Any]
    dept_reports: list[dict[str, Any]]
