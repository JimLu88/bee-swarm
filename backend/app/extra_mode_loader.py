from __future__ import annotations

from pathlib import Path
from typing import Any, get_args

from .models import DeptName, ModeInfo

_EXTRA_DIR = Path(__file__).resolve().parent.parent / "scenarios" / "extra"
_ALLOWED: frozenset[str] = frozenset(get_args(DeptName))


def extra_modes_dir() -> Path:
    return _EXTRA_DIR


def list_extra_mode_yaml_basenames() -> list[str]:
    if not _EXTRA_DIR.exists():
        return []
    return sorted(p.name for p in _EXTRA_DIR.glob("*.yaml"))


def _coerce_str_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        out[str(k)] = str(v)
    return out


def _parse_mode_file(path: Path, *, skip_mode_ids: frozenset[str]) -> ModeInfo | None:
    try:
        import yaml  # type: ignore
    except Exception:
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    mid = str(raw.get("mode_id") or "").strip()
    if not mid or mid in skip_mode_ids:
        return None
    label = str(raw.get("label") or mid).strip() or mid
    depts_raw = raw.get("departments")
    if not isinstance(depts_raw, list) or not depts_raw:
        return None
    depts: list[DeptName] = []
    for d in depts_raw:
        s = str(d).strip()
        if s in _ALLOWED:
            depts.append(s)  # type: ignore[assignment]
    if not depts:
        return None

    labels = _coerce_str_map(raw.get("department_labels"))
    merged_labels: dict[str, str] = {}
    for d in depts:
        merged_labels[d] = labels.get(d, d)

    sd = raw.get("scenario_description")
    scenario_description = str(sd).strip() if sd is not None and str(sd).strip() else None
    dth = raw.get("default_task_hint")
    default_task_hint = str(dth).strip() if dth is not None and str(dth).strip() else None

    gene_seeds: dict[str, str] = {}
    gs = raw.get("gene_seeds")
    if isinstance(gs, dict):
        for k, v in gs.items():
            ks = str(k)
            if ks in depts and v is not None:
                gene_seeds[ks] = str(v).strip()

    return ModeInfo(
        mode_id=mid,
        label=label,
        departments=depts,
        department_labels=merged_labels,
        scenario_description=scenario_description,
        default_task_hint=default_task_hint,
        gene_seeds=gene_seeds or {},
        scenario_yaml=None,
    )


def load_extra_modes(*, builtin_mode_ids: frozenset[str]) -> dict[str, ModeInfo]:
    """
    Load ``backend/scenarios/extra/*.yaml`` as additional modes.
    Files must declare ``mode_id`` not colliding with builtins, and ``departments``
    must be a non-empty list of known ``DeptName`` values.
    """
    if not _EXTRA_DIR.exists():
        return {}
    out: dict[str, ModeInfo] = {}
    for path in sorted(_EXTRA_DIR.glob("*.yaml")):
        m = _parse_mode_file(path, skip_mode_ids=builtin_mode_ids)
        if m is None:
            continue
        if m.mode_id in out:
            continue
        out[m.mode_id] = m
    return out
