"""user_profile — v13 #2 长期记忆 + 用户画像 (单用户, 轻量本地 JSON).

跨决策记住"用户是谁/偏好/处境", 提问时注入 CEO 综合阶段, 让顾问团认识你,
不用每次重新交代背景, 建议也更贴合你。

设计取舍:
- 单用户场景几十条画像事实, 直接全量注入即可 → **不引入 Qdrant** (proposal 里说的 Qdrant 是过度设计).
- 存本地 backend/data/user_profile.json: {"enabled": bool, "facts": [{"text","ts"}]}.
- 隐私: 文件里 enabled=false 或 env HSEMAS_USER_MEMORY=0 → 整体关闭; 前端可查看/删除/清空.
- 决策后 fire-and-forget 异步提炼, 不给主链路加延迟.

调用方: decision_engine.py (format_for_prompt 注入 + store_async 提炼), main.py (管理 API).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

_MAX_FACTS = 80       # 文件里最多留多少条 (超出丢最旧)
_INJECT_LIMIT = 24    # 注入提示词时最多带多少条
_EXTRACT_MODEL = "openai/deepseek-v4-flash"
_bg_tasks: set[asyncio.Task] = set()  # 持有后台任务引用, 防被 GC


def _path() -> Path:
    p = Path(__file__).resolve().parent.parent / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p / "user_profile.json"


def _read() -> dict[str, Any]:
    p = _path()
    if not p.is_file():
        return {"enabled": True, "facts": []}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            return {"enabled": True, "facts": []}
        d.setdefault("enabled", True)
        d.setdefault("facts", [])
        return d
    except Exception:
        return {"enabled": True, "facts": []}


def _write(d: dict[str, Any]) -> None:
    facts = d.get("facts") or []
    d["facts"] = facts[-_MAX_FACTS:]
    try:
        _path().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def enabled() -> bool:
    """env 强制关 (=0) 优先; 否则看文件里的 enabled 开关 (默认开)."""
    if os.environ.get("HSEMAS_USER_MEMORY", "1") == "0":
        return False
    return bool(_read().get("enabled", True))


def get_state() -> dict[str, Any]:
    """给前端管理面板: {enabled, facts:[{text,ts}]}."""
    return _read()


def set_enabled(on: bool) -> None:
    d = _read()
    d["enabled"] = bool(on)
    _write(d)


def add_facts(new: list[str]) -> int:
    """去重后追加画像事实, 返回新增条数."""
    d = _read()
    facts = d.get("facts") or []
    existing = {str(f.get("text", "")).strip() for f in facts}
    added = 0
    for t in new:
        t = (t or "").strip()
        if t and t not in existing and 1 < len(t) <= 120:
            facts.append({"text": t, "ts": int(time.time())})
            existing.add(t)
            added += 1
    if added:
        d["facts"] = facts
        _write(d)
    return added


def delete_fact(index: int) -> bool:
    d = _read()
    facts = d.get("facts") or []
    if 0 <= index < len(facts):
        facts.pop(index)
        d["facts"] = facts
        _write(d)
        return True
    return False


def clear() -> None:
    d = _read()
    d["facts"] = []
    _write(d)


def format_for_prompt() -> str:
    """供 decision_engine 注入 CEO 提示词; 关闭/为空 → 空串."""
    if not enabled():
        return ""
    facts = (_read().get("facts") or [])[-_INJECT_LIMIT:]
    if not facts:
        return ""
    lines = "\n".join(f"- {f.get('text', '')}" for f in facts if f.get("text"))
    if not lines:
        return ""
    return (
        "【关于这位用户 (长期记忆, 供参考; 与本次问题冲突时以本次为准)】\n"
        f"{lines}\n"
    )


async def extract_and_store(task: str, ceo_text: str) -> None:
    """从一次咨询里提炼关于用户本人的长期事实, 去重写入. best-effort."""
    if not enabled() or not (task or "").strip():
        return
    try:
        from .llm.litellm_client import litellm_client
        from .llm.parsing import _extract_json

        prompt = (
            "从下面这次咨询里, 提炼关于【用户本人】的**长期稳定**事实/偏好/处境 "
            "(不是这次问题的临时内容), 例如: 所在城市、职业/行业、家庭情况、预算偏好、"
            "已有资产/设备、口味、健康状况、价值观等。只挑明确无疑的, 每条≤20字, 最多5条; "
            '没有就返回空数组。严格只输出 JSON: {"facts":["...","..."]}\n\n'
            f"咨询内容: {(task or '')[:600]}"
        )
        resp = await litellm_client.complete(
            model=_EXTRACT_MODEL, prompt=prompt,
            system="你只输出严格 JSON, 不要解释或代码块。",
        )
        obj = _extract_json(resp.text or "") or {}
        facts = obj.get("facts") if isinstance(obj, dict) else None
        if isinstance(facts, list):
            add_facts([str(x) for x in facts])
    except Exception:
        pass


def store_async(task: str, ceo_text: str) -> None:
    """fire-and-forget 提炼 (不阻塞决策返回). 无事件循环时静默跳过."""
    if not enabled():
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            t = loop.create_task(extract_and_store(task, ceo_text))
            _bg_tasks.add(t)
            t.add_done_callback(_bg_tasks.discard)
    except Exception:
        pass
