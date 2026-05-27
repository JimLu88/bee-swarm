from __future__ import annotations

from typing import Any

from .llm.litellm_client import litellm_client
from .llm.router import router as llm_router
from .modes import get_mode

_EVOLVE_SYSTEM = (
    "你是提示词优化器（DSPy 风格）：把「部门基因」改写得更清晰、可执行、适合多轮辩论与结构化打分。"
    "只输出改写后的中文基因正文（单段），不要 Markdown 代码围栏、不要前后说明。"
)


async def evolve_gene_prompt(
    *,
    mode_id: str,
    dept: str,
    active_prompt: str,
    task_sample: str,
) -> tuple[str, dict[str, Any]]:
    mode = get_mode(mode_id)
    scenario = (mode.scenario_description or "").strip()
    hint = (mode.default_task_hint or "").strip()
    sample = (task_sample or "").strip() or hint or "（无具体任务样例：请泛化优化）"
    user = (
        f"模式：{mode.label}（{mode_id}）\n部门：{dept}\n"
        f"场景说明：{scenario or '—'}\n\n"
        f"当前基因：\n---\n{active_prompt}\n---\n\n"
        f"校准任务样例：\n{sample[:4000]}\n\n"
        "请输出新的基因正文。"
    )
    choice = llm_router.pick_for_dept(dept)
    meta: dict[str, Any] = {"provider": choice.provider, "mode_id": mode_id, "dept": dept}
    if choice.provider != "litellm":
        stub = (
            f"{active_prompt.strip()}\n\n"
            f"【模拟进化·DSPy风格】结合样例「{sample[:120]}…」强调：可验证步骤、"
            "明确假设与边界、confidence/dissent 字段自洽；披露主要风险。"
        )
        meta["note"] = "simulated_provider_stub"
        return stub.strip()[:4000], meta

    fb = llm_router.fallbacks()
    resp = await litellm_client.complete(
        model=choice.model,
        prompt=user,
        fallbacks=[m for m in fb if m != choice.model],
        system=_EVOLVE_SYSTEM,
    )
    text = (resp.text or "").strip()
    if text.startswith("[litellm failed]") or text.startswith("[simulated]"):
        meta["degraded"] = True
        text = (
            f"{active_prompt.strip()}\n\n"
            f"【进化回退】LLM 不可用，保留原基因并附加样例对齐：{sample[:200]}"
        ).strip()[:4000]
    meta["raw_note"] = "litellm"
    return text[:4000], meta
