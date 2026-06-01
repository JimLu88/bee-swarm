from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..settings_llm_rag import llm_rag_settings


@dataclass(frozen=True)
class LlmResponse:
    text: str
    raw: dict[str, Any]


class LiteLlmClient:
    """
    Phase 2 scaffold. We keep it import-safe even if keys are missing.

    In the next step we will wire:
    - litellm.completion() with fallbacks
    - per-dept model mapping
    - rate-limit retries
    """

    def _extra(self, model: str = "") -> dict[str, Any]:
        extra: dict[str, Any] = {}
        # v10 关键修复: 本地 ollama 模型必须发到本机 ollama 服务, 不能套云网关 base_url,
        # 否则会拼成 https://<gateway>/v1/api/chat → "Invalid URL" → 本地档/分类全失败.
        is_local = model.lower().startswith(("ollama", "local"))
        if is_local:
            import os as _os
            extra["api_base"] = _os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")
            # 本地模型不需要云网关 key (ollama 不校验), 显式不传, 避免误用.
            # v10 关键: ollama 默认 num_ctx 仅 2048 → 长 prompt(如 63 场景菜单)被静默截断 →
            # 模型看不全 → 乱答/兜底。显式调大上下文窗口, 让完整 prompt 进得去.
            try:
                extra["num_ctx"] = int(_os.environ.get("OLLAMA_NUM_CTX", "8192"))
            except ValueError:
                extra["num_ctx"] = 8192
        else:
            if llm_rag_settings.litellm_base_url:
                extra["api_base"] = llm_rag_settings.litellm_base_url
            # v6-U 显式传 api_key (防 LiteLLM 找不到 env 而 silent fail)
            api_key = getattr(llm_rag_settings, "openai_api_key", None)
            if not api_key:
                import os as _os
                api_key = _os.environ.get("OPENAI_API_KEY")
            if api_key:
                extra["api_key"] = api_key
        # v6-U 显式 timeout 150s (大 prompt 给 Opus 留余量) + 禁 LiteLLM 内部重试 (我们自己重试)
        extra["timeout"] = 150.0
        extra["num_retries"] = 0
        # v6-W-fix 关键修复: 不设 max_tokens 时网关默认截断在 ~1k tokens,
        # 部门要求输出 JSON, 截断 → JSON 不完整 → parse 失败 → 退化成占位符.
        # 给足额度让 consensus+conflicts+评分 JSON 完整输出.
        extra["max_tokens"] = 4000
        return extra

    async def _ollama_chat(
        self,
        model: str,
        system: str,
        user_text: str,
        images: list[str] | None = None,
    ) -> str:
        """v10: 直连本机 ollama /api/chat。绕开 litellm 的 ollama 封装(会丢 num_ctx/温度乱来)。
        temperature 低 + num_ctx 大, 保证长 prompt(场景菜单/人设)不被截断、输出稳定。"""
        import os as _os
        import httpx  # FastAPI 栈已依赖

        base = _os.environ.get("OLLAMA_API_BASE", "http://localhost:11434").rstrip("/")
        name = model.split("/", 1)[1] if "/" in model else model
        try:
            num_ctx = int(_os.environ.get("OLLAMA_NUM_CTX", "8192"))
        except ValueError:
            num_ctx = 8192
        user_msg: dict[str, Any] = {"role": "user", "content": user_text}
        if images:
            b64: list[str] = []
            for u in images:
                if isinstance(u, str) and u.strip().startswith("data:") and "," in u:
                    b64.append(u.split(",", 1)[1])  # 去掉 data:...;base64, 前缀
                elif isinstance(u, str):
                    b64.append(u)
            if b64:
                user_msg["images"] = b64
        body = {
            "model": name,
            "messages": [{"role": "system", "content": system}, user_msg],
            "stream": False,
            "options": {"num_ctx": num_ctx, "temperature": 0.2, "num_predict": 4000},
        }
        async with httpx.AsyncClient(timeout=180.0) as cli:
            r = await cli.post(f"{base}/api/chat", json=body)
            r.raise_for_status()
            data = r.json()
        return str((data.get("message") or {}).get("content", "") or "")

    @staticmethod
    def _is_retryable(err: Exception) -> bool:
        msg = (repr(err) + " " + str(err)).lower()
        return any(
            k in msg
            for k in [
                "rate limit",
                "429",
                "timeout",
                "timed out",
                "temporarily unavailable",
                "service unavailable",
                "connection reset",
                "econnreset",
                "gateway timeout",
                "502",
                "503",
                "504",
            ]
        )

    async def complete(
        self,
        *,
        model: str,
        prompt: str,
        fallbacks: list[str] | None = None,
        system: str | None = None,
        images: list[str] | None = None,
    ) -> LlmResponse:
        """v6-X: ``images`` 非空时按 OpenAI 多模态格式拼 user content.
        调方 (decision_engine._run_dept) 负责确保 model 在 vision_capable 里, 否则模型会报错."""
        if llm_rag_settings.llm_provider != "litellm":
            return LlmResponse(
                text="[simulated] LLM_PROVIDER!=litellm; using placeholder response.",
                raw={"enabled": False, "provider": llm_rag_settings.llm_provider},
            )

        # Lazy import so Phase 1 works without litellm configured.
        from litellm import acompletion  # type: ignore

        sys_msg = system or "You are a helpful expert consultant. Return concise, actionable output."

        # v6-X: 有图就拼多模态 content; 没图保持纯文本 (向后兼容).
        if images:
            user_content: Any = [{"type": "text", "text": prompt}]
            for img_url in images:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": img_url},  # data URL 或 https URL litellm 都接受
                })
        else:
            user_content = prompt

        models = [model] + [m for m in (fallbacks or []) if m and m != model]
        if not models:
            models = [model]

        last_err: Exception | None = None
        for m in models:
            is_local = m.lower().startswith(("ollama", "local"))
            for attempt in range(llm_rag_settings.litellm_max_retries + 1):
                try:
                    # v10: 本地 ollama 直接走原生 /api/chat — litellm 的 ollama 封装会丢 num_ctx/
                    # 乱用默认温度, 导致长 prompt 被截断 + 模型乱答兜底。直连稳定可控。
                    if is_local:
                        text = await self._ollama_chat(m, sys_msg, prompt, images)
                        return LlmResponse(text=text, raw={"model": m, "via": "ollama_native"})
                    resp = await acompletion(
                        model=m,
                        messages=[
                            {
                                "role": "system",
                                "content": sys_msg,
                            },
                            {"role": "user", "content": user_content},
                        ],
                        **self._extra(m),
                    )
                    text = ""
                    try:
                        text = resp["choices"][0]["message"]["content"]  # type: ignore[index]
                    except Exception:
                        text = str(resp)
                    return LlmResponse(text=text, raw={"model": m, "resp": resp})  # type: ignore[arg-type]
                except Exception as e:
                    last_err = e
                    if attempt >= llm_rag_settings.litellm_max_retries or not self._is_retryable(e):
                        break
                    # backoff
                    import asyncio

                    await asyncio.sleep((llm_rag_settings.litellm_retry_base_ms / 1000.0) * (2**attempt))

        return LlmResponse(
            text=f"[litellm failed] {last_err!r}",
            raw={"enabled": True, "provider": "litellm", "attempted_models": models},
        )


litellm_client = LiteLlmClient()

