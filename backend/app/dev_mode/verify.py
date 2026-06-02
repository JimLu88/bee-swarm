"""verify — 开发结果的"评审方"(生成-评审对抗里的 Evaluator).

对 claude 的改动 + 测试结果做独立 LLM 评审, 给 0-1 评分 + 问题列表。
(人类测试员 human_tester 是第三路验证, 在 M3 由 session 单独调; 本文件只管 LLM 评审。)
失败兜底: LLM 不可用 → 返回中性分 0.5 + 说明, 不阻断。
"""

from __future__ import annotations

import json
import os
from typing import Any

_MODEL = os.environ.get("BEE_DEV_REVIEW_MODEL", "deepseek/deepseek-chat")

_SYSTEM = (
    "你是严格的代码评审员。基于任务目标、改动概要、测试结果, 评估这次实现的质量。"
    "重点看: 是否真正满足需求、是否有明显 bug/遗漏、改动是否过大或跑题、测试是否真的覆盖。"
    '只输出 JSON: {"score":0到1的小数,"verdict":"pass|needs_work|fail","issues":["问题1","问题2"]}。'
    "score: 1=很好, 0.6+=可接受, <0.5=有明显问题。不要解释, 只要 JSON。"
)


def _parse(text: str) -> dict[str, Any]:
    s = (text or "").strip()
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1 or b < a:
        return {}
    try:
        d = json.loads(s[a:b + 1])
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


async def review(*, spec: str, code_output: str, test_result: dict[str, Any]) -> dict[str, Any]:
    """返回 {score:0-1, verdict, issues:[]}。"""
    tests_passed = bool(test_result.get("passed"))
    test_summary = str(test_result.get("summary", ""))[:2500]
    try:
        from ..llm.litellm_client import litellm_client
        prompt = (f"[任务目标]\n{spec[:2000]}\n\n"
                  f"[执行者的改动总结]\n{code_output[:3000]}\n\n"
                  f"[测试是否通过] {tests_passed}\n[测试输出]\n{test_summary}\n\n请评审并输出 JSON:")
        resp = await litellm_client.complete(model=_MODEL, fallbacks=[], prompt=prompt, system=_SYSTEM)
        d = _parse(resp.text)
    except Exception:
        d = {}
    if not d:
        # 兜底: 没评审到 → 用测试结果给个保守分
        return {"score": 0.6 if tests_passed else 0.3, "verdict": "pass" if tests_passed else "needs_work",
                "issues": ["LLM 评审不可用, 仅按测试结果估分"]}
    try:
        score = max(0.0, min(1.0, float(d.get("score", 0.5))))
    except Exception:
        score = 0.5
    verdict = str(d.get("verdict", "needs_work"))
    issues = [str(x)[:300] for x in (d.get("issues") or [])][:10]
    return {"score": round(score, 3), "verdict": verdict, "issues": issues}
