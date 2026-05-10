from __future__ import annotations

from typing import Any

# Minimal keyword hints per dept bucket (expand per-mode later).
_DEPT_FOCUS: dict[str, list[str]] = {
    "finance": ["成本", "预算", "财务", "ROI", "现金流", "报价"],
    "security": ["安全", "合规", "隐私", "审计", "GDPR", "风险"],
    "business": ["商业", "客户", "市场", "变现", "增长"],
    "design": ["设计", "体验", "交互", "视觉", "UI", "品牌"],
    "efficiency": ["效率", "供应链", "流程", "自动化", "产能"],
    "benchmark": ["对标", "竞品", "行业", "开源", "框架", "案例"],
    "xlab": ["创新", "破局", "颠覆", "实验", "边界"],
    "arch": ["架构", "模块", "服务", "伸缩", "分层"],
    "logic": ["逻辑", "算法", "一致性", "边界条件"],
    "ui": ["界面", "组件", "前端", "可用性"],
    "database": ["数据库", "存储", "索引", "迁移", "一致性"],
    "symptom": ["症状", "体征", "病程"],
    "nutrition": ["营养", "膳食", "过敏原"],
    "drug_interactions": ["药物", "相互作用", "禁忌"],
    "psych": ["心理", "情绪", "睡眠", "压力"],
    "macro_policy": ["宏观", "政策", "利率", "通胀"],
    "financial_reports": ["财报", "营收", "负债", "现金流"],
    "technical_indicators": ["均线", "MACD", "技术指标", "量价"],
    "smart_money": ["主力", "资金流", "筹码"],
    "visa": ["签证", "入境", "停留"],
    "flight_value": ["航班", "票价", "转机"],
    "local_safety": ["治安", "安全", "紧急"],
    "culture_taboos": ["禁忌", "文化", "礼仪"],
}

_STRATEGIC_MARKERS = ("战略", "三年", "五年", "路线图", "roadmap", "愿景", "转型", "长期")


def classify_task(task: str) -> dict[str, Any]:
    t = task.strip()
    low = t.lower()
    strategic = len(t) >= 600 or any(m in t for m in _STRATEGIC_MARKERS) or "strategy" in low
    level = "strategic" if strategic else "tactical"
    urgency = "high" if any(x in t for x in ("紧急", "立刻", "今天", "urgent", "asap")) else "normal"
    return {"level": level, "urgency": urgency, "task_chars": len(t)}


def focus_hint(dept: str, task: str) -> str:
    keys = _DEPT_FOCUS.get(dept, [])
    hits = [k for k in keys if k in task]
    if hits:
        return f"任务中与 {dept} 相关的关键词：{', '.join(hits[:5])} —— 请优先围绕这些点给出结论。"
    return f"任务未命中 {dept} 关键词库；请从该部门职能视角做通用审查与落地建议。"


def dept_briefs(task: str, departments: list[str]) -> dict[str, str]:
    """Split context for each department: short focus + truncated full task."""
    summary = task.strip()
    if len(summary) > 500:
        summary = summary[:500] + "…"
    out: dict[str, str] = {}
    for d in departments:
        hint = focus_hint(d, task)
        out[d] = f"{hint}\n\n【完整任务摘录】\n{summary}"
    return out


def run_dispatcher(*, task: str, departments: list[str]) -> dict[str, Any]:
    """
    Preprocessor / triage (白皮书「预处理分诊官」骨架).
    Deterministic + keyword-assisted; replaceable by LLM later.
    """
    meta = classify_task(task)
    briefs = dept_briefs(task, departments)
    # lightweight diversity so parallel depts don't get identical first line when no keywords
    notes_parts = [
        f"分级：{meta['level']}（{'偏长期/架构型' if meta['level'] == 'strategic' else '偏执行/迭代型'}）",
        f"时效：{meta['urgency']}",
        f"已为 {len(departments)} 个部门生成独立上下文片段，降低互相干扰与 token 浪费。",
    ]
    return {
        **meta,
        "dept_briefs": briefs,
        "notes": " ".join(notes_parts),
        "version": "dispatcher_v1",
    }
