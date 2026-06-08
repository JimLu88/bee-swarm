"""skills_store — 读取 p3 蒸馏的可复用技能 (skills_registry.jsonl), 匹配当前任务注入决策.

p3_skill_breed.py 把高置信决策蒸馏成 SOP 写进 evolution_coordinator/data/skills_registry.jsonl;
本模块在 CEO 综合前把与任务相关的技能挑出来注入 prompt, 闭合"沉淀→复用"回路.
每条 skill: {skill_id, trigger, steps[], applies_to(mode_id 或 *), source_decision_id}.
无技能 / 文件缺失 / 解析失败 → 一律返回空 (静默降级, 不影响决策).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SKILLS_FILE = Path(__file__).resolve().parent / "evolution_coordinator" / "data" / "skills_registry.jsonl"

_STOPWORDS = set(
    "的 了 和 与 或 在 是 我 你 他 她 它 们 这 那 个 有 要 想 帮 请 一个 怎么 如何 什么 给 我们 需要".split()
)


def load_skills() -> list[dict[str, Any]]:
    """读全部技能; 文件不存在/损坏 → 空表. 同 skill_id 取最后一条 (后写覆盖)."""
    if not SKILLS_FILE.exists():
        return []
    by_id: dict[str, dict[str, Any]] = {}
    try:
        for line in SKILLS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("skill_id"):
                by_id[str(obj["skill_id"])] = obj
    except Exception:
        return []
    return list(by_id.values())


_CJK = r"一-鿿"


def _tokens(text: str) -> set[str]:
    """中文无词边界 → 用 CJK 字符 bigram + 拉丁/数字词 做匹配单元."""
    s = str(text).lower()
    toks: set[str] = set()
    # 拉丁/数字词 (>=2 字符, 去停用词)
    for w in re.findall(r"[a-z0-9]{2,}", s):
        if w not in _STOPWORDS:
            toks.add(w)
    # CJK: 每段连续汉字切相邻 2 字窗 (单字成段则取该字)
    for run in re.findall(rf"[{_CJK}]+", s):
        if len(run) == 1:
            toks.add(run)
        else:
            for i in range(len(run) - 1):
                toks.add(run[i:i + 2])
    return toks


def match_skills(task: str, mode_id: str = "", k: int = 3) -> list[dict[str, Any]]:
    """按 trigger 与任务的词重叠度挑相关技能; applies_to 过滤 (mode_id 或 *)."""
    skills = load_skills()
    if not skills:
        return []
    task_toks = _tokens(task)
    if not task_toks:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for s in skills:
        applies = str(s.get("applies_to", "*")).strip()
        if applies and applies != "*" and mode_id and applies != mode_id:
            continue
        trig_toks = _tokens(s.get("trigger", "")) | _tokens(s.get("skill_id", ""))
        overlap = task_toks & trig_toks
        if not overlap:
            continue
        score = len(overlap) / (len(trig_toks) ** 0.5 + 1e-6)
        scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:k]]


def format_skills_brief(skills: list[dict[str, Any]]) -> str:
    """拼成注入 CEO prompt 的简报; 空 → 空串."""
    if not skills:
        return ""
    lines = ["## 🧠 可复用历史技能 (从过往成功决策蒸馏的 SOP, 命中当前任务):"]
    for s in skills:
        steps = s.get("steps") or []
        steps_txt = "; ".join(str(x) for x in steps[:8]) if isinstance(steps, list) else str(steps)
        lines.append(f"- **{s.get('skill_id', '')}** (触发: {s.get('trigger', '')}): {steps_txt}")
    lines.append("（如与当前任务契合可借鉴这些步骤; 不契合则忽略。）")
    return "\n".join(lines)
