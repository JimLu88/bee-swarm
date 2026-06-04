# -*- coding: utf-8 -*-
"""#2 联网实时增强(临时RAG)—— 决策时用七剑客 bee-scraper 实时联网抓权威资料注入部门提示。

- 默认关闭:仅当环境变量 BOOKS_WEB_RAG=1 时启用(避免无搜索源时每次决策白调、增加延迟)。
- 需要 bee-scraper + Tavily/Exa 等搜索 key(在设置里配)。
- 任何异常/无结果 → 返回空串, 不影响决策。
"""
from __future__ import annotations

import os


def web_enabled() -> bool:
    return os.environ.get("BOOKS_WEB_RAG", "0") == "1"


def web_context(query: str, k: int = 3, max_chars: int = 1200) -> str:
    if not web_enabled():
        return ""
    try:
        from ..tools.seven_clients import bee_clients
        r = bee_clients.web_search(query) or {}
    except Exception:
        return ""
    items = r.get("results") or r.get("items") or r.get("data") or []
    if not isinstance(items, list) or not items:
        return ""
    lines = ["[实时联网检索 — 供参考的最新公开资料(可能未经核实, 谨慎引用)]"]
    used = 0
    for it in items[:k]:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or it.get("name") or "")
        body = str(it.get("snippet") or it.get("content") or it.get("summary") or it.get("text") or "")
        src = str(it.get("url") or it.get("link") or "")
        piece = f"- {title}: {' '.join(body.split())[:300]}" + (f" ({src})" if src else "")
        if used + len(piece) > max_chars:
            break
        lines.append(piece)
        used += len(piece)
    return "\n".join(lines) if len(lines) > 1 else ""
