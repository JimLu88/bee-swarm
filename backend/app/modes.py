from __future__ import annotations

from typing import Any, Literal

from .models import ModeInfo

ModeRegistrySource = Literal["builtin", "extra", "fallback"]
from .scenario_loader import load_scenario_dict

_EXTRA_MODES_CACHE: dict[str, ModeInfo] | None = None


def _builtin_mode_ids() -> frozenset[str]:
    return frozenset(MODES.keys())


def _extra_modes() -> dict[str, ModeInfo]:
    global _EXTRA_MODES_CACHE
    if _EXTRA_MODES_CACHE is None:
        from .extra_mode_loader import load_extra_modes

        _EXTRA_MODES_CACHE = load_extra_modes(builtin_mode_ids=_builtin_mode_ids())
    return _EXTRA_MODES_CACHE


def reload_mode_yaml_cache() -> None:
    """Clear cached extra-mode registry; next ``get_mode`` / ``list_modes`` re-reads ``scenarios/extra/*.yaml``."""
    global _EXTRA_MODES_CACHE
    _EXTRA_MODES_CACHE = None


MODES: dict[str, ModeInfo] = {
    "program_management": ModeInfo(
        mode_id="program_management",
        label="程序管理设计",
        departments=["arch", "logic", "ui", "database", "benchmark", "xlab"],
        department_labels={
            "arch": "架构部",
            "logic": "逻辑部",
            "ui": "UI部",
            "database": "数据库部",
            "benchmark": "外部对标部",
            "xlab": "破局思考部",
        },
    ),
    "family_doctor": ModeInfo(
        mode_id="family_doctor",
        label="家庭医生助手",
        departments=["symptom", "nutrition", "drug_interactions", "psych", "security", "benchmark", "xlab"],
        department_labels={
            "symptom": "症状分析部",
            "nutrition": "营养部",
            "drug_interactions": "药物相互作用部",
            "psych": "心理辅导部",
            "security": "安全/合规部",
            "benchmark": "外部对标部",
            "xlab": "破局思考部",
        },
    ),
    "stock_trading": ModeInfo(
        mode_id="stock_trading",
        label="股票交易助手",
        departments=["macro_policy", "financial_reports", "technical_indicators", "smart_money", "security", "benchmark", "xlab"],
        department_labels={
            "macro_policy": "宏观政策部",
            "financial_reports": "财务报表部",
            "technical_indicators": "技术指标分析部",
            "smart_money": "主力资金监控部",
            "security": "安全/合规部",
            "benchmark": "外部对标部",
            "xlab": "破局思考部",
        },
    ),
    "travel_planning": ModeInfo(
        mode_id="travel_planning",
        label="旅行计划管理",
        departments=["visa", "flight_value", "local_safety", "culture_taboos", "security", "benchmark", "xlab"],
        department_labels={
            "visa": "签证部",
            "flight_value": "航空性价比部",
            "local_safety": "当地安全部",
            "culture_taboos": "文化禁忌部",
            "security": "安全/合规部",
            "benchmark": "外部对标部",
            "xlab": "破局思考部",
        },
    ),
}


def _apply_scenario_yaml(base: ModeInfo) -> ModeInfo:
    raw = load_scenario_dict(base.mode_id)
    if not raw:
        return base
    updates: dict[str, Any] = {"scenario_yaml": f"{base.mode_id}.yaml"}
    if raw.get("label"):
        updates["label"] = str(raw["label"]).strip()
    if raw.get("scenario_description") is not None:
        updates["scenario_description"] = str(raw.get("scenario_description") or "").strip() or None
    if raw.get("default_task_hint") is not None:
        updates["default_task_hint"] = str(raw.get("default_task_hint") or "").strip() or None
    dl = raw.get("department_labels")
    if isinstance(dl, dict):
        merged = dict(base.department_labels)
        for k, v in dl.items():
            ks, vs = str(k), str(v)
            if ks in base.departments:
                merged[ks] = vs
        updates["department_labels"] = merged
    gs = raw.get("gene_seeds")
    if isinstance(gs, dict) and gs:
        merged_seeds = dict(base.gene_seeds or {})
        for k, v in gs.items():
            ks = str(k)
            if ks in base.departments and v is not None:
                merged_seeds[ks] = str(v).strip()
        updates["gene_seeds"] = merged_seeds
    return base.model_copy(update=updates)


def resolve_mode(mode_id: str) -> tuple[ModeInfo, ModeRegistrySource]:
    """
    Resolve ``mode_id`` to a ``ModeInfo`` (with root ``scenarios/{id}.yaml`` overlay applied).

    Unknown ids fall back to built-in ``program_management`` (``registry=fallback``), matching ``get_mode`` semantics.
    """
    if mode_id in MODES:
        return _apply_scenario_yaml(MODES[mode_id]), "builtin"
    extra = _extra_modes().get(mode_id)
    if extra is not None:
        return _apply_scenario_yaml(extra), "extra"
    return _apply_scenario_yaml(MODES["program_management"]), "fallback"


def get_mode(mode_id: str) -> ModeInfo:
    return resolve_mode(mode_id)[0]


def list_modes() -> list[ModeInfo]:
    core = [_apply_scenario_yaml(m) for m in MODES.values()]
    extras = [_apply_scenario_yaml(m) for _, m in sorted(_extra_modes().items(), key=lambda kv: kv[0])]
    return core + extras


def list_extra_mode_ids() -> list[str]:
    """``mode_id`` values registered from ``backend/scenarios/extra/*.yaml`` (not in built-in ``MODES``)."""
    return sorted(_extra_modes().keys())

