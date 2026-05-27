from __future__ import annotations

from pathlib import Path
from typing import Any

_SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"


def scenarios_dir() -> Path:
    return _SCENARIOS_DIR


def list_scenario_yaml_basenames() -> list[str]:
    if not _SCENARIOS_DIR.exists():
        return []
    return sorted(p.name for p in _SCENARIOS_DIR.glob("*.yaml"))


def load_scenario_dict(mode_id: str) -> dict[str, Any] | None:
    """
    Load ``backend/scenarios/{mode_id}.yaml`` if present.
    Expected keys (all optional): label, scenario_description, default_task_hint,
    department_labels, gene_seeds.
    """
    p = _SCENARIOS_DIR / f"{mode_id}.yaml"
    if not p.exists():
        return None
    try:
        import yaml  # type: ignore
    except Exception:
        return None
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    file_mode = str(raw.get("mode_id") or mode_id).strip()
    if file_mode and file_mode != mode_id:
        return None
    return raw
