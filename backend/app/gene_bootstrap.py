"""
AI-generated department genes: 3+1 微型团队（成员 A/B/C + Lead），由总 CEO 人设分配。

Uses the same LiteLLM routing as decision runs (per-dept model / profiles).
"""

from __future__ import annotations

import re
from typing import Any

from .gene_defaults import build_initial_gene_prompt
from .gene_store import GeneStore
from .gene_team import (
    SLOTS,
    merge_team_to_prompt,
    normalize_team,
    parse_role_json,
    parse_team_json,
    team_from_record,
    team_has_content,
)
from .llm.litellm_client import litellm_client
from .llm.router import router as llm_router
from .modes import get_mode
from .runtime_paths import backend_data_dir
from .settings_llm_rag import llm_rag_settings

_CEO_TEAM_SYSTEM = (
    "你是企业协同决策系统的总负责人（CEO），负责为每个业务部门的「3+1 微型团队」分配互补职能并撰写人设。"
    "只输出一个 JSON 对象，不要 Markdown 代码围栏，不要任何其他说明文字。"
    '结构严格为：{"member_a":{"role_title":"string","persona_prompt":"string"},'
    '"member_b":{"role_title":"string","persona_prompt":"string"},'
    '"member_c":{"role_title":"string","persona_prompt":"string"},'
    '"lead":{"role_title":"string","persona_prompt":"string"}} 。'
    "member_a/b/c：三条专业职能视角，职能名称用简短中文 role_title；persona_prompt 为中文系统提示片段，"
    "说明该视角下的分析方式、边界、输出习惯，并须与部门场景一致。"
    "lead：部门主管，主持内部辩论，在 persona_prompt 中须明确要求输出「共识」与「无法调和的冲突」的归纳方式，"
    "并仍要求 confidence_score 与 dissent_intensity。"
    "每条 persona_prompt 建议 200～900 字；总 JSON 字符数尽量不超过 12000。"
)

_REGEN_ROLE_SYSTEM = (
    "你是 CEO，正在为部门「3+1 微型团队」中的某一席位重新分配职能并撰写人设。"
    "只输出一个 JSON 对象，不要 Markdown 围栏，不要其他文字。"
    '格式严格为：{"role_title":"string","persona_prompt":"string"} 。'
    "persona_prompt 为中文系统提示片段；须与当前部门及其他席位协调、可执行。"
)


def _strip_fences(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^```[\w]*\s*", "", t)
    t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def _dept_context(mode_id: str, dept: str) -> str:
    mode = get_mode(mode_id)
    label = (mode.department_labels or {}).get(dept, dept)
    seed = (mode.gene_seeds or {}).get(dept, "")
    seed = str(seed).strip()
    return (
        f"业务类型：{mode.label}（{mode.mode_id}）\n"
        f"场景说明：{(mode.scenario_description or '').strip() or '—'}\n"
        f"部门显示名：{label}\n"
        f"部门代码：{dept}\n"
        f"场景模板补充（gene_seeds）：{seed or '—'}\n"
        f"参考任务示例：{(mode.default_task_hint or '').strip() or '—'}\n"
        f"全局默认模型（参考）：{(llm_rag_settings.litellm_default_model or 'gpt-4o-mini')}\n"
    )


async def generate_team_for_dept(*, mode_id: str, dept: str) -> dict[str, dict[str, str]]:
    """CEO 生成完整 3+1 团队 JSON。"""
    user = _dept_context(mode_id, dept) + "\n请为上述部门生成完整的 3+1 微型团队 JSON。"

    choice = llm_router.pick_for_dept(dept)
    if choice.provider != "litellm":
        return _fallback_team(mode_id, dept)

    fb = llm_router.fallbacks()
    resp = await litellm_client.complete(
        model=choice.model,
        prompt=user,
        fallbacks=[m for m in fb if m != choice.model],
        system=_CEO_TEAM_SYSTEM,
    )
    text = _strip_fences((resp.text or "").strip())
    team = parse_team_json(text)
    if team is None or not team_has_content(team):
        return _fallback_team(mode_id, dept)
    return team


def _fallback_team(mode_id: str, dept: str) -> dict[str, dict[str, str]]:
    base = build_initial_gene_prompt(mode_id, dept)
    t = empty_team()
    t["member_a"] = {"role_title": "专业视角一", "persona_prompt": f"{base}\n\n你代表成员 A：从可行性优先角度审视方案。"}
    t["member_b"] = {"role_title": "专业视角二", "persona_prompt": f"{base}\n\n你代表成员 B：从风险与合规角度审视方案。"}
    t["member_c"] = {"role_title": "专业视角三", "persona_prompt": f"{base}\n\n你代表成员 C：从用户体验与落地成本角度审视方案。"}
    t["lead"] = {
        "role_title": "部门主管",
        "persona_prompt": (
            f"{base}\n\n你是部门主管 (Lead)：主持 A/B/C 内部辩论，在结论中分别写出「共识」与「无法调和的冲突」，"
            "并给出 confidence_score 与 dissent_intensity。"
        ),
    }
    return t


async def regenerate_team_slot(
    *,
    mode_id: str,
    dept: str,
    slot: str,
    preference: str,
    current_team: dict[str, dict[str, str]] | None,
) -> dict[str, str]:
    """CEO 为单席位重新生成职能 + 人设。"""
    if slot not in SLOTS:
        raise ValueError("invalid_slot")
    team = normalize_team(current_team or {})
    ctx = _dept_context(mode_id, dept)
    pref = (preference or "").strip()
    pref_line = f"用户对本轮职能的倾向说明：{pref}" if pref else "用户未指定倾向：请自由生成与该部门协调的新职能与人设。"
    import json as _json

    user = (
        f"{ctx}\n当前 3+1 团队（JSON，需保持与除「{slot}」外席位协调）：\n"
        f"{_json.dumps(team, ensure_ascii=False)}\n\n"
        f"请仅重新生成席位「{slot}」的 role_title 与 persona_prompt。\n{pref_line}"
    )

    choice = llm_router.pick_for_dept(dept)
    if choice.provider != "litellm":
        fb_team = _fallback_team(mode_id, dept)
        return fb_team.get(slot) or {"role_title": "", "persona_prompt": ""}

    model_fb = llm_router.fallbacks()
    resp = await litellm_client.complete(
        model=choice.model,
        prompt=user,
        fallbacks=[m for m in model_fb if m != choice.model],
        system=_REGEN_ROLE_SYSTEM,
    )
    text = _strip_fences((resp.text or "").strip())
    role = parse_role_json(text)
    if role is None:
        return team.get(slot) or {"role_title": "（生成失败）", "persona_prompt": build_initial_gene_prompt(mode_id, dept)}
    return role


async def generate_prompt_for_dept(*, mode_id: str, dept: str) -> str:
    """向后兼容：返回合并后的单段基因文本。"""
    team = await generate_team_for_dept(mode_id=mode_id, dept=dept)
    return merge_team_to_prompt(mode_id, dept, team)


async def generate_all_dept_prompts(mode_id: str, *, overwrite: bool = True) -> dict[str, Any]:
    """
    CEO 为每个部门生成 3+1 团队并落盘（含 team + 合并 prompt）。
    ``overwrite`` 为 False 时跳过已有非空 team 或已有非空 prompt 的部门。
    """
    mode = get_mode(mode_id)
    gs = GeneStore(backend_data_dir())
    results: dict[str, Any] = {}

    for dept in mode.departments:
        if not overwrite:
            existing = gs.get_active(mode_id=mode_id, dept=dept)
            if existing:
                if team_has_content(team_from_record(existing)):
                    results[dept] = {"ok": True, "skipped": True, "reason": "already_has_team"}
                    continue
                cur = str((existing or {}).get("prompt") or "").strip()
                if cur:
                    results[dept] = {"ok": True, "skipped": True, "reason": "already_has_prompt"}
                    continue

        try:
            team = await generate_team_for_dept(mode_id=mode_id, dept=dept)
            merged = merge_team_to_prompt(mode_id, dept, team)
            gs.set_active(mode_id=mode_id, dept=dept, team=team, prompt=merged)
            results[dept] = {"ok": True, "skipped": False, "slots": list(SLOTS)}
        except Exception as e:
            fb = _fallback_team(mode_id, dept)
            merged = merge_team_to_prompt(mode_id, dept, fb)
            gs.set_active(mode_id=mode_id, dept=dept, team=fb, prompt=merged)
            results[dept] = {"ok": False, "error": repr(e), "used_fallback": True}

    return {
        "ok": True,
        "mode_id": mode_id,
        "mode_label": mode.label,
        "litellm_default_model": llm_rag_settings.litellm_default_model,
        "results": results,
        "team_schema": "3+1",
    }
