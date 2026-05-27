"""
3+1 微型团队基因：成员 A/B/C + 部门主管 Lead；合并为决策引擎使用的单段 system 文本。
"""

from __future__ import annotations

import json
import re
from typing import Any

from .modes import get_mode

SLOTS: tuple[str, ...] = ("member_a", "member_b", "member_c", "lead")

SLOT_LABELS: dict[str, str] = {
    "member_a": "成员 A",
    "member_b": "成员 B",
    "member_c": "成员 C",
    "lead": "部门主管 (Lead)",
}


def empty_role() -> dict[str, str]:
    return {"role_title": "", "persona_prompt": ""}


def empty_team() -> dict[str, dict[str, str]]:
    return {s: empty_role() for s in SLOTS}


def normalize_role(r: Any) -> dict[str, str]:
    if isinstance(r, dict):
        return {
            "role_title": str(r.get("role_title") or "").strip()[:200],
            "persona_prompt": str(r.get("persona_prompt") or "").strip()[:12_000],
        }
    return empty_role()


def normalize_team(raw: Any) -> dict[str, dict[str, str]]:
    out = empty_team()
    if not isinstance(raw, dict):
        return out
    for s in SLOTS:
        out[s] = normalize_role(raw.get(s))
    return out


def team_from_record(rec: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    if not rec:
        return empty_team()
    t = rec.get("team")
    if isinstance(t, dict):
        return normalize_team(t)
    return empty_team()


def team_has_content(team: dict[str, dict[str, str]]) -> bool:
    return any((team[s]["persona_prompt"] or team[s]["role_title"]) for s in SLOTS)


def merge_team_to_prompt(mode_id: str, dept: str, team: dict[str, dict[str, str]]) -> str:
    mode = get_mode(mode_id)
    label = (mode.department_labels or {}).get(dept, dept)
    parts: list[str] = [
        f"【{label}（{dept}）· 3+1 微型团队】",
        "本部门由成员 A、成员 B、成员 C 与部门主管 (Lead) 协同完成评审。",
        "成员 A/B/C 为总 CEO 分配的三条互补职能视角；Lead 主持内部辩论，在输出中须明确「共识」与「无法调和的冲突」（若有），",
        "并仍给出 confidence_score 与 dissent_intensity（0～1 小数）。",
        "",
    ]
    for s in SLOTS:
        r = team[s]
        title = r["role_title"] or SLOT_LABELS[s]
        parts.append(f"—— {SLOT_LABELS[s]} · {title} ——")
        parts.append(r["persona_prompt"] or "（人设待补充）")
        parts.append("")
    return "\n".join(parts).strip()


def merged_gene_prompt(gene: dict[str, Any] | None, mode_id: str, dept: str, fallback: str) -> str:
    if not gene:
        return fallback
    team = team_from_record(gene)
    if team_has_content(team):
        return merge_team_to_prompt(mode_id, dept, team)
    p = str(gene.get("prompt") or "").strip()
    return p or fallback


def strip_json_fences(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^```[\w]*\s*", "", t)
    t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def parse_team_json(text: str) -> dict[str, dict[str, str]] | None:
    raw = strip_json_fences(text)
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    team = normalize_team(obj)
    if not team_has_content(team):
        return None
    return team


def parse_role_json(text: str) -> dict[str, str] | None:
    raw = strip_json_fences(text)
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    r = normalize_role(obj)
    if not r["persona_prompt"] and not r["role_title"]:
        return None
    return r
