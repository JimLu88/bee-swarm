from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .settings import settings as core_app_settings


DeptName = Literal[
    # shared
    "benchmark",
    "xlab",
    # general consultants
    "business",
    "design",
    "efficiency",
    "finance",
    "security",
    # program management design
    "arch",
    "logic",
    "ui",
    "database",
    # family doctor
    "symptom",
    "nutrition",
    "drug_interactions",
    "psych",
    # stock trading
    "macro_policy",
    "financial_reports",
    "technical_indicators",
    "smart_money",
    # travel planning
    "visa",
    "flight_value",
    "local_safety",
    "culture_taboos",
]


class DecisionStartRequest(BaseModel):
    task: str = Field(min_length=1, max_length=20_000)
    mode_id: str = Field(default="program_management", min_length=1, max_length=64)


class SandboxExecRequest(BaseModel):
    """White-list subprocess sandbox; argv passed to asyncio.create_subprocess_exec (never shell=True)."""

    argv: list[str]

    @field_validator("argv")
    @classmethod
    def argv_length(cls, v: list[str]) -> list[str]:
        cap = core_app_settings.hsemas_exec_max_args
        if len(v) < 1 or len(v) > cap:
            raise ValueError(f"argv_len_must_be_1_{cap}")
        return v


class ModeInfo(BaseModel):
    mode_id: str
    label: str
    departments: list[DeptName]
    department_labels: dict[str, str] = Field(default_factory=dict)


class DeptLeadReport(BaseModel):
    dept: DeptName
    consensus: str
    conflicts: list[str] = Field(default_factory=list)
    credibility_weight: float = Field(default=0.8, ge=0.0, le=1.0)
    confidence_score: float = Field(ge=0.0, le=1.0)
    dissent_intensity: float = Field(ge=0.0, le=1.0)
    debate_log_id: str
    dispatcher_context: str = ""
    rag_context: list[dict[str, Any]] = Field(default_factory=list)
    raw_debate: list[dict[str, Any]] = Field(default_factory=list)


class HeatmapCell(BaseModel):
    dept: DeptName
    confidence_score: float
    dissent_intensity: float
    alert: Literal["green", "yellow", "red"]
    debate_log_id: str


class DecisionSummary(BaseModel):
    decision_id: str
    task: str
    heatmap: list[HeatmapCell]
    dept_reports: list[DeptLeadReport]
    ceo_decision: str
    red_team_risks: list[str] = Field(default_factory=list)
    dispatcher: dict[str, Any] | None = None
    # Phase 3: deterministic QA gate + structured execution checklist (no code execution)
    execution: dict[str, Any] | None = None


class StreamEvent(BaseModel):
    type: str
    decision_id: str
    payload: dict[str, Any] = Field(default_factory=dict)

