"""v4-B 4 档分级 + 类型识别 (替换 v3-A 二档).
Haiku-style cheap triage. Used by POST /api/decision/estimate.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class TriageResult:
    difficulty: int    # 1=轻 / 2=中 / 3=重 / 4=极重
    type: str          # office | decision | coding | intel | mixed
    confidence: float
    reason: str
    suggested_frameworks: list[str]


def triage(task: str) -> TriageResult:
    text = (task or "").strip()
    n = len(text)
    kw = text.lower()

    # type detection
    if any(k in kw for k in ["ppt", "excel", "word", "pdf", "邮件", "截图", "翻译", "总结", "上传", "导出"]):
        ttype = "office"
    elif any(k in kw for k in ["爬", "trending", "新闻", "arxiv", "热搜"]):
        ttype = "intel"
    elif any(k in kw for k in ["写代码", "重构", "bug", "实现", "function", "class ", "import ", "fastapi", "react"]):
        ttype = "coding"
    elif any(k in kw for k in ["选哪个", "怎么报价", "下半年", "战略", "规划", "决策"]):
        ttype = "decision"
    else:
        ttype = "decision"

    # difficulty
    if ttype == "office" and n < 60:
        diff = 1
    elif n < 30:
        diff = 1
    elif n < 120:
        diff = 2
    elif n < 300:
        diff = 3
    else:
        diff = 4

    # framework hints
    sf: list[str] = []
    if ttype == "decision":
        if diff >= 3: sf = ["first_principles", "inversion", "pre_mortem"]
        if diff == 4: sf += ["triz", "constraint_flip"]
    return TriageResult(
        difficulty=diff,
        type=ttype,
        confidence=0.65,
        reason=f"{ttype}/{n} chars",
        suggested_frameworks=sf,
    )