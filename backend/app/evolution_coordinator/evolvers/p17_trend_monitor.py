"""v6-G p17 趋势监控 — 每天扫 arxiv/HN/GitHub trending, 找新框架/技术, 入 pending_changes 待审."""
from __future__ import annotations
import os
import httpx
from ._utils import append_log, ask_cheap_llm, parse_json_loose

SCRAPER_URL = os.environ.get("BEE_SCRAPER_URL", "http://127.0.0.1:8003")
TOKEN = os.environ.get("BEE_BEARER_TOKEN", "dev-token-change-me")


def _fetch_trends() -> dict[str, list[dict]]:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    out: dict[str, list[dict]] = {}
    targets = [
        ("hacker_news", "", 10),
        ("github_trending", "stars:>500 created:>2026-01-01", 8),
        ("arxiv", "agent self-improvement", 5),
    ]
    for site, kw, lim in targets:
        try:
            with httpx.Client(timeout=30) as c:
                r = c.post(f"{SCRAPER_URL}/scraper/task",
                           json={"site": site, "keyword": kw, "limit": lim},
                           headers=headers)
            if r.status_code == 200:
                out[site] = r.json().get("items", [])
        except Exception:
            pass
    return out


def run() -> dict:
    import asyncio
    trends = _fetch_trends()
    total = sum(len(v) for v in trends.values())
    if total == 0:
        return {"evolver": "p17_trend_monitor", "status": "no_data",
                "summary": "未抓到趋势 (bee-scraper 可能未启)"}

    feed = []
    for site, items in trends.items():
        for it in items[:8]:
            title = str(it.get("title") or it.get("full_name") or "")
            desc = str(it.get("description") or it.get("summary") or "")[:200]
            url = str(it.get("url") or it.get("pdf") or "")
            feed.append(f"[{site}] {title}\n  {desc}\n  {url}")

    prompt = (
        f"H-SEMAS 是一个多智能体决策系统. 以下是今天扫到的外部趋势:\n\n"
        + "\n\n".join(feed[:25]) + "\n\n"
        "评估每一条对 H-SEMAS 是否有【可整合价值】 (新框架/新模型/新数据源/新评估方法).\n"
        "只挑出值得整合的, 最多 3 条. 输出 strict JSON:\n"
        '{"integrations": [{"title":"...","why":"...","integration_kind":"new_dep|new_dept|new_prompt|new_evolver","priority":"low|med|high"}]}\n'
        "若全无价值, integrations 为空."
    )
    try:
        text = asyncio.run(ask_cheap_llm(prompt))
        obj = parse_json_loose(text) or {}
    except Exception as e:
        append_log("p17_trend_monitor", {"status": "llm_error", "error": repr(e)[:200]})
        return {"evolver": "p17_trend_monitor", "status": "llm_error",
                "summary": f"LLM 失败: {e!r}"}

    integrations = obj.get("integrations") or []
    submitted = 0
    if integrations:
        from ...pending_changes import submit_change
        for it in integrations[:3]:
            try:
                submit_change(
                    evolver="p17_trend_monitor",
                    kind="trend_integration",
                    target=str(it.get("integration_kind", "")),
                    description=f"[{it.get('priority','med')}] {it.get('title','')}: {it.get('why','')}",
                    proposal=it,
                )
                submitted += 1
            except Exception:
                pass

    append_log("p17_trend_monitor", {
        "trends_fetched": total, "integrations_proposed": len(integrations),
        "submitted_to_pending": submitted,
        "sources": {k: len(v) for k, v in trends.items()},
    })
    return {
        "evolver": "p17_trend_monitor", "status": "done",
        "trends_fetched": total, "submitted_to_pending": submitted,
        "summary": f"扫 {total} 条趋势, 提案 {submitted} 条入待审池",
    }
