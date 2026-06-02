"""prompt_optimizer — 轻量提示词优化器 (复用 gene_evolve 的 DSPy 式思路, 可换 DSPy).

把用户的大白话需求整理成结构化、无歧义的 SPEC, 供 Claude Code 准确执行。
只在每个开发任务"开头"跑一次(几秒), 不进运行时热路径, 不拖慢日常。
做成可替换接口: 将来想上 DSPy/PromptWizard, 只换本文件 optimize() 内部即可。
失败兜底: LLM 不可用时原样返回 raw, 绝不阻断。
"""

from __future__ import annotations

import os

_MODEL = os.environ.get("BEE_DEV_OPTIMIZER_MODEL", "deepseek/deepseek-chat")

_SYSTEM = (
    "你是资深需求分析师 + 提示词工程师。把用户的口语化需求整理成给 AI 编码助手执行的高质量 SPEC。"
    "要点: 目标一句话讲清; 列出明确的功能点/验收标准; 标出约束(技术栈/不可改动的部分);"
    "标出不确定处让执行者注意; 不要替用户拍板没说的需求(不臆造)。只输出整理后的 SPEC 正文, 不要寒暄。"
)


async def optimize(raw_request: str, *, context: str = "") -> str:
    """raw_request → 结构化 SPEC. context 可带项目背景(如 CLAUDE.md 摘要)。"""
    raw = (raw_request or "").strip()
    if not raw:
        return ""
    try:
        from ..llm.litellm_client import litellm_client
        prompt = (f"[项目背景]\n{context}\n\n" if context else "") + \
                 f"[用户原始需求]\n{raw}\n\n请整理成结构化 SPEC:"
        resp = await litellm_client.complete(model=_MODEL, fallbacks=[], prompt=prompt, system=_SYSTEM)
        out = (resp.text or "").strip()
        # 兜底: 模型异常/空/报错回原文
        if not out or out.startswith("[litellm") or out.startswith("[simulated"):
            return raw
        return out
    except Exception:
        return raw
