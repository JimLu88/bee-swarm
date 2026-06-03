#!/usr/bin/env python3
"""一次性生成 15 个产业后台场景的对齐 team.yaml(从 modes.py 部门标签确定性模板化, 零 LLM)。

每个部门 head 的 persona_id = head_<mode>_<dept>, 与 seed 知识库绑定一致。
专科提示词从 modes.py 的 department_labels(中文名 + 专业描述)模板化生成。
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # backend/
import yaml  # noqa: E402
from app.modes import get_mode  # noqa: E402

TEAMS = pathlib.Path(__file__).resolve().parent.parent / "scenarios" / "teams"

INDUSTRIAL = [
    "industrialization", "machinery", "textiles", "chemical_industry", "metallurgy",
    "electronics_semiconductor", "energy_power", "construction_materials", "automotive",
    "food_processing", "pharma_biomfg", "modern_agriculture", "aerospace",
    "shipbuilding_marine", "mining_extraction",
]

MODELS = {
    "model_modeA": "openai/claude-opus-4-7",
    "model_modeB": "openai/deepseek-v4-flash",
    "model_modeC": "ollama_chat/qwen2.5:7b-instruct",
    "model_vendor": "Anthropic",
}


def _split_label(label: str) -> tuple[str, str]:
    """'机械设计 (结构/选型/CAD)' → ('机械设计', '结构/选型/CAD')"""
    label = (label or "").strip()
    for lb, rb in (("(", ")"), ("（", "）")):
        if lb in label and label.rstrip().endswith(rb):
            name = label[: label.index(lb)].strip()
            desc = label[label.index(lb) + 1 : -1].strip()
            return name or label, desc or name
    return label, label


def _head_prompt(name: str, desc: str, mode_label: str) -> str:
    return (
        f"你是{mode_label}领域「{name}」部门主管, 资深行业专家。\n"
        f"专科职责: {desc}。\n"
        "框架: 1.先讲清这个问题在本专业里的关键点与原理 2.给出上游材料/工艺/装备/标准等相关维度的判断 "
        "3.结合真实案例与常见误区 4.给可执行结论与下一步。\n"
        "风格: 专业、有依据、讲清来龙去脉, 面向'想理解世界 + 问技术问题'的用户。\n"
        "禁忌: 不编造数据/标准号; 不确定就说明边界。\n"
        "输出: 专业判断 → 关键维度 → 案例/误区 → 结论与下一步。"
    )


def _ceo_prompt(mode_label: str) -> str:
    return (
        f"你是{mode_label}领域总顾问, 统筹 6 位专科主管(覆盖上游材料→工艺制造→装备控制→质量标准→产业经济→前沿趋势)。\n"
        "角色: 把各专科判断综合成一个系统、可理解的回答。\n"
        "工作流: 1.先给一句总判断 2.按重要性综合各专科要点 3.指出产业链/趋势视角 4.给结论与延伸阅读方向。\n"
        "禁忌: 不编造具体数据/标准号; 不替用户下结论。\n"
        "输出: 总判断 → 综合要点 → 产业链/趋势视角 → 结论。"
    )


def build_team(mode_id: str) -> dict:
    mode = get_mode(mode_id)
    label = mode.label
    labels = mode.department_labels or {}
    team: dict = {
        "mode_id": mode_id,
        "generated_at": 1780000002,
        "generator_model": "industrial-template-v1",
        "ceo": {
            "persona_id": f"ceo_{mode_id}",
            "name": f"{label}总顾问",
            "title": f"{label}总顾问",
            "sub_specialty": f"{label}全产业链统筹 / 多专科协调",
            "ocean": {"O": 0.7, "C": 0.9, "E": 0.6, "A": 0.7, "N": 0.25},
            "personality": f"资深{label}行业统筹者, 系统思维, 重证据。",
            "diagnostic_style": "先看全局产业链, 再综合各专科要点。",
            **MODELS,
            "prompt": _ceo_prompt(label),
        },
        "departments": [],
    }
    for dept in mode.departments or []:
        name, desc = _split_label(labels.get(dept, dept))
        team["departments"].append({
            "dept_id": dept,
            "label": labels.get(dept, dept),
            "head": {
                "persona_id": f"head_{mode_id}_{dept}",
                "name": f"{name}主管",
                "title": f"{name}主管",
                "sub_specialty": desc,
                "ocean": {"O": 0.6, "C": 0.9, "E": 0.5, "A": 0.65, "N": 0.3},
                "personality": f"{name}领域资深专家, 严谨务实。",
                "diagnostic_style": f"围绕 {desc} 逐项分析。",
                **MODELS,
                "prompt": _head_prompt(name, desc, label),
            },
            "staff": [],
        })
    return team


def main() -> int:
    TEAMS.mkdir(parents=True, exist_ok=True)
    written = []
    for mid in INDUSTRIAL:
        team = build_team(mid)
        p = TEAMS / f"{mid}.yaml"
        p.write_text(yaml.safe_dump(team, allow_unicode=True, sort_keys=False, indent=2), encoding="utf-8")
        written.append(mid)
    print(f"[gen] 生成 {len(written)} 个产业 team.yaml: {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
