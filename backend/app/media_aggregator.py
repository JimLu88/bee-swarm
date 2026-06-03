"""media_aggregator — 把多平台爬虫结果聚合成前端信息流 media_cards.

背景: DecisionSummary.media_cards 字段早就声明了 (models.py), 前端 InfoFeed 也做了
(text/image/video/link 四种卡片 + 瀑布流 + lightbox), 但中间「去搜 → 填进 media_cards」
这段一直没写, 所以信息流永远空着. 本模块补上这段接线.

数据来源 (都走 bee-scraper 8003, 见 数据爬虫/app/platforms.py):
- web_search(query): tavily(含图)/brave → 通用图文
- scrape(platform, keyword): 26 个平台
    原生 API: reddit / wikipedia / bilibili / fourchan / stackexchange / youtube
    site: 限定 + og:image: 知乎/小红书/抖音/ins/tiktok/discord/quora/小黑盒/淘宝/京东/
          拼多多/豆瓣/pinterest/什么值得买/大众点评/马蜂窝/下厨房/微信/medium/微博

按「当前场景」选最相关的 2-4 个平台 (见 SCENE_PLATFORMS), 让信息流贴合专业领域.

设计原则:
- 完全 best-effort: 任何异常 → 返回已聚合的部分 (绝不拖垮决策主链路).
- env BEE_MEDIA_FEED=0 可整体关闭 (离线/省钱).
- 按 url 去重, 限 MAX_CARDS 条. 优先保留带图的卡.
- 同步 httpx 客户端放线程池, 不阻塞事件循环.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from urllib.parse import urlparse

MAX_CARDS = 60  # v14: 40→60 (大屏选择墙: 一屏铺 50-60 真候选供挑选)

# 场景 mode_id → 该领域最相关的爬取平台 (web_search 通用之外的垂直补充).
# 平台名必须是 数据爬虫/platforms.py 注册的 fetcher key.
SCENE_PLATFORMS: dict[str, list[str]] = {
    # ---- 13 内置 ----
    "program_management": ["github_trending", "stackexchange", "hacker_news", "reddit"],
    "family_doctor": ["wikipedia", "zhihu", "xiaohongshu"],
    "stock_trading": ["weibo", "zhihu", "xueqiu"],
    "travel_planning": ["mafengwo", "xiaohongshu", "douban", "bilibili"],
    "legal_consulting": ["zhihu", "wikipedia"],
    "startup_advisory": ["hacker_news", "github_trending", "zhihu", "medium"],
    "learning_planning": ["arxiv", "zhihu", "bilibili", "wikipedia"],
    "child_education": ["zhihu", "xiaohongshu", "bilibili"],
    "dining_recommendation": ["dianping", "xiaohongshu", "xiachufang"],
    "nutrition_fitness": ["xiaohongshu", "bilibili", "zhihu"],
    "purchase_decision": ["smzdm", "jd", "taobao", "zhihu", "bilibili"],
    "tax_insurance": ["zhihu", "wikipedia"],
    "generic_consulting": ["zhihu", "wikipedia", "reddit"],
    # ---- extra 高频 (其余走通用 web_search 兜底) ----
    "cooking_recipe": ["xiachufang", "xiaohongshu", "bilibili"],
    "skincare_beauty": ["xiaohongshu", "douban", "bilibili"],
    "fashion_styling": ["xiaohongshu", "pinterest", "instagram"],
    "home_renovation": ["xiaohongshu", "zhihu", "pinterest"],
    "pet_care": ["xiaohongshu", "zhihu", "bilibili"],
    "board_game": ["xiaoheihe", "bilibili", "reddit"],
    "short_video": ["douyin", "bilibili", "tiktok"],
    "photography": ["xiaohongshu", "pinterest", "instagram", "bilibili"],
    "car_purchase": ["smzdm", "zhihu", "bilibili", "douban"],
    "study_abroad": ["zhihu", "xiaohongshu", "reddit"],
    "music_learning": ["bilibili", "youtube", "zhihu"],
    "gardening": ["xiaohongshu", "xiachufang", "pinterest"],
    "wedding_planning": ["xiaohongshu", "pinterest", "douban"],
    "ip_patent": ["wikipedia", "zhihu"],
    "data_analytics": ["github_trending", "stackexchange", "medium", "zhihu"],
    "prompt_engineering": ["github_trending", "reddit", "medium", "hacker_news"],
    "product_manager": ["medium", "zhihu", "hacker_news"],
    "seo_growth": ["medium", "reddit", "zhihu"],
    "ui_ux_review": ["pinterest", "medium", "dribbble"],
    "contract_review": ["zhihu", "wikipedia"],
    "ecommerce_ops": ["zhihu", "smzdm", "taobao", "jd"],
    "cross_border": ["reddit", "zhihu", "medium"],
    "collectibles": ["xianyu", "douban", "xiaohongshu"],
    "gift_selection": ["xiaohongshu", "smzdm", "zhihu"],
    # ---- extra 其余 ----
    "agriculture": ["zhihu", "bilibili", "wikipedia"],
    "career_transition": ["zhihu", "medium", "reddit"],
    "chronic_disease": ["wikipedia", "zhihu", "xiaohongshu"],
    "debate_speech": ["zhihu", "bilibili", "youtube"],
    "digital_office": ["zhihu", "bilibili", "medium"],
    "dispute_rights": ["zhihu", "wikipedia"],
    "elder_care": ["zhihu", "xiaohongshu"],
    "event_planning": ["xiaohongshu", "pinterest", "zhihu"],
    "family_finance": ["zhihu", "xueqiu", "smzdm"],
    "fitness_plan": ["xiaohongshu", "bilibili", "zhihu"],
    "grad_civil_exam": ["zhihu", "bilibili"],
    "health_checkup": ["wikipedia", "zhihu"],
    "home_organize": ["xiaohongshu", "bilibili", "pinterest"],
    "insurance_planning": ["zhihu", "xueqiu"],
    "language_learning": ["bilibili", "youtube", "reddit", "zhihu"],
    "mental_wellness": ["zhihu", "xiaohongshu", "reddit"],
    "parenting_baby": ["xiaohongshu", "zhihu", "bilibili"],
    "presentation_skills": ["zhihu", "bilibili", "medium"],
    "private_domain": ["zhihu", "medium"],
    "rent_buy_house": ["zhihu", "douban", "xiaohongshu"],
    "resume_interview": ["zhihu", "medium", "reddit"],
    "sleep_health": ["wikipedia", "zhihu", "xiaohongshu"],
    "time_productivity": ["zhihu", "medium", "reddit"],
    "travel_deep": ["mafengwo", "xiaohongshu", "douban", "bilibili"],
    "writing_polish": ["zhihu", "medium"],
}

# 兜底: 没专属映射的场景用这几个通用源
_DEFAULT_PLATFORMS = ["zhihu", "wikipedia", "reddit"]

_VIDEO_DOMAINS = ("youtube.com", "youtu.be", "bilibili.com", "douyin.com", "tiktok.com", "v.qq.com", "vimeo.com")
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

# ---- 方向1: 域名黑名单 (内容农场 / SEO 站群 / AI 水文站, 命中即丢) ----
_DOMAIN_DENY: tuple[str, ...] = (
    "zhjsw.cn", "zhjsw.com",  # 用户实测企业站群, 全 AI 水文
)

# ---- 方向4: 来源权威度权重 (越高越靠前; 真实 UGC / 权威站加权) ----
_AUTHORITY: dict[str, int] = {
    # 高: 真实点评 / 高质 UGC / 权威百科
    "dianping.com": 3, "xiaohongshu.com": 3, "zhihu.com": 3, "mafengwo.cn": 3,
    "douban.com": 3, "wikipedia.org": 3, "xueqiu.com": 3,
    # 中: 社区 / 视频 / 电商 / 工具站
    "bilibili.com": 2, "xiachufang.com": 2, "weibo.com": 2, "smzdm.com": 2,
    "jd.com": 2, "taobao.com": 2, "reddit.com": 2, "stackexchange.com": 2,
    "github.com": 2, "medium.com": 2, "pinterest.com": 2,
}

# 方向5: 兜底 LLM 质检模型 (最便宜的快模型)
_QUALITY_MODEL = "openai/deepseek-v4-flash"
_QUALITY_PROMPT = (
    "你是内容质检员。下面是为「{task}」聚合的资料条目 (序号|来源|标题摘要)。\n"
    "请挑出**低质应丢弃**的条目序号: AI 水文/SEO 站群软文/纯广告/与任务无关/无信息量/标题党。\n"
    "保留: 真实点评、有具体信息(数字/地址/亲历)、权威或 UGC 优质内容。\n"
    '严格只输出 JSON: {"drop":[序号,...]}; 没有要丢的输出 {"drop":[]}。\n\n{items}\n'
)


def _is_denied(url: str) -> bool:
    """方向1: 命中黑名单域名 → True (直接丢)."""
    d = _domain(url)
    return any(bad in d for bad in _DOMAIN_DENY)


def _authority_score(url: str, source: str) -> int:
    """方向4: 来源权威度 0-3. 杂域查表; 平台 scrape 来源(非域名)给 2; 未知给 0."""
    d = _domain(url)
    for dom, w in _AUTHORITY.items():
        if dom in d:
            return w
    if source and "." not in source:  # source 是平台名 (垂直 scrape) → 中等可信
        return 2
    return 0


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _classify(item: dict[str, Any]) -> dict[str, Any]:
    """把一条平台结果归一成 MediaCard dict (前端 InfoFeed 的形状)."""
    title = str(item.get("title") or "").strip()
    url = str(item.get("url") or "").strip()
    snippet = str(item.get("snippet") or item.get("summary") or item.get("body")
                  or item.get("description") or "").strip()
    image_url = str(item.get("image_url") or item.get("cover") or item.get("thumbnail")
                    or item.get("pic") or "").strip()
    video_url = str(item.get("video_url") or "").strip()
    source = str(item.get("source") or "") or _domain(url)

    low = url.lower()
    # 视频: 有 video_url 或视频域名 → video 卡 (前端可点开)
    if video_url or any(d in low for d in _VIDEO_DOMAINS):
        return {"type": "video", "title": title or "视频", "url": video_url or url,
                "image_url": image_url, "source": source}
    # 图片: 有封面图 / 图片后缀 → image 卡
    if image_url or low.endswith(_IMAGE_EXTS):
        return {"type": "image", "title": title or "图片",
                "image_url": image_url or url, "url": url, "source": source}
    # 链接: 有 url → link 卡 (带摘要)
    if url:
        card: dict[str, Any] = {"type": "link", "title": title or url, "url": url, "source": source}
        if snippet:
            card["body"] = snippet[:240]
        return card
    # 纯文本
    if snippet or title:
        return {"type": "text", "title": title, "body": snippet[:240], "source": source}
    return {}


def _platforms_for(mode_id: str) -> list[str]:
    from .tools.seven_clients import bee_clients  # noqa: F401 (确保模块可用)
    return SCENE_PLATFORMS.get(mode_id, _DEFAULT_PLATFORMS)


def _collect_sync(task: str, mode_id: str) -> list[dict[str, Any]]:
    """同步收集 (在线程池里跑). 返回归一后的 media_cards."""
    from .tools.seven_clients import bee_clients, ToolCallError  # noqa: F401

    # 用任务首行前 80 字做查询词 (附件摘要太长会污染搜索)
    query = ""
    for line in (task or "").splitlines():
        s = line.strip()
        if s and not s.startswith("["):  # 跳过 [用户上传图片摘要] 这类标记行
            query = s[:80]
            break
    if not query:
        query = (task or "").strip()[:80]
    if not query:
        return []

    raw: list[dict[str, Any]] = []

    # 1) 通用 web 搜索 (tavily 带图)
    try:
        resp = bee_clients.web_search(query)
        results = resp.get("results") or {}
        if isinstance(results, dict):
            for _provider, items in results.items():
                if isinstance(items, list):
                    raw.extend(x for x in items if isinstance(x, dict))
    except Exception:
        pass

    # 2) 场景垂直平台 (每个少量, 控制总耗时). v14: 4→6 平台 × 4→6 条, 配合 MAX_CARDS=60 凑满选择墙
    platforms = SCENE_PLATFORMS.get(mode_id, _DEFAULT_PLATFORMS)
    per = 6
    for plat in platforms[:6]:
        try:
            resp = bee_clients.scrape(plat, keyword=query, limit=per)
            items = resp.get("items") or []
            if isinstance(items, list):
                for x in items:
                    if isinstance(x, dict):
                        x.setdefault("source", plat)
                        raw.append(x)
        except Exception:
            continue

    # 归一 + 去重 (按 url) + 黑名单过滤(方向1) + 权威度打分(方向4) + 限量
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        card = _classify(item)
        if not card:
            continue
        url = card.get("url") or ""
        if _is_denied(url):  # 方向1: 内容农场/站群 直接丢
            continue
        key = url or card.get("title") or ""
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        card["_q"] = _authority_score(url, str(card.get("source") or ""))  # 方向4
        cards.append(card)

    # 排序: 权威度高 + 带图 优先, 再截断 (_q 在 gather 末尾清掉)
    cards.sort(key=lambda c: (-(c.get("_q") or 0), 0 if c.get("type") in ("image", "video") else 1))
    return cards[:MAX_CARDS]


async def _llm_quality_gate(task: str, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """方向5: flash 一次性批量质检, 丢掉 AI 水文/广告/无关项. best-effort, 失败/误杀则原样返回."""
    if os.environ.get("BEE_MEDIA_QUALITY", "1") == "0" or len(cards) <= 6:
        return cards  # 条目太少不值得过滤
    try:
        from .llm.litellm_client import litellm_client
        from .llm.parsing import _extract_json
        lines = []
        for i, c in enumerate(cards):
            t = str(c.get("title") or "")[:60]
            b = str(c.get("body") or "")[:80]
            s = str(c.get("source") or "")
            lines.append(f"{i}|{s}|{t} {b}".strip())
        prompt = _QUALITY_PROMPT.replace("{task}", (task or "")[:120]).replace("{items}", "\n".join(lines))
        resp = await litellm_client.complete(
            model=_QUALITY_MODEL, prompt=prompt,
            system="你只输出严格 JSON, 不要解释或 markdown 代码块。",
        )
        obj = _extract_json(resp.text or "") or {}
        drop_raw = obj.get("drop") if isinstance(obj, dict) else None
        if not isinstance(drop_raw, list):
            return cards
        drop = {int(x) for x in drop_raw if str(x).isdigit()}
        kept = [c for i, c in enumerate(cards) if i not in drop]
        return kept or cards  # 全被丢 → 判为误杀, 保留原样
    except Exception:
        return cards


# v14: 同一批候选既喂给部门讨论(决策开始时), 又复用做 media_cards/大屏(finalize).
# 按 decision_id 缓存, 避免一次决策爬两遍 (并保证"部门读到的"=="瀑布展示的").
_CARD_CACHE: dict[str, list[dict[str, Any]]] = {}


def candidates_digest(cards: list[dict[str, Any]], limit: int = 30) -> str:
    """把候选压成给部门读的紧凑清单 (标题+来源+简介), 拼进 task 让所有部门+CEO 共享真实资料。"""
    if not cards:
        return ""
    lines: list[str] = []
    for i, c in enumerate(cards[:limit], 1):
        title = str(c.get("title") or "").strip()[:60]
        if not title:
            continue
        src = str(c.get("source") or "").strip()
        body = str(c.get("body") or c.get("desc") or "").strip()[:90]
        seg = f"{i}. {title}"
        if src:
            seg += f" [{src}]"
        if body:
            seg += f" — {body}"
        lines.append(seg)
    if not lines:
        return ""
    return ("[实时联网/爬虫候选 — 以下是刚抓到的真实资料/商品/案例/店铺, 讨论与给建议时请优先参考并引用真实项, "
            "不要凭空编造具体型号/店名/链接]\n" + "\n".join(lines))


async def gather_media_cards(task: str, mode_id: str, decision_id: str = "") -> list[dict[str, Any]]:
    """聚合相关图文/视频/链接. 决策开始时调一次(喂部门+缓存), finalize 再调直接命中缓存.

    完全 best-effort: 关闭开关 / 无网络 / 爬虫服务没起 → 返回 []. 绝不抛异常.
    """
    if decision_id and decision_id in _CARD_CACHE:
        return _CARD_CACHE[decision_id]
    if os.environ.get("BEE_MEDIA_FEED", "1") == "0":
        return []
    try:
        cards = await asyncio.to_thread(_collect_sync, task, mode_id)
        cards = await _llm_quality_gate(task, cards)  # 方向5: flash 兜底质检
    except Exception:
        return []
    for c in cards:  # 清掉内部排序字段, 不外泄给前端
        c.pop("_q", None)
    if decision_id:
        _CARD_CACHE[decision_id] = cards
        if len(_CARD_CACHE) > 100:  # 防泄漏: 超量清掉一半旧的
            for k in list(_CARD_CACHE)[:50]:
                _CARD_CACHE.pop(k, None)
    return cards
