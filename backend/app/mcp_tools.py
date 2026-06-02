"""mcp_tools — v13 #1 MCP 工具注册表 + 配置 + 按场景白名单.

第①步(本文件): 管"装了哪些 MCP / 开了哪些 / 什么场景用 / 何时调用的说明 / Key/URL".
第②步(后续 mcp_client): 决策时按场景取启用的工具, 让模型挑选并真实调用, 把结果注入决策.

关键纪律(防"装多了变笨"):
- 每个工具带中文「何时调用」说明 (when), 模型据此判断要不要用.
- 每个工具有场景白名单 (scenes), 只在相关场景才放给模型; 通配 ["*"] = 所有场景.
- 单场景实际放给模型的工具数有上限 (MAX_TOOLS_PER_SCENE), 落在准确率甜区.

存 backend/data/mcp_config.json: {server_id: {"enabled":bool, "key":str, "url":str}}.
预置的 enabled/url 是默认值, 用户在配置页可覆盖; key 一律用户自己填 (脱敏返回).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAX_TOOLS_PER_SCENE = 5  # 单场景放给模型的工具上限 (准确率甜区)

# 9 个预置 MCP (用户选定: 1 股票 / 8 地图 / 9 天气 / 10 Airbnb / 16 Firecrawl / 23 GitHub / 25 Context7 / 37 PubMed / 49 Pipedream)
# url 给 best-effort 默认, 用户可在配置页改成自己拿到的真实端点; transport: http=填URL即可, stdio=需独立容器.
PRESETS: list[dict[str, Any]] = [
    {
        "id": "alpha_vantage", "name": "Alpha Vantage · 股票数据", "category": "金融",
        "transport": "http", "url": "https://mcp.alphavantage.co/mcp", "needs_key": True, "default": True,
        "scenes": ["stock_trading", "family_finance", "insurance_planning", "tax_insurance"],
        "when": "涉及股票/ETF/期权/外汇/加密的实时价格、财报、技术指标、宏观数据时调用",
    },
    {
        "id": "weather", "name": "天气 · OpenWeather", "category": "实时",
        "transport": "http", "url": "", "needs_key": True, "default": True,
        "scenes": ["travel_planning", "travel_deep", "event_planning", "wedding_planning", "agriculture", "gardening"],
        "when": "需要某地实时天气/未来几天预报时调用 (旅行/活动/穿衣/农事)",
    },
    {
        "id": "firecrawl", "name": "Firecrawl · 网站抓取", "category": "抓取",
        "transport": "http", "url": "https://mcp.firecrawl.dev", "needs_key": True, "default": True,
        "scenes": ["*"],
        "when": "需要把某个网页/网站抓成干净结构化内容时调用 (读全文/比价/抓动态站)",
    },
    {
        "id": "github", "name": "GitHub", "category": "开发",
        "transport": "http", "url": "https://api.githubcopilot.com/mcp/", "needs_key": True, "default": True,
        "scenes": ["program_management", "data_analytics", "prompt_engineering"],
        "when": "涉及代码/开源项目时调用: 查仓库 star/活跃度/PR/issue、搜代码、评估项目权重",
    },
    {
        "id": "context7", "name": "Context7 · 最新文档", "category": "开发",
        "transport": "http", "url": "https://mcp.context7.com/mcp", "needs_key": False, "default": True,
        "scenes": ["program_management", "data_analytics", "prompt_engineering"],
        "when": "写代码/用某个库或框架时调用, 拉取该库的最新官方文档与用法",
    },
    {
        "id": "pubmed", "name": "PubMed · 医学文献", "category": "健康",
        "transport": "http", "url": "", "needs_key": False, "default": True,
        "scenes": ["family_doctor", "chronic_disease", "health_checkup", "nutrition_fitness", "elder_care", "mental_wellness"],
        "when": "健康/医疗问题需要循证依据时调用, 检索权威医学研究文献",
    },
    {
        "id": "osm", "name": "OpenStreetMap · 海外地图/路线", "category": "地图",
        "transport": "http", "url": "https://nominatim.openstreetmap.org", "needs_key": False, "default": True,
        "scenes": ["travel_planning", "travel_deep", "study_abroad"],
        "when": "海外地点/POI/路线/距离时调用 (免费免key免卡; 国内默认走高德)",
    },
    {
        "id": "airbnb", "name": "Airbnb · 房源", "category": "出行",
        "transport": "stdio", "url": "", "needs_key": False, "default": False,
        "scenes": ["travel_planning", "travel_deep"],
        "when": "需要查民宿/短租房源与价格时调用",
    },
    {
        "id": "pipedream", "name": "Pipedream · 万能连接器(2500+App)", "category": "聚合",
        "transport": "http", "url": "https://remote.mcp.pipedream.net", "needs_key": True, "default": False,
        "scenes": [],  # 默认不进任何场景白名单 (工具爆炸, 用户要用时手动指定 App)
        "when": "需要把结论落地到 Notion/Google日历/表格/邮件 等外部 App 时, 单独开启指定 App 后调用",
    },
]
_PRESET_BY_ID = {p["id"]: p for p in PRESETS}


def _config_path() -> Path:
    p = Path(__file__).resolve().parent.parent / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p / "mcp_config.json"


def _load_config() -> dict[str, dict[str, Any]]:
    p = _config_path()
    if not p.is_file():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_config(cfg: dict[str, dict[str, Any]]) -> None:
    try:
        _config_path().write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _mask(v: str) -> str:
    v = v or ""
    return ("***" + v[-4:]) if len(v) > 4 else ("***" if v else "")


def is_enabled(server_id: str) -> bool:
    cfg = _load_config().get(server_id, {})
    if "enabled" in cfg:
        return bool(cfg["enabled"])
    return bool(_PRESET_BY_ID.get(server_id, {}).get("default", False))


def server_runtime(server_id: str) -> dict[str, Any]:
    """合并预置 + 用户配置, 返回真正用于调用的 url/key (key 不脱敏, 内部用)."""
    preset = dict(_PRESET_BY_ID.get(server_id, {}))
    cfg = _load_config().get(server_id, {})
    preset["url"] = (cfg.get("url") or preset.get("url") or "").strip()
    preset["key"] = (cfg.get("key") or "").strip()
    preset["enabled"] = is_enabled(server_id)
    return preset


def public_list() -> list[dict[str, Any]]:
    """给前端配置页: 预置 + 当前开关/url, key 脱敏."""
    cfg = _load_config()
    out = []
    for p in PRESETS:
        c = cfg.get(p["id"], {})
        out.append({
            "id": p["id"], "name": p["name"], "category": p["category"],
            "transport": p["transport"], "scenes": p["scenes"], "when": p["when"],
            "needs_key": p["needs_key"],
            "enabled": is_enabled(p["id"]),
            "url": (c.get("url") or p.get("url") or ""),
            "key_set": bool(c.get("key")),
            "key_masked": _mask(c.get("key", "")),
        })
    return out


def update_config(server_id: str, *, enabled: bool | None = None,
                  key: str | None = None, url: str | None = None) -> bool:
    if server_id not in _PRESET_BY_ID:
        return False
    cfg = _load_config()
    entry = dict(cfg.get(server_id, {}))
    if enabled is not None:
        entry["enabled"] = bool(enabled)
    if url is not None:
        entry["url"] = url.strip()
    # key: 传 "***xxxx" 表示保持不变; 空串=清除; 其它=更新
    if key is not None and not key.startswith("***"):
        if key.strip():
            entry["key"] = key.strip()
        else:
            entry.pop("key", None)
    cfg[server_id] = entry
    _save_config(cfg)
    return True


def tools_for_scene(mode_id: str) -> list[dict[str, Any]]:
    """决策时(第②步)用: 该场景下已启用且配置完整的工具, 截到上限. key 不脱敏."""
    picked: list[dict[str, Any]] = []
    for p in PRESETS:
        if not is_enabled(p["id"]):
            continue
        scenes = p.get("scenes") or []
        if "*" not in scenes and mode_id not in scenes:
            continue
        rt = server_runtime(p["id"])
        if p["needs_key"] and not rt.get("key"):
            continue  # 需要 Key 但没填 → 跳过
        if p["transport"] == "http" and not rt.get("url"):
            continue
        picked.append(rt)
        if len(picked) >= MAX_TOOLS_PER_SCENE:
            break
    return picked
