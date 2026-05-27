from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .settings import settings as core_app_settings


DeptName = Literal[
    "business",
    "design",
    "efficiency",
    "finance",
    "security",
    "benchmark",
    "xlab",
    "arch",
    "logic",
    "ui",
    "database",
    "symptom",
    "nutrition",
    "drug_interactions",
    "psych",
    "macro_policy",
    "financial_reports",
    "technical_indicators",
    "smart_money",
    "visa",
    "flight_value",
    "local_safety",
    "culture_taboos",
]


class DecisionStartRequest(BaseModel):
    task: str = Field(min_length=1, max_length=20_000)
    mode_id: str = Field(default="program_management", min_length=1, max_length=64)
    # Phase 6: when true, unknown mode_id returns 422 instead of silently using program_management.
    reject_unknown_mode: bool = False
    # v1.2 N-round debate (1-5). Default 1 == single pass, backward-compatible.
    debate_rounds: int = Field(default=1, ge=1, le=5)
    # v1.5 / L-infinity thinking frameworks (optional)
    thinking_frameworks: list[str] = Field(default_factory=list)


class DecisionEstimateRequest(BaseModel):
    """v4-B triage + estimate."""

    task: str = Field(min_length=1, max_length=20_000)
    mode_id: str = Field(default="program_management", min_length=1, max_length=64)
    debate_rounds: int = Field(default=1, ge=1, le=5)


class DecisionEstimateResponse(BaseModel):
    difficulty: int = Field(ge=1, le=4, description="1=light/2=med/3=heavy/4=extra")
    type: str = Field(description="office|decision|coding|intel|mixed")
    confidence: float = Field(default=0.6, ge=0, le=1)
    reason: str = Field(default="")
    estimate_tokens: int = Field(default=0, ge=0)
    estimate_yuan: float = Field(default=0.0, ge=0)
    eta_sec: int = Field(default=0, ge=0)
    suggested_frameworks: list[str] = Field(default_factory=list)


class PriceCardEntry(BaseModel):
    model: str
    input_per_million_usd: float
    output_per_million_usd: float
    input_per_million_yuan: float
    output_per_million_yuan: float


class PriceCardResponse(BaseModel):
    """GET /api/llm/price-card."""

    fx_rate_cny_per_usd: float = 7.2
    entries: list[PriceCardEntry] = Field(default_factory=list)


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
    scenario_description: str | None = None
    default_task_hint: str | None = None
    gene_seeds: dict[str, str] = Field(default_factory=dict)
    scenario_yaml: str | None = Field(default=None, description="Basename of applied scenario file, if any.")


class GeneEvolveRequest(BaseModel):
    """DSPy-style meta-prompt: propose an improved shadow gene from active + task sample."""

    task_sample: str = ""
    save_shadow: bool = True
    require_gate: bool = False
    gate_trials: int = 5
    min_lb95_delta: float = 0.0


class GeneRegenerateSlotRequest(BaseModel):
    """CEO regenerates one slot (3+1 team) function and persona."""

    slot: Literal["member_a", "member_b", "member_c", "lead"]
    preference: str = ""


class GenesBulkSaveRequest(BaseModel):
    """Bulk upsert active gene prompts for a business mode (mode_id)."""

    prompts: dict[str, str] = Field(default_factory=dict)


class GenesGenerateRequest(BaseModel):
    """AI-generate department prompts using current LiteLLM routing."""

    overwrite: bool = True


class GenesTeamsSaveRequest(BaseModel):
    """Bulk save 3+1 team per department (mode_id)."""

    teams: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ScenarioValidateRequest(BaseModel):
    """Phase 7 authoring aid: validate YAML dicts before saving to disk."""

    kind: Literal["root_overlay", "extra_mode"]
    mode_id: str = Field(default="program_management", min_length=1, max_length=64)
    yaml: dict[str, Any] = Field(default_factory=dict)


class ScenarioScaffoldRequest(BaseModel):
    """Phase 7 authoring aid: generate starter YAML for extra modes."""

    mode_id: str = "your_mode_id"


class ScenarioWriteRequest(BaseModel):
    """Phase 9: write YAML to backend/scenarios/ or backend/scenarios/extra/."""

    kind: Literal["root_overlay", "extra_mode"]
    mode_id: str = Field(default="program_management", min_length=1, max_length=64)
    yaml_text: str = Field(min_length=1, max_length=200_000)
    overwrite: bool = True
    reload_modes: bool = False


class ScenarioRollbackRequest(BaseModel):
    """Phase 10: rollback an existing scenario file to a prior history snapshot."""

    kind: Literal["root_overlay", "extra_mode"]
    mode_id: str = Field(default="program_management", min_length=1, max_length=64)
    history_path: str = Field(min_length=1, max_length=500)
    reload_modes: bool = False


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
    rag_retrieval_meta: dict[str, Any] = Field(default_factory=dict)
    raw_debate: list[dict[str, Any]] = Field(default_factory=list)


class HeatmapCell(BaseModel):
    dept: DeptName
    confidence_score: float = Field(ge=0.0, le=1.0)
    dissent_intensity: float = Field(ge=0.0, le=1.0)
    alert: Literal["green", "yellow", "red"]
    debate_log_id: str


class DecisionSummary(BaseModel):
    decision_id: str
    task: str
    mode_id: str = ""
    mode_label: str = ""
    heatmap: list[HeatmapCell] = Field(default_factory=list)
    dept_reports: list[DeptLeadReport] = Field(default_factory=list)
    ceo_decision: str = ""
    red_team_risks: list[str] = Field(default_factory=list)
    dispatcher: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
    rag_aggregate: dict[str, Any] | None = None


class StreamEvent(BaseModel):
    type: str
    decision_id: str
    payload: dict[str, Any] = Field(default_factory=dict)