from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .settings import settings as core_app_settings


## v6-A: DeptName 从 Literal 改 str. 让 AI 自由命名 dept (例 family_doctor 现在可以
## 拥有 internal_medicine / surgery / radiology 这种真实科室). pydantic 字段保留 DeptName
## 别名,运行时校验降级为任意字符串。已注册的 dept 集合改由 catalog.list_dept_names() 从
## modes.MODES 动态列举 (代替原来的 get_args(DeptName))。
DeptName = str


class AttachedFile(BaseModel):
    """v6-Y 用户上传的文档附件 (xlsx/pdf/docx/...). content_b64 可含 data URL 前缀."""
    name: str = Field(min_length=1, max_length=300)
    content_b64: str = Field(min_length=1, max_length=20 * 1024 * 1024)  # ~15MB 原文件


class DecisionStartRequest(BaseModel):
    task: str = Field(min_length=1, max_length=20_000)
    mode_id: str = Field(default="program_management", min_length=1, max_length=64)
    # Phase 6: when true, unknown mode_id returns 422 instead of silently using program_management.
    reject_unknown_mode: bool = False
    # v1.2 N-round debate (1-5). Default 1 == single pass, backward-compatible.
    debate_rounds: int = Field(default=1, ge=1, le=5)
    # v1.5 / L-infinity thinking frameworks (optional)
    thinking_frameworks: list[str] = Field(default_factory=list)
    # v6-W 3 档降级: A=高档旗舰, B=中档便宜云, C=离线本地 (并发限 2)
    tier: str = Field(default="A", pattern=r"^[ABC]$")
    # v6-X 多模态: data URL (data:image/png;base64,...) 或 https URL, 最多 4 张.
    # 瞎子模型自动走 vision_fallback 表换视觉兄弟; tier C 默认 ollama/llava:7b.
    images: list[str] = Field(default_factory=list, max_length=10)
    # v6-Y 文档附件: xlsx/pdf/docx/pptx/csv/txt 等, 进程内解析成文字拼进 task.
    # 文字对所有模型免费可读 (含瞎子模型), 不走视觉.
    files: list[AttachedFile] = Field(default_factory=list, max_length=5)
    # v6-Z 路线: all=全部门 / multi=CEO选多部门 / key=重点部门 / single=单部门 / ceo_only=CEO单答
    route: str = Field(default="all", pattern=r"^(all|multi|key|single|ceo_only)$")
    # v6-Z route!=all 时, 前端传 CEO/用户选定的部门子集 (route=single 则 1 个)
    departments_override: list[str] = Field(default_factory=list, max_length=40)
    # v6-Z 难度桶 (light/medium/heavy), 供 sop_bandit 记录; 空则后端自算
    difficulty_bucket: str = Field(default="", max_length=12)

    @field_validator("images")
    @classmethod
    def _validate_images(cls, v: list[str]) -> list[str]:
        # 单张 <= 8 MB base64 (约 6 MB 原图); 拒绝空串和明显非法 scheme.
        out: list[str] = []
        for s in v:
            s = (s or "").strip()
            if not s:
                continue
            if not (s.startswith("data:image/") or s.startswith("http://") or s.startswith("https://")):
                raise ValueError(f"image must be data:image/... or http(s)://, got: {s[:32]}")
            if len(s) > 8 * 1024 * 1024:
                raise ValueError(f"image too large: {len(s)} bytes (max 8MB)")
            out.append(s)
        return out


class PreflightRequest(BaseModel):
    """v6-Z CEO 预分析: 读 task → 推荐启动哪些部门 + 路线 + 轮数 (供前端 5×3 选择器)."""
    task: str = Field(min_length=1, max_length=20_000)
    mode_id: str = Field(default="program_management", min_length=1, max_length=64)
    images: list[str] = Field(default_factory=list, max_length=10)
    files: list[AttachedFile] = Field(default_factory=list, max_length=5)


class DecisionFeedbackRequest(BaseModel):
    """v6-Z 👍👎 奖励回填: bandit 学习信号. route/band/difficulty 由前端从选择时带回 (免服务端存状态)."""
    decision_id: str = Field(min_length=1, max_length=64)
    mode_id: str = Field(default="program_management", min_length=1, max_length=64)
    reward: float = Field(ge=0.0, le=1.0, description="👍=1.0 / 👎=0.0 / 1-5星归一化")
    route: str = Field(default="all", pattern=r"^(all|multi|key|single|ceo_only)$")
    rounds_band: str = Field(default="medium", pattern=r"^(heavy|medium|light)$")
    difficulty: str = Field(default="medium", pattern=r"^(light|medium|heavy)$")


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
    # v10 D: 本次该顾问从专业知识库实际读取(注入)的条数, 前端显示"读了 N 本专业书"
    kb_used: int = 0


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
    # v6-B ELO 信号:本次决策实际用了哪些 persona + model + role (从 team.yaml 提取)
    # 格式: [{"persona_id": "head_orth_xxx", "role": "head", "model": "deepseek/...", "dept_id": "symptom"}]
    team_personas_used: list[dict[str, Any]] = Field(default_factory=list)
    # 用户反馈 (👍/👎/驳回/差评), 由前端在决策完成后回写
    user_feedback: str = ""
    # v7 W3 爬虫图文聚合卡 (信息流): [{type,title,body,url,image_url,source}]
    media_cards: list[dict[str, Any]] = Field(default_factory=list)


class StreamEvent(BaseModel):
    type: str
    decision_id: str
    payload: dict[str, Any] = Field(default_factory=dict)