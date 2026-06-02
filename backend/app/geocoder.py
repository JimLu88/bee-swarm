"""geocoder — 把决策结果里的店铺/地点名 → 经纬度 (高德 Web 服务 API), 给情报站「地图钉店」(方案4).

流程:
  (1) 轻量 LLM (flash) 从 CEO 结论 + 媒体卡标题里抽 [{name, city}] (最多 _MAX_PLACES 个);
  (2) 高德 /v3/geocode/geo 逐个地理编码 → {name, lng, lat, address, city}.

设计原则:
- 仅对「带地点」场景启用 (GEO_SCENES: 餐饮/旅行/租房等), 其余场景直接返回 [].
- best-effort: 无 AMAP_KEY / 无网 / 抽取失败 / 高德报错 → 返回 [], 绝不抛异常拖垮决策主链路.
- AMAP_KEY 只从 settings (env / .env) 读, 绝不写进代码或日志.
- 内存缓存 (name|city → coord) 避免重复调用, 省额度.
- env BEE_MAP_PINS=0 可整体关闭.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

# 「带地点」场景白名单: 只有这些场景的结果才值得在地图上钉店.
GEO_SCENES: set[str] = {
    # 出行/居住/活动
    "dining_recommendation",
    "travel_planning",
    "travel_deep",
    "rent_buy_house",
    "event_planning",
    "wedding_planning",
    "home_renovation",
    "gardening",
    "car_purchase",
    "study_abroad",
    # 医疗/养老 (医院/诊所/机构)
    "family_doctor",
    "chronic_disease",
    "health_checkup",
    "elder_care",
    "mental_wellness",
    # 教育/培训 (学校/机构/琴行)
    "child_education",
    "music_learning",
    # 门店/线下消费 (实体店/影楼/宠物医院)
    "purchase_decision",
    "nutrition_fitness",
    "fitness_plan",
    "skincare_beauty",
    "fashion_styling",
    "photography",
    "pet_care",
    "collectibles",
    "gift_selection",
}

# 用 POI 文本搜索 (/v3/place/text) 而非地理编码 (/v3/geocode/geo):
# 后者只认结构化街道地址, 对「海底捞(国贸店)」这类店名/POI 名会报 ENGINE_RESPONSE_DATA_ERROR.
_AMAP_POI_URL = "https://restapi.amap.com/v3/place/text"
_EXTRACT_MODEL = "openai/deepseek-v4-flash"  # 最便宜的快模型做抽取
_MAX_PLACES = 12
_GEOCODE_TIMEOUT = 8.0

# 内存缓存: "店名|城市" → {lng,lat,address,city} (或 None 表示查不到)
_cache: dict[str, dict[str, Any] | None] = {}


def _amap_key() -> str:
    """只从 settings (env/.env) 读高德 Key; 兜底直接读环境变量."""
    try:
        from .settings import settings
        k = (settings.amap_key or "").strip()
        if k:
            return k
    except Exception:
        pass
    return os.environ.get("AMAP_KEY", "").strip()


_EXTRACT_PROMPT = (
    "你是地点抽取器。从下面的「决策结论」和「相关资料标题」中, 找出所有被【推荐/提到】的"
    "**真实店铺、餐厅、景点、小区、商场或具体地点名称**。\n"
    "规则:\n"
    "- 只要真实可定位的地点名, 忽略泛指 (如「附近的火锅店」「某商场」) 和非地点词。\n"
    "- 尽量判断每个地点所在【城市】(从上下文推断, 拿不准就留空字符串)。\n"
    f"- 最多 {_MAX_PLACES} 个, 去重。\n"
    '- 严格只输出 JSON, 形如: {"places":[{"name":"海底捞(国贸店)","city":"北京"}, ...]}。\n'
    '- 如果没有任何可定位地点, 输出 {"places":[]}。\n\n'
    "【决策结论】\n{ceo}\n\n【相关资料标题】\n{titles}\n"
)


async def _extract_places(ceo_text: str, card_titles: list[str]) -> list[dict[str, str]]:
    """用 flash LLM 抽 [{name, city}]. 失败返回 []."""
    ceo = (ceo_text or "").strip()[:4000]
    titles = "\n".join(f"- {t}" for t in card_titles if t)[:1500] or "(无)"
    if not ceo and titles == "(无)":
        return []
    prompt = _EXTRACT_PROMPT.replace("{ceo}", ceo or "(无)").replace("{titles}", titles)
    try:
        from .llm.litellm_client import litellm_client
        from .llm.parsing import _extract_json
        resp = await litellm_client.complete(
            model=_EXTRACT_MODEL,
            prompt=prompt,
            system="你只输出严格 JSON, 不要任何解释或 markdown 代码块标记。",
        )
        obj = _extract_json(resp.text or "") or {}
    except Exception:
        return []
    raw = obj.get("places") if isinstance(obj, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for p in raw:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "").strip()
        city = str(p.get("city") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "city": city})
        if len(out) >= _MAX_PLACES:
            break
    return out


def _amap_str(v: Any) -> str:
    """高德某些字段无值时返回 [] (空列表), 统一成字符串."""
    if isinstance(v, list):
        return ""
    return str(v or "")


async def _geocode_one(client: httpx.AsyncClient, key: str, name: str, city: str) -> dict[str, Any] | None:
    """单个店名/地点 → 坐标 (POI 文本搜索, 取最相关一条). 命中缓存直接返回. 查不到/出错返回 None."""
    ck = f"{name}|{city}"
    if ck in _cache:
        cached = _cache[ck]
        return {**cached, "name": name} if cached else None
    params: dict[str, Any] = {
        "key": key, "keywords": name, "offset": 1, "page": 1,
        "extensions": "all",  # 带 biz_ext: 评分(rating) / 人均(cost)
        "output": "JSON",
    }
    if city:
        params["city"] = city
        params["citylimit"] = "true"  # 限定城市内, 避免同名跨城误命中
    try:
        r = await client.get(_AMAP_POI_URL, params=params)
        data = r.json()
    except Exception:
        _cache[ck] = None
        return None
    if str(data.get("status")) != "1":
        _cache[ck] = None
        return None
    pois = data.get("pois") or []
    if not pois:
        _cache[ck] = None
        return None
    p0 = pois[0]
    loc = _amap_str(p0.get("location"))  # 高德格式: "经度,纬度"
    if "," not in loc:
        _cache[ck] = None
        return None
    try:
        lng_s, lat_s = loc.split(",", 1)
        lng, lat = float(lng_s), float(lat_s)
    except Exception:
        _cache[ck] = None
        return None
    # biz_ext: 评分 rating(0-5) / 人均 cost(元). 部分 POI 无值 → 空字符串.
    biz = p0.get("biz_ext") if isinstance(p0.get("biz_ext"), dict) else {}
    rating_s = _amap_str(biz.get("rating"))
    cost_s = _amap_str(biz.get("cost"))
    try:
        rating = round(float(rating_s), 1) if rating_s else None
    except Exception:
        rating = None
    try:
        cost = round(float(cost_s)) if cost_s else None
    except Exception:
        cost = None
    # type 形如 "餐饮服务;中餐厅;火锅店" → 取最细一级做品类标签
    cat_parts = [s for s in _amap_str(p0.get("type")).split(";") if s]
    category = cat_parts[-1] if cat_parts else ""

    rec: dict[str, Any] = {
        "lng": lng,
        "lat": lat,
        "address": _amap_str(p0.get("address")) or _amap_str(p0.get("name")) or name,
        "city": _amap_str(p0.get("cityname")) or city,
        "poi_name": _amap_str(p0.get("name")) or name,  # 高德返回的规范店名
        "rating": rating,      # 评分 0-5 (无则 None)
        "cost": cost,          # 人均 ¥ (无则 None)
        "category": category,  # 品类标签 (如 "火锅店")
        "tel": _amap_str(p0.get("tel")).split(";")[0],
    }
    _cache[ck] = rec
    return {**rec, "name": name}


async def gather_map_places(
    *, mode_id: str, ceo_text: str, media_cards: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """决策 finalize 时调用: 抽地点 → 高德地理编码 → 返回可钉地图的坐标列表.

    best-effort: 非地点场景 / 无 Key / 关闭开关 → []. 任何异常吞掉返回已得部分.
    """
    if os.environ.get("BEE_MAP_PINS", "1") == "0":
        return []
    if mode_id not in GEO_SCENES:
        return []
    key = _amap_key()
    if not key:
        return []
    try:
        titles = [str(c.get("title") or "").strip() for c in (media_cards or []) if c.get("title")]
        places = await _extract_places(ceo_text, titles)
        if not places:
            return []
        async with httpx.AsyncClient(timeout=_GEOCODE_TIMEOUT) as client:
            results = await asyncio.gather(
                *[_geocode_one(client, key, p["name"], p["city"]) for p in places],
                return_exceptions=True,
            )
        out: list[dict[str, Any]] = []
        for r in results:
            if isinstance(r, dict):
                out.append(r)
        return out
    except Exception:
        return []
