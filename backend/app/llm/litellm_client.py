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
    ) -> LlmResponse:
        if llm_rag_settings.llm_provider != "litellm":
            return LlmResponse(
                text="[simulated] LLM_PROVIDER!=litellm; using placeholder response.",
                raw={"enabled": False, "provider": llm_rag_settings.llm_provider},
            )

        # Lazy import so Phase 1 works without litellm configured.
        from litellm import acompletion  # type: ignore

        sys_msg = system or "You are a helpful expert consultant. Return concise, actionable output."

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
                            {"role": "user", "content": prompt},
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

