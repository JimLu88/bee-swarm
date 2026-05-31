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

    def _extra(self) -> dict[str, Any]:
        extra: dict[str, Any] = {}
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
            for attempt in range(llm_rag_settings.litellm_max_retries + 1):
                try:
                    resp = await acompletion(
                        model=m,
                        messages=[
                            {
                                "role": "system",
                                "content": sys_msg,
                            },
                            {"role": "user", "content": user_content},
                        ],
                        **self._extra(),
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

