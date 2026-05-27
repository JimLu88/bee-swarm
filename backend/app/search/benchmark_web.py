from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from ..rag.types import RagChunk
from ..settings_llm_rag import llm_rag_settings


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


async def _tavily_search(query: str, *, limit: int) -> tuple[list[RagChunk], dict[str, Any]]:
    key = llm_rag_settings.tavily_api_key
    if not key:
        return [], {"provider": "tavily", "skipped": True, "reason": "no_api_key"}
    payload = {
        "api_key": key,
        "query": query[:2000],
        "search_depth": "basic",
        "include_answer": False,
        "max_results": max(1, min(limit, 10)),
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post("https://api.tavily.com/search", json=payload)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return [], {"provider": "tavily", "ok": False, "error": repr(e)}
    out: list[RagChunk] = []
    for i, item in enumerate(data.get("results") or []):
        url = str(item.get("url") or "")
        title = str(item.get("title") or "web")
        body = str(item.get("content") or item.get("raw_content") or "")[:1200]
        dom = _domain(url)
        score = 1.0 - i * 0.03
        out.append(
            RagChunk(
                chunk_id=f"tavily-{i}-{hash(url) % 10_000_000}",
                title=title,
                content=body,
                score=max(0.1, score),
                meta={
                    "source": "tavily",
                    "domain": dom,
                    "source_url": url,
                },
            )
        )
    return out[:limit], {"provider": "tavily", "ok": True, "count": len(out)}


async def _exa_search(query: str, *, limit: int) -> tuple[list[RagChunk], dict[str, Any]]:
    key = llm_rag_settings.exa_api_key
    if not key:
        return [], {"provider": "exa", "skipped": True, "reason": "no_api_key"}
    payload = {"query": query[:2000], "numResults": max(1, min(limit, 10)), "useAutoprompt": True}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                "https://api.exa.ai/search",
                json=payload,
                headers={"x-api-key": key, "Content-Type": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return [], {"provider": "exa", "ok": False, "error": repr(e)}
    out: list[RagChunk] = []
    for i, item in enumerate(data.get("results") or []):
        url = str(item.get("url") or "")
        title = str(item.get("title") or "web")
        body = str(item.get("text") or item.get("snippet") or "")[:1200]
        dom = _domain(url)
        score = 1.0 - i * 0.03
        out.append(
            RagChunk(
                chunk_id=f"exa-{i}-{hash(url) % 10_000_000}",
                title=title,
                content=body,
                score=max(0.1, score),
                meta={
                    "source": "exa",
                    "domain": dom,
                    "source_url": url,
                },
            )
        )
    return out[:limit], {"provider": "exa", "ok": True, "count": len(out)}


async def fetch_benchmark_web_chunks(query: str, *, limit: int = 3) -> tuple[list[RagChunk], dict[str, Any]]:
    """
    Vision-layer web search for ``benchmark`` / ``xlab`` (Phase 3).

    Tavily first when ``TAVILY_API_KEY`` is set; otherwise Exa when ``EXA_API_KEY`` is set.
    """
    if not llm_rag_settings.benchmark_web_search:
        return [], {"enabled": False, "reason": "BENCHMARK_WEB_SEARCH disabled"}

    meta_out: dict[str, Any] = {"enabled": True, "attempts": []}

    chunks, m = await _tavily_search(query, limit=limit)
    meta_out["attempts"].append(m)
    if chunks:
        meta_out["used"] = "tavily"
        meta_out["count"] = len(chunks)
        return chunks, meta_out

    chunks, m = await _exa_search(query, limit=limit)
    meta_out["attempts"].append(m)
    if chunks:
        meta_out["used"] = "exa"
        meta_out["count"] = len(chunks)
        return chunks, meta_out

    meta_out["used"] = None
    meta_out["count"] = 0
    meta_out["note"] = "no_results_or_no_keys"
    return [], meta_out
