"""v6-A 团队管理 HTTP 端点.

挂载 prefix: /api/team

POST /api/team/generate/{mode_id}                        - 首次生成整个团队 (Opus, ~¥3, 60-90s)
POST /api/team/regen-dept/{mode_id}/{dept_id}            - 重生某部门 head+staff (~¥0.5)
POST /api/team/regen-persona/{mode_id}/{dept_id}/{pid}   - 重生单个人设 (~¥0.2)
PUT  /api/team/prompt/{mode_id}/{dept_id}/{pid}          - 手编 system prompt
GET  /api/team/{mode_id}                                 - 读当前团队
GET  /api/team/{mode_id}/history                         - 列归档版本
POST /api/team/{mode_id}/rollback                        - body {file:"..."} 回滚
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from . import team_generator, team_store

router = APIRouter(prefix="/api/team", tags=["team"])


@router.post("/generate/{mode_id}")
async def generate(mode_id: str) -> dict[str, Any]:
    try:
        team = await team_generator.generate_full_team(mode_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"generate_failed: {e}")
    saved = team_store.save_team(mode_id, team)
    return {"mode_id": mode_id, "team": team, "saved": saved}


@router.post("/regen-dept/{mode_id}/{dept_id}")
async def regen_dept(mode_id: str, dept_id: str) -> dict[str, Any]:
    try:
        new_dept = await team_generator.regenerate_department(mode_id, dept_id)
        saved = team_store.regen_department(mode_id, dept_id, new_dept)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"regen_failed: {e}")
    return {"mode_id": mode_id, "dept_id": dept_id, "new_dept": new_dept, "saved": saved}


@router.post("/regen-persona/{mode_id}/{dept_id}/{persona_id}")
async def regen_persona(mode_id: str, dept_id: str, persona_id: str) -> dict[str, Any]:
    try:
        new_persona = await team_generator.regenerate_persona(mode_id, dept_id, persona_id)
        saved = team_store.regen_persona(mode_id, dept_id, persona_id, new_persona)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"regen_failed: {e}")
    return {
        "mode_id": mode_id, "dept_id": dept_id, "persona_id": persona_id,
        "new_persona": new_persona, "saved": saved,
    }


@router.put("/prompt/{mode_id}/{dept_id}/{persona_id}")
def put_prompt(mode_id: str, dept_id: str, persona_id: str,
               body: dict = Body(...)) -> dict[str, Any]:
    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="prompt_required")
    try:
        saved = team_store.put_persona_prompt(mode_id, dept_id, persona_id, prompt)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"mode_id": mode_id, "dept_id": dept_id, "persona_id": persona_id, "saved": saved}


@router.get("/{mode_id}")
def get_team(mode_id: str) -> dict[str, Any]:
    team = team_store.load_team(mode_id)
    if team is None:
        return {"mode_id": mode_id, "status": "not_generated"}
    # v6-U 实时 patch + 重算 missing_api_keys
    # —— 即使是旧 yaml (修改前生成的) 也能立即用新逻辑显示, 不必重生
    try:
        team_generator._patch_team_to_user_gateway(team)
        team["missing_api_keys"] = team_generator._missing_keys_warning(team)
    except Exception:
        pass
    return {"mode_id": mode_id, "status": "ready", "team": team}


@router.get("/{mode_id}/history")
def list_history(mode_id: str, limit: int = 30) -> dict[str, Any]:
    return {"mode_id": mode_id, "items": team_store.list_history(mode_id, limit)}


@router.get("/{mode_id}/persona-stats")
def persona_stats(mode_id: str, last_n: int = 5) -> dict[str, Any]:
    """v6-S8 主管近况: 每个 dept 最近 N 次决策的自信度 + 评分."""
    from ..decision_memory import DecisionMemory
    from ..runtime_paths import backend_data_dir

    try:
        mem = DecisionMemory(backend_data_dir())
        rows = mem.read_all_summaries(mode_id=mode_id)
    except Exception:
        rows = []

    stats: dict[str, dict[str, Any]] = {}
    for row in rows:
        ts = row.get("created_at") or ""
        for r in (row.get("dept_reports") or []):
            dept = str(r.get("dept") or "").strip()
            if not dept:
                continue
            s = stats.setdefault(dept, {
                "recent_confidence": [], "recent_dissent": [],
                "decisions_count": 0, "last_seen": "",
            })
            s["decisions_count"] += 1
            s["last_seen"] = ts or s["last_seen"]
            try:
                s["recent_confidence"].append(float(r.get("confidence_score") or 0))
                s["recent_dissent"].append(float(r.get("dissent_intensity") or 0))
            except Exception:
                pass

    last_n = max(1, min(last_n, 20))
    for s in stats.values():
        s["recent_confidence"] = s["recent_confidence"][-last_n:]
        s["recent_dissent"] = s["recent_dissent"][-last_n:]

    team_generated_at = None
    try:
        team = team_store.load_team(mode_id)
        if team:
            team_generated_at = team.get("generated_at")
    except Exception:
        pass

    return {
        "mode_id": mode_id,
        "stats": stats,
        "team_generated_at": team_generated_at,
    }


@router.post("/{mode_id}/rollback")
def rollback(mode_id: str, body: dict = Body(...)) -> dict[str, Any]:
    history_file = str(body.get("file") or "").strip()
    if not history_file:
        raise HTTPException(status_code=422, detail="file_required")
    try:
        saved = team_store.rollback(mode_id, history_file)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"rollback_failed: {e}")
    return {"mode_id": mode_id, "rolled_back_from": history_file, "saved": saved}
