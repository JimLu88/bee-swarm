from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..settings_llm_rag import llm_rag_settings


Provider = Literal["simulated", "litellm"]


@dataclass(frozen=True)
class LLMChoice:
    provider: Provider
    model: str


class LLMRouter:
    """
    Phase 2 scaffold:
    - Later this becomes LiteLLM routing + fallbacks.
    - For now we keep the system runnable with a simulated provider.
    """

    def __init__(self) -> None:
        self._default = LLMChoice(provider="simulated", model="sim-1")

    def pick_for_dept(self, dept: str) -> LLMChoice:
        if llm_rag_settings.llm_provider == "litellm":
            # MVP mapping: everything uses one default. Phase 2 will add per-dept models.
            _ = dept
            return LLMChoice(provider="litellm", model=llm_rag_settings.litellm_default_model)

        _ = dept
        return self._default

    def fallbacks(self) -> list[str]:
        raw = llm_rag_settings.litellm_fallback_models or ""
        models = [m.strip() for m in raw.split(",") if m.strip()]
        # ensure default is first
        if llm_rag_settings.litellm_default_model and llm_rag_settings.litellm_default_model not in models:
            models.insert(0, llm_rag_settings.litellm_default_model)
        return models[:8]


router = LLMRouter()

