"""v8 思维框架接线 — 把 scenarios/thinking_frameworks/*.yaml 真正注入决策 prompt.

之前: 8 个框架 yaml (第一性原理/逆向/六顶帽/事前验尸/SCAMPER/TRIZ/类比/约束反转)
      定义好了, run_decision 也收 thinking_frameworks 参数, 但函数体从没用 → 死代码.
现在:
  - select_framework_ids(task, explicit): 用户显式选 → 用之; 否则按 trigger_keywords 命中 task 自动选.
  - build_framework_brief(...): 把选中框架的 system_prompt 拼成一段注入文字, 塞进部门/CEO prompt.
所有框架内容来自 yaml, 不硬编码; 加载结果缓存.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

FRAMEWORKS_DIR = Path(__file__).resolve().parent.parent / "scenarios" / "thinking_frameworks"

_CACHE: dict[str, dict[str, Any]] | None = None
MAX_FRAMEWORKS = 2  # 一次最多注入 2 个, 防止 prompt 过载 + 互相打架


def _load_all() -> dict[str, dict[str, Any]]:
    """读 thinking_frameworks/*.yaml → {id: {name, trigger_keywords, system_prompt, ...}}."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    out: dict[str, dict[str, Any]] = {}
    if FRAMEWORKS_DIR.is_dir():
        for f in sorted(FRAMEWORKS_DIR.glob("*.yaml")):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            fid = str(data.get("id") or f.stem)
            data["id"] = fid
            out[fid] = data
    _CACHE = out
    return out


def list_frameworks() -> list[dict[str, Any]]:
    return list(_load_all().values())


def select_framework_ids(task: str, explicit: list[str] | None = None,
                         max_n: int = MAX_FRAMEWORKS) -> list[str]:
    """选框架. 用户显式指定优先(校验存在); 否则按 trigger_keywords 命中 task 自动选."""
    fw = _load_all()
    if explicit:
        picked = [fid for fid in explicit if fid in fw]
        if picked:
            return picked[:max_n]
    t = task or ""
    scored: list[tuple[int, str]] = []
    for fid, data in fw.items():
        kws = data.get("trigger_keywords") or []
        hits = sum(1 for kw in kws if isinstance(kw, str) and kw and kw in t)
        if hits:
            scored.append((hits, fid))
    scored.sort(reverse=True)
    return [fid for _, fid in scored[:max_n]]


def build_framework_brief(task: str, explicit: list[str] | None = None) -> str:
    """拼成注入文字. 没选中任何框架 → 返回空串 (普通任务不啰嗦)."""
    fw = _load_all()
    ids = select_framework_ids(task, explicit)
    if not ids:
        return ""
    blocks: list[str] = []
    for fid in ids:
        data = fw.get(fid) or {}
        name = data.get("name") or fid
        sp = (data.get("system_prompt") or "").strip()
        if sp:
            blocks.append(f"【{name}】{sp}")
    if not blocks:
        return ""
    body = "\n".join(blocks)
    return ("【思维框架要求 (本题适用, 请在分析中显式运用)】\n" + body + "\n")
