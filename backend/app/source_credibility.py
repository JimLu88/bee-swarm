"""source_credibility — 按场景给聚合资料做「信源可信度 + 观点权重」分析.

在 media_aggregator 的通用「选源 + 域名权威度 + 质检」之上, 再叠一层"场景智能":
- 评分对比型 (美食/旅行/购物/营养): 抽各平台数字评分 → 归一 5 分 → 跨平台对比, 标一致/分歧 + 人均.
- 代码权威型 (写程序): 抽 GitHub stars/forks/活跃度 + Stack Overflow 采纳/票数 → 仓库权重.
- 观点共识型 (股票/法律/税保/创业): 判断每条立场 + 持同观点条数 + 按信源权威加权 → 多数派观点.
- 通用/专业证据型 (其余前台场景): 权威机构/专家/有出处优先, 软文降权.

产出:
- 给每张 media_card 加 `credibility` (0-100) + 可选 `cred_note` (短理由), 并按可信度重排.
- 返回 `consensus` = {"headline": 一句话, "summary": 短总结} 给前端数据墙 + CEO 上下文.

完全 best-effort: 任何异常 / 关闭开关 / 非前台场景 → 原样返回 cards, consensus={}. 绝不拖垮决策主链路.
env BEE_CREDIBILITY=0 可整体关闭. 先只覆盖 12 个前台场景 (见 CREDIBILITY_PROFILE).
调用方: decision_engine.py (finalize, gather_media_cards 之后).
"""

from __future__ import annotations

import os
from typing import Any

# 用最便宜的快模型做抽取 (与 media_aggregator 质检同款, 控成本).
_CRED_MODEL = "openai/deepseek-v4-flash"

# 场景 → 可信度画像. 已铺全部场景; 未列出的场景默认走 "evidence" (通用专业证据型).
CREDIBILITY_PROFILE: dict[str, str] = {
    # ---- 评分对比型: 地点/商品/服务有跨平台数字评分/口碑/价格 ----
    "dining_recommendation": "rating_compare",
    "travel_planning": "rating_compare",
    "travel_deep": "rating_compare",
    "purchase_decision": "rating_compare",
    "nutrition_fitness": "rating_compare",
    "cooking_recipe": "rating_compare",
    "skincare_beauty": "rating_compare",
    "fashion_styling": "rating_compare",
    "home_renovation": "rating_compare",
    "board_game": "rating_compare",
    "photography": "rating_compare",
    "car_purchase": "rating_compare",
    "wedding_planning": "rating_compare",
    "collectibles": "rating_compare",
    "gift_selection": "rating_compare",
    "pet_care": "rating_compare",
    # ---- 代码权威型: GitHub stars/forks + Stack Overflow ----
    "program_management": "repo_authority",
    "data_analytics": "repo_authority",
    "prompt_engineering": "repo_authority",
    # ---- 观点共识型: 立场分歧 + 谁的话更有分量 + 多数派 ----
    "stock_trading": "opinion_consensus",
    "legal_consulting": "opinion_consensus",
    "tax_insurance": "opinion_consensus",
    "startup_advisory": "opinion_consensus",
    "ip_patent": "opinion_consensus",
    "product_manager": "opinion_consensus",
    "seo_growth": "opinion_consensus",
    "contract_review": "opinion_consensus",
    "ecommerce_ops": "opinion_consensus",
    "cross_border": "opinion_consensus",
    "career_transition": "opinion_consensus",
    "debate_speech": "opinion_consensus",
    "dispute_rights": "opinion_consensus",
    "family_finance": "opinion_consensus",
    "insurance_planning": "opinion_consensus",
    "private_domain": "opinion_consensus",
    "rent_buy_house": "opinion_consensus",
    "resume_interview": "opinion_consensus",
    # ---- 专业证据型: 权威机构/专家共识/有出处优先 (健康/教育/方法) ----
    "family_doctor": "evidence",
    "learning_planning": "evidence",
    "child_education": "evidence",
    "generic_consulting": "evidence",
    "short_video": "evidence",
    "study_abroad": "evidence",
    "music_learning": "evidence",
    "gardening": "evidence",
    "ui_ux_review": "evidence",
    "agriculture": "evidence",
    "chronic_disease": "evidence",
    "digital_office": "evidence",
    "elder_care": "evidence",
    "fitness_plan": "evidence",
    "grad_civil_exam": "evidence",
    "health_checkup": "evidence",
    "home_organize": "evidence",
    "language_learning": "evidence",
    "mental_wellness": "evidence",
    "parenting_baby": "evidence",
    "presentation_skills": "evidence",
    "sleep_health": "evidence",
    "time_productivity": "evidence",
    "writing_polish": "evidence",
}

_PROFILE_INSTRUCTION: dict[str, str] = {
    "rating_compare": (
        "场景=本地生活/商品推荐。重点: 抽取每条提到的评分(大众点评/小红书/高德/豆瓣等, 统一归到5分制)"
        "与人均价格, 跨平台对比。headline 标注'均分X.X★, 各平台一致/有分歧'; summary 点出最值得信的"
        "选择和分歧点。真实点评/有人均有地址的可信度高, 纯种草软文降权。"
    ),
    "repo_authority": (
        "场景=技术/写程序。重点: 抽取 GitHub 仓库的 stars/forks/最近更新, Stack Overflow 采纳答案/票数。"
        "星多、活跃、被采纳的权威度高; 久不维护或无人问津的降权。headline 标注最权威的项目/答案; "
        "summary 点出该选哪个、是否还在维护。"
    ),
    "opinion_consensus": (
        "场景=投资/法律/税保/创业, 观点常有分歧。重点: 判断每条作者的立场(如 看多/看空/中性, 或 支持/反对), "
        "统计持各立场的条数, 并按来源权威(雪球/专业机构>个人)加权。headline 标注'多数派观点(如 看多 7:3, 高权威偏空)'; "
        "summary 点出高权威来源怎么看、主要分歧在哪。切忌被散户情绪带偏。"
    ),
    "evidence": (
        "场景=健康/教育/学习, 重证据。重点: 优先采信权威机构/专家共识/有出处研究的内容, "
        "给个人经验贴、营销软文、无出处臆测降权。headline 标注整体信源可靠度; summary 点出最该信的来源与理由。"
    ),
}

_MAX_ITEMS = 24  # 送进模型的卡片上限, 控 token


def profile_for(mode_id: str) -> str | None:
    return CREDIBILITY_PROFILE.get(mode_id)


def _build_prompt(task: str, profile: str, cards: list[dict[str, Any]]) -> str:
    lines = []
    for i, c in enumerate(cards[:_MAX_ITEMS]):
        src = str(c.get("source") or "")
        title = str(c.get("title") or "")[:60]
        body = str(c.get("body") or "")[:90]
        dom = ""
        url = str(c.get("url") or "")
        if url:
            from urllib.parse import urlparse

            try:
                dom = urlparse(url).netloc.lower().replace("www.", "")
            except Exception:
                dom = ""
        lines.append(f"{i}|{src or dom}|{title} {body}".strip())
    instr = _PROFILE_INSTRUCTION.get(profile, _PROFILE_INSTRUCTION["evidence"])
    return (
        f'你是「信源可信度分析师」。下面是为「{(task or "")[:120]}」聚合的资料 (序号|来源|标题+摘要):\n'
        f"{instr}\n"
        "请为每条给一个可信度 cred (0-100, 综合来源权威度/信息具体度/相关度), 并给整体 consensus。\n"
        "严格只输出 JSON, 不要解释或代码块:\n"
        '{"items":[{"i":序号,"cred":0-100,"note":"≤15字理由"}],'
        '"consensus":{"headline":"≤20字","summary":"≤60字"}}\n\n'
        + "\n".join(lines)
    )


async def analyze_credibility(task: str, mode_id: str, cards: list[dict[str, Any]]) -> dict[str, Any]:
    """给 cards 打 credibility 分 + 汇总 consensus. best-effort: 失败/非前台场景 → 原样返回."""
    if os.environ.get("BEE_CREDIBILITY", "1") == "0":
        return {"cards": cards, "consensus": {}}
    # 未明确归类的场景 → 走通用"专业证据"画像 (全场景覆盖, 不再跳过)
    profile = CREDIBILITY_PROFILE.get(mode_id) or "evidence"
    if not cards or len(cards) < 3:
        return {"cards": cards, "consensus": {}}
    try:
        from .llm.litellm_client import litellm_client
        from .llm.parsing import _extract_json

        prompt = _build_prompt(task, profile, cards)
        resp = await litellm_client.complete(
            model=_CRED_MODEL,
            prompt=prompt,
            system="你只输出严格 JSON, 不要解释或 markdown 代码块。",
        )
        obj = _extract_json(resp.text or "") or {}
        if not isinstance(obj, dict):
            return {"cards": cards, "consensus": {}}
        by_i: dict[int, dict] = {}
        for x in obj.get("items") or []:
            if isinstance(x, dict) and str(x.get("i", "")).strip().lstrip("-").isdigit():
                by_i[int(x["i"])] = x
        for i, c in enumerate(cards):
            x = by_i.get(i)
            if not x:
                continue
            try:
                cred = int(float(x.get("cred", 0)))
            except Exception:
                continue
            c["credibility"] = max(0, min(100, cred))
            note = str(x.get("note") or "").strip()
            if note:
                c["cred_note"] = note[:30]
        # 按可信度重排 (未评分的按中位 50 处理, 不至于被埋到最底)
        cards.sort(key=lambda c: -(c.get("credibility") if c.get("credibility") is not None else 50))
        consensus = obj.get("consensus")
        if not isinstance(consensus, dict):
            consensus = {}
        return {"cards": cards, "consensus": consensus}
    except Exception:
        return {"cards": cards, "consensus": {}}
