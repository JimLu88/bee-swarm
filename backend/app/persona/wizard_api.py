"""v7 W4 自定义场景向导 — 分步问答 → 便宜 LLM 草拟部门 → 落地为新场景.

挂载 prefix: /api/wizard
POST /api/wizard/draft   - body {domain, examples, angles_hint} → 草拟 {mode_id,label,departments[{id,label}],ceo_title,scenario_description}
POST /api/wizard/create  - body {mode_id,label,scenario_description,departments[{id,label}]} → 注册 extra mode + 生成 team.yaml
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Body, HTTPException

router = APIRouter(prefix="/api/wizard", tags=["wizard"])

_EXTRA_DIR = Path(__file__).resolve().parent.parent.parent / "scenarios" / "extra"


def _slug(s: str) -> str:
    """中文/任意 → 安全 mode_id. 全中文时回退 custom_<时间戳尾>."""
    s = (s or "").strip().lower()
    safe = re.sub(r"[^a-z0-9_]+", "_", s).strip("_")
    if not safe or not re.search(r"[a-z]", safe):
        safe = f"custom_{int(time.time()) % 100000}"
    return safe[:48]


@router.post("/draft")
async def draft(body: dict = Body(...)) -> dict[str, Any]:
    """用便宜 LLM 把用户的领域描述 → 草拟一套部门 (id+label) + CEO 头衔."""
    domain = str(body.get("domain") or "").strip()
    examples = str(body.get("examples") or "").strip()
    angles = str(body.get("angles_hint") or "").strip()
    if not domain:
        raise HTTPException(status_code=422, detail="domain_required")

    from ..llm.litellm_client import litellm_client
    from ..llm.router import router as llm_router
    from ..llm.parsing import _extract_json
    from ..decision_engine import _PREFLIGHT_MODEL

    sys_prompt = (
        "你是组织设计专家. 用户要为某个咨询领域组建一支 AI 专家顾问团.\n"
        "请设计 4-7 个真实'专科/角色'部门 (不是工序步骤, 是有独立判断力的专家角色).\n"
        "只输出 JSON, 不要解释. 格式:\n"
        "{\n"
        '  "label": "场景中文名(8字内)",\n'
        '  "ceo_title": "总顾问头衔",\n'
        '  "scenario_description": "一句话场景说明",\n'
        '  "departments": [{"id":"英文蛇形id","label":"中文角色名(职责简述)"}]\n'
        "}\n"
        "id 必须英文蛇形 (如 senior_lawyer); label 要含括号职责, 对标该领域世界一流团队分工."
    )
    user_prompt = f"领域: {domain}\n典型问题举例: {examples or '(未提供)'}\n希望分析角度: {angles or '(由你判断)'}"

    obj: dict[str, Any] = {}
    err = ""
    try:
        resp = await litellm_client.complete(
            model=_PREFLIGHT_MODEL, fallbacks=llm_router.fallbacks(),
            system=sys_prompt, prompt=user_prompt,
        )
        obj = _extract_json(resp.text or "") or {}
    except Exception as e:
        err = repr(e)

    label = str(obj.get("label") or domain[:8] or "自定义场景").strip()
    ceo_title = str(obj.get("ceo_title") or f"{label}总顾问").strip()
    desc = str(obj.get("scenario_description") or f"{domain} 相关咨询").strip()
    raw_depts = obj.get("departments")
    depts: list[dict[str, str]] = []
    seen: set[str] = set()
    if isinstance(raw_depts, list):
        for d in raw_depts:
            if not isinstance(d, dict):
                continue
            did = _slug(str(d.get("id") or ""))
            dlabel = str(d.get("label") or did).strip()
            if did and did not in seen:
                seen.add(did)
                depts.append({"id": did, "label": dlabel})
    if not depts:
        depts = [
            {"id": "domain_expert", "label": "领域专家 (核心专业判断)"},
            {"id": "risk_advisor", "label": "风险顾问 (合规/陷阱/红线)"},
            {"id": "cost_analyst", "label": "成本分析师 (预算/性价比/取舍)"},
            {"id": "execution_planner", "label": "执行规划师 (步骤/资源/时间表)"},
            {"id": "user_advocate", "label": "用户代言人 (体验/可行性/接受度)"},
            {"id": "researcher", "label": "调研员 (信息搜集/对标/趋势)"},
        ]

    return {
        "mode_id": _slug(label) + "_" + str(int(time.time()) % 10000),
        "label": label, "ceo_title": ceo_title,
        "scenario_description": desc,
        "departments": depts[:7],
        "llm_error": err,
    }


@router.post("/create")
async def create(body: dict = Body(...)) -> dict[str, Any]:
    """落地: 写 extra mode yaml → reload → generate_full_team → save team.yaml."""
    mode_id = _slug(str(body.get("mode_id") or ""))
    label = str(body.get("label") or "").strip()
    desc = str(body.get("scenario_description") or "").strip()
    raw_depts = body.get("departments") or []
    if not mode_id or not label or not isinstance(raw_depts, list) or not raw_depts:
        raise HTTPException(status_code=422, detail="mode_id/label/departments_required")

    from ..modes import MODES
    if mode_id in MODES:
        raise HTTPException(status_code=409, detail=f"mode_id {mode_id} 与内置场景冲突, 换个名")

    departments: list[str] = []
    dept_labels: dict[str, str] = {}
    for d in raw_depts:
        if not isinstance(d, dict):
            continue
        did = _slug(str(d.get("id") or ""))
        if did and did not in dept_labels:
            departments.append(did)
            dept_labels[did] = str(d.get("label") or did).strip()
    if not departments:
        raise HTTPException(status_code=422, detail="no_valid_departments")

    _EXTRA_DIR.mkdir(parents=True, exist_ok=True)
    extra_yaml = {
        "mode_id": mode_id, "label": label,
        "scenario_description": desc or f"{label} 自定义场景",
        "departments": departments,
        "department_labels": dept_labels,
    }
    (_EXTRA_DIR / f"{mode_id}.yaml").write_text(
        yaml.safe_dump(extra_yaml, allow_unicode=True, sort_keys=False), encoding="utf-8")

    from ..modes import reload_mode_yaml_cache
    reload_mode_yaml_cache()

    from . import team_generator, team_store
    gen_error = ""
    try:
        team = await team_generator.generate_full_team(mode_id)
        team_store.save_team(mode_id, team)
    except Exception as e:
        gen_error = repr(e)

    return {
        "ok": True, "mode_id": mode_id, "label": label,
        "departments": departments, "team_generated": not gen_error,
        "gen_error": gen_error,
    }
