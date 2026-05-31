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

MAX_CARDS = 12

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

    # 2) 场景垂直平台 (每个少量, 控制总耗时)
    platforms = SCENE_PLATFORMS.get(mode_id, _DEFAULT_PLATFORMS)
    per = 4
    for plat in platforms[:4]:
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

    # 归一 + 去重 (按 url) + 优先带图 + 限量
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        card = _classify(item)
        if not card:
            continue
        key = card.get("url") or card.get("title") or ""
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        cards.append(card)

    # 带图/视频的排前面 (信息流更好看), 再截断
    cards.sort(key=lambda c: 0 if c.get("type") in ("image", "video") else 1)
    return cards[:MAX_CARDS]


async def gather_media_cards(task: str, mode_id: str) -> list[dict[str, Any]]:
    """决策 finalize 时调用: 聚合相关图文/视频/链接给前端信息流.

    完全 best-effort: 关闭开关 / 无网络 / 爬虫服务没起 → 返回 []. 绝不抛异常.
    """
    if os.environ.get("BEE_MEDIA_FEED", "1") == "0":
        return []
    try:
        return await asyncio.to_thread(_collect_sync, task, mode_id)
    except Exception:
        return []
