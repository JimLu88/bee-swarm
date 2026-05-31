"""v6-X 视觉能力查询 + 瞎子模型 fallback.

读 backend/data/vision_models.yaml 一次, lru_cache 进程级缓存.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _yaml_path() -> Path:
    # backend/app/llm/ → backend/data/
    return Path(__file__).resolve().parent.parent.parent / "data" / "vision_models.yaml"


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    p = _yaml_path()
    if not p.exists():
        return {"vision_capable": [], "text_only": [], "vision_fallback": {}, "image_summary_model": {}}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def is_vision_capable(model: str) -> bool:
    """精确字符串匹配; 前缀宽松 (claude-haiku-4-5 命中 claude-haiku-4-5-20251001)."""
    if not model:
        return False
    vc = _load().get("vision_capable") or []
    if model in vc:
        return True
    for v in vc:
        if model.startswith(v) or v.startswith(model):
            return True
    return False


def swap_for_vision(model: str) -> tuple[str, bool]:
    """模型瞎? 查表换视觉兄弟. 返回 (effective_model, was_swapped).

    若已是视觉模型 → 原样返回, swapped=False.
    若是 text_only 但无 fallback 配置 → 原样返回, swapped=False (调方决定要不要忽略图).
    """
    if is_vision_capable(model):
        return (model, False)
    fb = (_load().get("vision_fallback") or {}).get(model)
    if isinstance(fb, str) and fb.strip():
        return (fb.strip(), True)
    return (model, False)


def image_summary_model(tier: str) -> str:
    """v6-X-5 一次性图像摘要专用模型 (按档选最便宜的视觉模型)."""
    t = (tier or "A").upper()
    table = _load().get("image_summary_model") or {}
    return str(table.get(t) or table.get("A") or "openai/gemini-3.5-flash")


def reload_cache() -> None:
    """测试/热更新用; 生产无需调."""
    _load.cache_clear()
