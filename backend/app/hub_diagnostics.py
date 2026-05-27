"""
Hub settings diagnostics: per-surface connectivity (no chat) vs minimal chat probes.

Uses current in-process ``llm_rag_settings`` (after hub apply / .env).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .settings_llm_rag import llm_rag_settings
from .status import check_qdrant

# Direct-to-vendor probes（未配置 LiteLLM_API_Base 时）：模型名与 LiteLLM 文档一致。
# 配置了 OpenAI 兼容网关时，探测统一改用 hub 里的「默认模型」（与「全渠道多品牌 AI 客服」一致：
# 中转只认识网关里登记的 model id，如 openai/gpt-4o-mini，勿硬编码 gemini/deepseek 渠道路由）。
_LLM_PROBE_SPECS: list[tuple[str, str, str]] = [
    ("openai", "openai_api_key", "gpt-4o-mini"),
    ("anthropic", "anthropic_api_key", "anthropic/claude-3-5-haiku-20241022"),
    ("gemini", "gemini_api_key", "gemini/gemini-2.0-flash"),
    ("deepseek", "deepseek_api_key", "deepseek/deepseek-chat"),
    ("doubao", "doubao_api_key", "volcengine/doubao-lite-4k-character"),
]


def _key_configured(field: str) -> bool:
    v = getattr(llm_rag_settings, field, None)
    return isinstance(v, str) and bool(v.strip())


def _proxy_mode() -> bool:
    return bool((llm_rag_settings.litellm_base_url or "").strip())


def _chat_probe_eligible(key_field: str) -> bool:
    """槽位已填 Key，或「网关 + OpenAI_Key + 默认模型」可共用探测（与 AI 客服工作台一致）。"""
    if _key_configured(key_field):
        return True
    return bool(
        _proxy_mode()
        and _key_configured("openai_api_key")
        and (llm_rag_settings.litellm_default_model or "").strip()
    )


def _resolve_probe_api_key(provider_id: str, key_field: str) -> str:
    """槽位已填则用该槽；否则网关场景下空槽回退 OpenAI_Key（与 AI 客服「一格密钥」一致）。"""
    k = (getattr(llm_rag_settings, key_field, None) or "").strip()
    if k:
        return k
    if _proxy_mode() and _key_configured("openai_api_key"):
        return (llm_rag_settings.openai_api_key or "").strip()
    return ""


def _api_key_for_probe(model: str, key_field: str) -> str:
    """
    与 ``apps/core/ai/llm_client.resolve_litellm_api_key`` 一致：按**实际请求的 model** 选 Key。
    网关下探测模型多为 ``openai/...``，必须用 OpenAI 槽位密钥，不能用已填的 Gemini/DeepSeek 格
    （否则与客服项目行为不一致且必然 401/渠道错）。
    """
    by_model = _api_key_for_model(model)
    if by_model:
        return by_model
    return _resolve_probe_api_key("", key_field)


def _resolve_probe_model(provider_id: str, canonical_model: str) -> str:
    """配置了网关且填写了默认模型时，所有对话探测走该模型 ID（避免网关无 gemini/deepseek 硬编码渠道）。"""
    default_m = (llm_rag_settings.litellm_default_model or "").strip()
    if _proxy_mode() and default_m:
        return default_m
    if provider_id == "doubao":
        if "volcengine/" in default_m or "doubao" in default_m.lower():
            return default_m
    return canonical_model


def _api_key_for_model(model: str) -> str:
    """按默认模型前缀选择密钥（用于「默认模型」单行探测）。"""
    m = (model or "").strip().lower()
    if m.startswith("openai/"):
        return (llm_rag_settings.openai_api_key or "").strip()
    if m.startswith("anthropic/"):
        return (llm_rag_settings.anthropic_api_key or "").strip()
    if m.startswith("gemini/") or m.startswith("google/"):
        return (llm_rag_settings.gemini_api_key or "").strip()
    if m.startswith("deepseek/"):
        return (llm_rag_settings.deepseek_api_key or "").strip()
    if "volcengine/" in m or "doubao" in m:
        return (llm_rag_settings.doubao_api_key or "").strip()
    if "gpt" in m or "o1" in m or "o3" in m:
        return (llm_rag_settings.openai_api_key or "").strip()
    if "claude" in m:
        return (llm_rag_settings.anthropic_api_key or "").strip()
    if "gemini" in m:
        return (llm_rag_settings.gemini_api_key or "").strip()
    return (llm_rag_settings.openai_api_key or llm_rag_settings.anthropic_api_key or "").strip()


def _litellm_extra() -> dict[str, Any]:
    extra: dict[str, Any] = {}
    if llm_rag_settings.litellm_base_url:
        extra["api_base"] = llm_rag_settings.litellm_base_url.rstrip("/")
    return extra


async def _ping_litellm_proxy() -> dict[str, Any]:
    base = (llm_rag_settings.litellm_base_url or "").strip().rstrip("/")
    if not base:
        return {"ok": True, "skipped": True, "detail": "no_litellm_base_url"}
    last = ""
    for path in ("/health", "/health/liveness", "/v1/models", "/"):
        url = f"{base}{path}"
        try:
            async with httpx.AsyncClient(timeout=6.0) as c:
                r = await c.get(url)
                if r.status_code < 500:
                    return {"ok": True, "skipped": False, "detail": f"HTTP {r.status_code} {url}"}
                last = f"HTTP {r.status_code} {url}"
        except Exception as e:
            last = repr(e)
    return {"ok": False, "skipped": False, "detail": last or "proxy_unreachable"}


async def _tavily_connectivity() -> dict[str, Any]:
    if not _key_configured("tavily_api_key"):
        return {"id": "tavily", "ok": False, "skipped": True, "configured": False, "detail": "not_configured"}
    payload = {
        "api_key": llm_rag_settings.tavily_api_key,
        "query": "connectivity",
        "search_depth": "basic",
        "include_answer": False,
        "max_results": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as c:
            r = await c.post("https://api.tavily.com/search", json=payload)
            ok = r.status_code < 400
            return {"id": "tavily", "ok": ok, "skipped": False, "configured": True, "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"id": "tavily", "ok": False, "skipped": False, "configured": True, "detail": repr(e)}


async def _exa_connectivity() -> dict[str, Any]:
    if not _key_configured("exa_api_key"):
        return {"id": "exa", "ok": False, "skipped": True, "configured": False, "detail": "not_configured"}
    payload = {"query": "connectivity", "numResults": 1, "useAutoprompt": True}
    try:
        async with httpx.AsyncClient(timeout=12.0) as c:
            r = await c.post(
                "https://api.exa.ai/search",
                json=payload,
                headers={"x-api-key": llm_rag_settings.exa_api_key, "Content-Type": "application/json"},
            )
            ok = r.status_code < 400
            return {"id": "exa", "ok": ok, "skipped": False, "configured": True, "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"id": "exa", "ok": False, "skipped": False, "configured": True, "detail": repr(e)}


async def run_connectivity() -> dict[str, Any]:
    """Layer-1 checks: RAG / proxy / search HTTP + whether each LLM key slot is configured (with shared proxy ping when set)."""
    q = await check_qdrant()
    proxy = await _ping_litellm_proxy()
    rag = llm_rag_settings.rag_backend
    llm_mode = llm_rag_settings.llm_provider

    llm_rows: list[dict[str, Any]] = []
    for pid, key_field, _model in _LLM_PROBE_SPECS:
        cfg = _key_configured(key_field)
        if llm_mode != "litellm":
            llm_rows.append(
                {
                    "id": pid,
                    "ok": True,
                    "skipped": True,
                    "configured": cfg,
                    "detail": "llm_provider!=litellm",
                }
            )
            continue
        if not cfg:
            llm_rows.append({"id": pid, "ok": False, "skipped": True, "configured": False, "detail": "not_configured"})
            continue
        if llm_rag_settings.litellm_base_url and str(llm_rag_settings.litellm_base_url).strip():
            ok = bool(proxy.get("ok")) and not proxy.get("skipped")
            llm_rows.append(
                {
                    "id": pid,
                    "ok": ok,
                    "skipped": False,
                    "configured": True,
                    "detail": "via_litellm_proxy" if ok else (proxy.get("detail") or "proxy_fail"),
                }
            )
        else:
            # Direct-to-vendor: lightweight unauthenticated reachability to public API host
            host = {
                "openai": "https://api.openai.com/",
                "anthropic": "https://api.anthropic.com/",
                "gemini": "https://generativelanguage.googleapis.com/",
                "deepseek": "https://api.deepseek.com/",
                "doubao": "https://ark.cn-beijing.volces.com/",
            }.get(pid, "https://api.openai.com/")
            try:
                async with httpx.AsyncClient(timeout=5.0) as c:
                    r = await c.get(host)
                    ok = r.status_code < 500
                    llm_rows.append(
                        {
                            "id": pid,
                            "ok": ok,
                            "skipped": False,
                            "configured": True,
                            "detail": f"HTTP {r.status_code} {host}",
                        }
                    )
            except Exception as e:
                llm_rows.append({"id": pid, "ok": False, "skipped": False, "configured": True, "detail": repr(e)})

    tavily = await _tavily_connectivity()
    exa = await _exa_connectivity()

    return {
        "llm_provider": llm_mode,
        "qdrant": {"ok": q.ok, "detail": q.detail, "rag_backend": rag},
        "litellm_proxy": proxy,
        "llm_keys": llm_rows,
        "search": [tavily, exa],
    }


def _probe_chat_sync(provider_id: str, model: str, *, api_key: str) -> dict[str, Any]:
    """
    与 AI 客服 ``litellm_completion_text`` 相同：同步 ``litellm.completion`` + 显式 api_key/api_base。
    避免 acompletion 与部分网关对 max_tokens 映射不一致（曾出现 max_output_tokens=12）。
    """
    if llm_rag_settings.llm_provider != "litellm":
        return {"id": provider_id, "ok": False, "skipped": True, "detail": "llm_provider!=litellm", "preview": ""}
    try:
        import litellm  # type: ignore
    except Exception as e:
        return {"id": provider_id, "ok": False, "skipped": True, "detail": f"litellm_import:{e!r}", "preview": ""}

    try:
        kwargs: dict[str, Any] = {
            "model": model.strip(),
            "messages": [
                {"role": "system", "content": "Reply with exactly one word: OK"},
                {"role": "user", "content": "Say OK."},
            ],
            "api_key": (api_key or "").strip(),
            # 与客服侧一致用足够大的上限；部分网关把 max_tokens 映射为 max_output_tokens 且下限 16。
            "max_tokens": 256,
            "temperature": 0.0,
            **_litellm_extra(),
        }
        resp = litellm.completion(**kwargs)
        choice = resp.choices[0]
        msg = choice.message
        text = str(getattr(msg, "content", None) or "")
        if not text.strip():
            blocks = getattr(msg, "content_blocks", None)
            if blocks:
                parts: list[str] = []
                for b in blocks:
                    if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                        parts.append(str(b["text"]))
                if parts:
                    text = "\n".join(parts)
        text = text.strip()[:200]
        ok = len(text) > 0
        note = ""
        if _proxy_mode() and model == (llm_rag_settings.litellm_default_model or "").strip():
            note = "; probe_model=gateway_default"
        return {
            "id": provider_id,
            "ok": ok,
            "skipped": False,
            "detail": f"model={model}{note}",
            "preview": text,
        }
    except Exception as e:
        return {"id": provider_id, "ok": False, "skipped": False, "detail": repr(e), "preview": ""}


async def _probe_chat(provider_id: str, model: str, *, api_key: str) -> dict[str, Any]:
    return await asyncio.to_thread(_probe_chat_sync, provider_id, model, api_key=api_key)


async def run_chat_probes() -> dict[str, Any]:
    """Layer-2: one minimal completion per configured LLM key slot (may incur small cost)."""
    rows: list[dict[str, Any]] = []
    for pid, key_field, canonical in _LLM_PROBE_SPECS:
        if not _chat_probe_eligible(key_field):
            rows.append({"id": pid, "ok": False, "skipped": True, "detail": "not_configured", "preview": ""})
            continue
        m = _resolve_probe_model(pid, canonical)
        api_key = _api_key_for_probe(m, key_field)
        if not api_key:
            rows.append({"id": pid, "ok": False, "skipped": True, "detail": "no_api_key", "preview": ""})
            continue
        rows.append(await _probe_chat(pid, m, api_key=api_key))

    # Optional: default model probe（密钥按模型前缀解析，与 AI 客服一致）
    default_probe: dict[str, Any] | None = None
    dm = (llm_rag_settings.litellm_default_model or "").strip()
    if llm_rag_settings.llm_provider == "litellm" and dm:
        dk = _api_key_for_probe(dm, "openai_api_key")
        if dk:
            default_probe = await _probe_chat("litellm_default", dm, api_key=dk)
        else:
            default_probe = {"id": "litellm_default", "ok": False, "skipped": True, "detail": "no_api_key_for_default_model", "preview": ""}

    return {"llm_provider": llm_rag_settings.llm_provider, "llm_chat": rows, "litellm_default": default_probe}


async def run_all_diagnostics() -> dict[str, Any]:
    c, ch = await asyncio.gather(run_connectivity(), run_chat_probes())
    return {"connectivity": c, "chat": ch}
