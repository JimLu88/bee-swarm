"""capability_manifest — 给 p18 能力雷达用: 盘点本系统当前能力快照 (只读).

汇总: 场景 / 工具(四把剑) / 模型链 / 已装插件 / 关键框架依赖.
完全 best-effort: 任何来源失败就跳过该项, 绝不抛异常.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

_APP_DIR = Path(__file__).resolve().parent          # backend/app
_BACKEND_DIR = _APP_DIR.parent                        # backend
_REPO_DIR = _BACKEND_DIR.parent                       # h-semas
_EVO_DB = _APP_DIR / "evolution_coordinator" / "data" / "evolution_history.sqlite"


def _scenarios() -> list[str]:
    try:
        from .modes import list_modes
        return [f"{m.mode_id}({getattr(m, 'label', '')})" for m in list_modes()][:60]
    except Exception:
        return []


def _model_chain() -> dict[str, Any]:
    try:
        hub = json.loads((_BACKEND_DIR / "data" / "hub_settings.json").read_text(encoding="utf-8"))
        return {
            "default": hub.get("litellm_default_model", ""),
            "fallbacks": [s for s in str(hub.get("litellm_fallback_models", "")).split(",") if s][:12],
        }
    except Exception:
        return {}


def _installed_skills() -> list[str]:
    """p14 已采纳(active)的 skill/MCP 插件."""
    try:
        c = sqlite3.connect(str(_EVO_DB))
        rows = c.execute(
            "SELECT repo FROM skill_candidates WHERE status IN ('active','adopted') LIMIT 40"
        ).fetchall()
        c.close()
        return [r[0] for r in rows]
    except Exception:
        return []


def _key_deps() -> dict[str, list[str]]:
    """关键框架依赖 (后端 requirements 顶层 + 前端 package.json deps), 用于判断'有没有落后'."""
    out: dict[str, list[str]] = {"backend": [], "frontend": []}
    try:
        reqs = (_BACKEND_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines()
        out["backend"] = [r.split("==")[0].split(">=")[0].strip() for r in reqs
                          if r.strip() and not r.strip().startswith("#")][:50]
    except Exception:
        pass
    try:
        pkg = json.loads((_REPO_DIR / "frontend" / "package.json").read_text(encoding="utf-8"))
        out["frontend"] = list((pkg.get("dependencies") or {}).keys())[:50]
    except Exception:
        pass
    return out


# 这套系统"是什么"的一句话定位 — 让 LLM 知道升级要服务于什么
SYSTEM_PURPOSE = (
    "H-SEMAS「蜂群智囊团」: 一个多智能体 AI 决策助手 — 用户提一个纠结的问题, "
    "系统按场景召集一支虚拟顾问团(部门主管 + 员工 + CEO), 各自查书/联网/辩论, "
    "最后 CEO 汇总成可执行建议。技术栈: FastAPI + LangGraph(后端) / Next.js(前端) / "
    "LiteLLM 多模型路由 / Qdrant 向量库 / 多个 bee 微服务(爬虫/记忆/视觉/执行)。"
)


def build_manifest() -> dict[str, Any]:
    """系统能力快照 (结构化)."""
    return {
        "purpose": SYSTEM_PURPOSE,
        "scenarios": _scenarios(),
        "model_chain": _model_chain(),
        "installed_skills": _installed_skills(),
        "key_deps": _key_deps(),
    }


def manifest_text(m: dict[str, Any] | None = None) -> str:
    """压成给 LLM 看的紧凑文本."""
    m = m or build_manifest()
    deps = m.get("key_deps", {})
    return (
        f"【系统定位】{m.get('purpose', '')}\n"
        f"【已支持场景({len(m.get('scenarios', []))}个)】" + ", ".join(m.get("scenarios", [])[:40]) + "\n"
        f"【当前模型链】默认={m.get('model_chain', {}).get('default', '?')}; "
        f"备用={', '.join(m.get('model_chain', {}).get('fallbacks', [])[:8])}\n"
        f"【已装插件/MCP】" + (", ".join(m.get("installed_skills", [])) or "无") + "\n"
        f"【后端关键依赖】" + ", ".join(deps.get("backend", [])[:30]) + "\n"
        f"【前端关键依赖】" + ", ".join(deps.get("frontend", [])[:30]) + "\n"
    )
