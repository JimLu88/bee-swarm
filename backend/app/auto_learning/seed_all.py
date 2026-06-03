"""seed_all — 全场景预灌书 (一次性, 取代"首问才懒加载现灌").

用户痛点: 懒加载导致"第一次问永远没有专业知识"。本模块在部署后跑一次 (或反复跑到全 done),
对每个 mode: 确保有 team(没有就生成)→ 经 lazy_seed.run_lazy_seed 灌书到 ROLE_TARGETS。
run_lazy_seed 自带"已灌够的 persona 跳过"+ 单次 LLM 调用上限, 所以可安全续跑。

触发:
- API:  POST /api/learning/seed-all      (后台跑, GET /api/learning/seed-all/status 看进度)
- CLI:  python -m app.auto_learning.seed_all
"""
from __future__ import annotations

from typing import Any

from .lazy_seed import get_status, run_lazy_seed
from ..modes import MODES

# 进度 (模块级, 供 /seed-all/status 读)
_PROGRESS: dict[str, Any] = {
    "running": False, "total": 0, "done": 0, "current": "", "results": {},
}


def seed_all_progress() -> dict[str, Any]:
    return dict(_PROGRESS)


async def _ensure_team(mode_id: str) -> dict[str, Any]:
    """该场景没有 team.yaml 就现生成并保存; 已有则直接返回。"""
    from ..persona.team_store import load_team, save_team
    team = load_team(mode_id)
    if team:
        return team
    from ..persona import team_generator
    team = await team_generator.generate_full_team(mode_id)
    save_team(mode_id, team)
    return team


async def seed_all_modes(only_missing: bool = True) -> dict[str, Any]:
    """遍历所有 mode 灌书。only_missing=True 跳过已 done 的 (可反复调用续灌)。"""
    ids = list(MODES.keys())
    _PROGRESS.update(running=True, total=len(ids), done=0, current="", results={})
    try:
        for mode_id in ids:
            _PROGRESS["current"] = mode_id
            st = get_status(mode_id)
            if only_missing and st.get("status") == "done":
                _PROGRESS["results"][mode_id] = "skip_done"
                _PROGRESS["done"] += 1
                continue
            try:
                team = await _ensure_team(mode_id)
            except Exception as e:  # noqa: BLE001
                _PROGRESS["results"][mode_id] = f"team_error: {e!r}"
                _PROGRESS["done"] += 1
                continue
            try:
                r = await run_lazy_seed(mode_id, team)
                _PROGRESS["results"][mode_id] = r.get("status", "?")
            except Exception as e:  # noqa: BLE001
                _PROGRESS["results"][mode_id] = f"error: {e!r}"
            _PROGRESS["done"] += 1
    finally:
        _PROGRESS["running"] = False
        _PROGRESS["current"] = ""
    return dict(_PROGRESS)


if __name__ == "__main__":
    import asyncio
    import json
    out = asyncio.run(seed_all_modes())
    print(json.dumps(out, ensure_ascii=False, indent=2))
