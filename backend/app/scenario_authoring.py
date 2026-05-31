from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, get_args

from .models import DeptName

ScenarioKind = Literal["root_overlay", "extra_mode"]


@dataclass(frozen=True)
class ScenarioValidation:
    ok: bool
    kind: ScenarioKind
    errors: list[str]
    warnings: list[str]
    normalized: dict[str, Any]


## v6-A: DeptName 改 str 后白名单从 Literal get_args 变成动态从 modes 列举.
def _allowed_depts() -> frozenset[str]:
    from .catalog import list_dept_names
    return frozenset(list_dept_names())


_ALLOWED_DEPTS: frozenset[str] = _allowed_depts()
_ROOT_ALLOWED_KEYS: frozenset[str] = frozenset(
    [
        "mode_id",
        "label",
        "scenario_description",
        "default_task_hint",
        "department_labels",
        "gene_seeds",
    ]
)
_EXTRA_ALLOWED_KEYS: frozenset[str] = frozenset(list(_ROOT_ALLOWED_KEYS) + ["departments"])


def _as_dict(raw: Any) -> dict[str, Any] | None:
    return raw if isinstance(raw, dict) else None


def validate_root_overlay(*, yaml_dict: dict[str, Any], mode_id: str) -> ScenarioValidation:
    errors: list[str] = []
    warnings: list[str] = []
    norm: dict[str, Any] = {"mode_id": mode_id}

    for k in yaml_dict.keys():
        if str(k) not in _ROOT_ALLOWED_KEYS:
            warnings.append(f"unknown_key:{k}")

    mid = str(yaml_dict.get("mode_id") or mode_id).strip()
    if mid and mid != mode_id:
        errors.append(f"mode_id_mismatch file={mid} expected={mode_id}")

    if "label" in yaml_dict and yaml_dict.get("label") is not None:
        norm["label"] = str(yaml_dict.get("label") or "").strip()
    if "scenario_description" in yaml_dict and yaml_dict.get("scenario_description") is not None:
        norm["scenario_description"] = str(yaml_dict.get("scenario_description") or "").strip()
    if "default_task_hint" in yaml_dict and yaml_dict.get("default_task_hint") is not None:
        norm["default_task_hint"] = str(yaml_dict.get("default_task_hint") or "").strip()

    dl = _as_dict(yaml_dict.get("department_labels"))
    if dl is not None:
        norm["department_labels"] = {str(k): str(v) for k, v in dl.items()}
    elif "department_labels" in yaml_dict:
        errors.append("department_labels_not_a_map")

    gs = _as_dict(yaml_dict.get("gene_seeds"))
    if gs is not None:
        norm["gene_seeds"] = {str(k): str(v) for k, v in gs.items() if v is not None}
    elif "gene_seeds" in yaml_dict:
        errors.append("gene_seeds_not_a_map")

    return ScenarioValidation(ok=len(errors) == 0, kind="root_overlay", errors=errors, warnings=warnings, normalized=norm)


def validate_extra_mode(*, yaml_dict: dict[str, Any], builtin_mode_ids: frozenset[str]) -> ScenarioValidation:
    errors: list[str] = []
    warnings: list[str] = []
    norm: dict[str, Any] = {}

    for k in yaml_dict.keys():
        if str(k) not in _EXTRA_ALLOWED_KEYS:
            warnings.append(f"unknown_key:{k}")

    mid = str(yaml_dict.get("mode_id") or "").strip()
    if not mid:
        errors.append("missing_mode_id")
    elif mid in builtin_mode_ids:
        errors.append(f"mode_id_collides_with_builtin:{mid}")
    norm["mode_id"] = mid

    label = str(yaml_dict.get("label") or mid).strip()
    norm["label"] = label

    depts_raw = yaml_dict.get("departments")
    if not isinstance(depts_raw, list) or not depts_raw:
        errors.append("departments_must_be_nonempty_list")
        norm["departments"] = []
    else:
        depts: list[str] = []
        for d in depts_raw:
            s = str(d).strip()
            if s not in _ALLOWED_DEPTS:
                warnings.append(f"unknown_dept:{s}")
                continue
            if s not in depts:
                depts.append(s)
        if not depts:
            errors.append("departments_no_known_values")
        norm["departments"] = depts

    root_like = validate_root_overlay(yaml_dict=yaml_dict, mode_id=mid or "MISSING")
    # merge normalized root fields, but keep extra-mode depts.
    for k, v in root_like.normalized.items():
        if k == "mode_id":
            continue
        norm[k] = v
    # carry root warnings (except key warnings already computed)
    for w in root_like.warnings:
        if not w.startswith("unknown_key:"):
            warnings.append(w)
    for e in root_like.errors:
        if not e.startswith("mode_id_mismatch"):
            errors.append(e)

    return ScenarioValidation(ok=len(errors) == 0, kind="extra_mode", errors=errors, warnings=warnings, normalized=norm)


def scaffold_extra_mode_yaml(*, mode_id: str) -> str:
    safe = (mode_id or "").strip() or "your_mode_id"
    return (
        "# Phase 7 scaffold: create a new YAML-defined mode.\n"
        "# Save to: backend/scenarios/extra/<mode_id>.yaml\n"
        f"mode_id: {safe}\n"
        f"label: {safe}\n"
        "departments:\n"
        "  - security\n"
        "  - benchmark\n"
        "  - xlab\n"
        "department_labels:\n"
        "  security: 安全与合规\n"
        "  benchmark: 外部对标\n"
        "  xlab: 破局思考\n"
        "scenario_description: |\n"
        "  （填写场景说明）\n"
        "default_task_hint: \"（填写默认任务提示）\"\n"
        "gene_seeds:\n"
        "  security: \"（该部门的基因种子，可选）\"\n"
    )

