"""L0 搜索策略进化 — 探针 scraper providers 的成功率, 给出 prefer/fallback/deprecate 建议."""
from __future__ import annotations
import os
import httpx
from collections import defaultdict
from ._utils import append_log

SCRAPER_URL = os.environ.get("BEE_SCRAPER_URL", "http://127.0.0.1:8003")
TOKEN = os.environ.get("BEE_BEARER_TOKEN", "dev-token-change-me")
SAMPLE_QUERIES = ["LLM agent 2026", "vector database benchmark"]


def run() -> dict:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{SCRAPER_URL}/scraper/sites", headers=headers)
        if r.status_code != 200:
            return {"evolver": "p10_search_evolve", "status": "scraper_unavailable",
                    "summary": f"bee-scraper 返 HTTP {r.status_code}"}
        info = r.json()
    except Exception as e:
        return {"evolver": "p10_search_evolve", "status": "scraper_error",
                "summary": f"{e!r}"}

    impl = info.get("search_implemented") or []
    stub = info.get("search_stub") or []

    provider_stats: dict[str, dict] = defaultdict(lambda: {"ok": 0, "fail": 0, "results": 0})
    for q in SAMPLE_QUERIES:
        for prov in impl[:3]:
            try:
                with httpx.Client(timeout=20) as c:
                    r = c.post(f"{SCRAPER_URL}/scraper/search/query",
                               json={"query": q, "providers": [prov]},
                               headers=headers)
                if r.status_code != 200:
                    provider_stats[prov]["fail"] += 1
                    continue
                d = r.json()
                if d.get("errors", {}).get(prov):
                    provider_stats[prov]["fail"] += 1
                else:
                    res = d.get("results", {}).get(prov) or []
                    provider_stats[prov]["ok"] += 1
                    provider_stats[prov]["results"] += len(res)
            except Exception:
                provider_stats[prov]["fail"] += 1

    recommendations = []
    for prov, st in provider_stats.items():
        total = st["ok"] + st["fail"]
        if total == 0:
            continue
        success_rate = st["ok"] / total
        avg_results = st["results"] / max(1, st["ok"])
        recommendations.append({
            "provider": prov, "success_rate": round(success_rate, 2),
            "avg_results": round(avg_results, 1),
            "verdict": ("prefer" if success_rate >= 0.8 and avg_results >= 3
                        else "fallback" if success_rate >= 0.5
                        else "deprecate"),
        })

    append_log("p10_search_evolve", {
        "implemented": impl, "stub": stub,
        "provider_stats": dict(provider_stats),
        "recommendations": recommendations,
    })
    return {
        "evolver": "p10_search_evolve", "status": "done",
        "providers_tested": len(provider_stats),
        "recommendations": recommendations,
        "summary": f"探针 {len(provider_stats)} provider, {sum(1 for r in recommendations if r['verdict']=='prefer')} 推荐",
    }
