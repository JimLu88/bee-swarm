from __future__ import annotations

from .models import DeptName, ModeInfo


MODES: dict[str, ModeInfo] = {
    "program_management": ModeInfo(
        mode_id="program_management",
        label="程序管理设计",
        departments=["arch", "logic", "ui", "database", "benchmark", "xlab"],
        department_labels={
            "arch": "架构部",
            "logic": "逻辑部",
            "ui": "UI部",
            "database": "数据库部",
            "benchmark": "外部对标部",
            "xlab": "破局思考部",
        },
    ),
    "family_doctor": ModeInfo(
        mode_id="family_doctor",
        label="家庭医生助手",
        departments=["symptom", "nutrition", "drug_interactions", "psych", "security", "benchmark", "xlab"],
        department_labels={
            "symptom": "症状分析部",
            "nutrition": "营养部",
            "drug_interactions": "药物相互作用部",
            "psych": "心理辅导部",
            "security": "安全/合规部",
            "benchmark": "外部对标部",
            "xlab": "破局思考部",
        },
    ),
    "stock_trading": ModeInfo(
        mode_id="stock_trading",
        label="股票交易助手",
        departments=["macro_policy", "financial_reports", "technical_indicators", "smart_money", "security", "benchmark", "xlab"],
        department_labels={
            "macro_policy": "宏观政策部",
            "financial_reports": "财务报表部",
            "technical_indicators": "技术指标分析部",
            "smart_money": "主力资金监控部",
            "security": "安全/合规部",
            "benchmark": "外部对标部",
            "xlab": "破局思考部",
        },
    ),
    "travel_planning": ModeInfo(
        mode_id="travel_planning",
        label="旅行计划管理",
        departments=["visa", "flight_value", "local_safety", "culture_taboos", "security", "benchmark", "xlab"],
        department_labels={
            "visa": "签证部",
            "flight_value": "航空性价比部",
            "local_safety": "当地安全部",
            "culture_taboos": "文化禁忌部",
            "security": "安全/合规部",
            "benchmark": "外部对标部",
            "xlab": "破局思考部",
        },
    ),
}


def get_mode(mode_id: str) -> ModeInfo:
    return MODES.get(mode_id) or MODES["program_management"]


def list_modes() -> list[ModeInfo]:
    return list(MODES.values())

