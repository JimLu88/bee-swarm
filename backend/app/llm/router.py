from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..hub_settings_store import dept_llm_model_for
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
            return LLMChoice(provider="litellm", model=dept_llm_model_for(dept))

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


# v13 推理模型路由: 复杂题 (需一步步推导/算账/比合同) 才切到推理模型, 简单题用主模型省钱省时.
_REASONING_KEYWORDS: tuple[str, ...] = (
    "算", "计算", "对比", "比较", "合同", "条款", "税", "报税", "保险", "期权", "收益",
    "利率", "回报", "现金流", "估值", "概率", "推导", "证明", "方案", "划算", "性价比",
    "贷款", "还款", "分期", "预算", "最优", "权衡", "利弊", "测算", "几种", "哪个更",
)


def reasoning_model_for(task: str) -> str | None:
    """配了推理模型 且 任务看起来需要多步推导 → 返回推理模型名; 否则 None (用主模型)."""
    rm = (llm_rag_settings.reasoning_model or "").strip()
    if not rm:
        return None
    t = task or ""
    if len(t) > 200 or any(k in t for k in _REASONING_KEYWORDS):
        return rm
    return None

