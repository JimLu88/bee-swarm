"""v6-A team.yaml 读写 + 三级重生历史快照.

存储路径:
  backend/scenarios/teams/<mode_id>.yaml                  # 当前活跃
  backend/scenarios/teams/_history/<mode_id>-<ts>.yaml    # 归档 (一键回滚)
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent.parent.parent
TEAMS_DIR = _ROOT / "scenarios" / "teams"
HISTORY_DIR = TEAMS_DIR / "_history"
TEAMS_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _team_path(mode_id: str) -> Path:
    safe = "".join(c for c in mode_id if c.isalnum() or c in ("_", "-"))[:64] or "default"
    return TEAMS_DIR / f"{safe}.yaml"


def _archive_current(mode_id: str) -> str | None:
    p = _team_path(mode_id)
    if not p.exists():
        return None
    ts = int(time.time())
    archive = HISTORY_DIR / f"{p.stem}-{ts}.yaml"
    archive.write_bytes(p.read_bytes())
    return archive.name


def load_team(mode_id: str) -> dict[str, Any] | None:
    p = _team_path(mode_id)
    if not p.exists():
        return None
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def save_team(mode_id: str, team: dict[str, Any]) -> dict[str, Any]:
    archived = _archive_current(mode_id)
    team = dict(team)
    team["mode_id"] = mode_id
    team.setdefault("generated_at", int(time.time()))
    p = _team_path(mode_id)
    p.write_text(
        yaml.safe_dump(team, allow_unicode=True, sort_keys=False, indent=2),
        encoding="utf-8",
    )
    return {"saved": str(p), "archived_previous": archived}


def regen_department(mode_id: str, dept_id: str, new_dept: dict[str, Any]) -> dict[str, Any]:
    team = load_team(mode_id)
    if not team:
        raise KeyError(f"team for {mode_id} not found")
    depts = team.get("departments") or []
    found = False
    for i, d in enumerate(depts):
        if str(d.get("dept_id")) == dept_id:
            depts[i] = {**new_dept, "dept_id": dept_id, "label": d.get("label", dept_id)}
            found = True
            break
    if not found:
        raise KeyError(f"dept_id {dept_id} not in team {mode_id}")
    team["departments"] = depts
    return save_team(mode_id, team)


def regen_persona(
    mode_id: str, dept_id: str, persona_id: str, new_persona: dict[str, Any]
) -> dict[str, Any]:
    team = load_team(mode_id)
    if not team:
        raise KeyError(f"team for {mode_id} not found")
    for d in team.get("departments") or []:
        if str(d.get("dept_id")) != dept_id:
            continue
        head = d.get("head") or {}
        if str(head.get("persona_id")) == persona_id:
            d["head"] = {**new_persona, "persona_id": persona_id}
            return save_team(mode_id, team)
        staff = d.get("staff") or []
        for i, s in enumerate(staff):
            if str(s.get("persona_id")) == persona_id:
                staff[i] = {**new_persona, "persona_id": persona_id}
                d["staff"] = staff
                return save_team(mode_id, team)
        raise KeyError(f"persona_id {persona_id} not found in dept {dept_id}")
    raise KeyError(f"dept_id {dept_id} not in team {mode_id}")


def put_persona_prompt(
    mode_id: str, dept_id: str, persona_id: str, prompt: str
) -> dict[str, Any]:
    team = load_team(mode_id)
    if not team:
        raise KeyError(f"team for {mode_id} not found")
    for d in team.get("departments") or []:
        if str(d.get("dept_id")) != dept_id:
            continue
        head = d.get("head") or {}
        if str(head.get("persona_id")) == persona_id:
            head["prompt"] = prompt
            d["head"] = head
            return save_team(mode_id, team)
        for s in d.get("staff") or []:
            if str(s.get("persona_id")) == persona_id:
                s["prompt"] = prompt
                return save_team(mode_id, team)
    raise KeyError(f"persona {persona_id} in dept {dept_id} not found")


def list_history(mode_id: str, limit: int = 30) -> list[dict[str, Any]]:
    safe = _team_path(mode_id).stem
    files = sorted(HISTORY_DIR.glob(f"{safe}-*.yaml"), reverse=True)[:limit]
    out: list[dict[str, Any]] = []
    for f in files:
        try:
            ts = int(f.stem.rsplit("-", 1)[-1])
        except ValueError:
            ts = 0
        out.append({"file": f.name, "ts": ts})
    return out


def rollback(mode_id: str, history_file: str) -> dict[str, Any]:
    target = HISTORY_DIR / history_file
    if not target.exists() or target.parent != HISTORY_DIR:
        raise KeyError(f"history file not found: {history_file}")
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"history file {history_file} is not a valid YAML object")
    return save_team(mode_id, data)
