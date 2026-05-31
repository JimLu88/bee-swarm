"""v6-K /api/trends/* — 聚合 p17/p2 evolver 抓的趋势, 给前端 3 视图渲染."""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/api/trends", tags=["trends"])

EVOLVERS_DATA = Path(__file__).resolve().parent / "evolution_coordinator" / "data"
SCRAPER_URL = os.environ.get("BEE_SCRAPER_URL", "http://127.0.0.1:8003")
TOKEN = os.environ.get("BEE_BEARER_TOKEN", "dev-token-change-me")


def _read_jsonl(path: Path, max_rows: int = 50) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for ln in reversed(lines):
        if not ln.strip():
            continue
        try:
            out.append(json.loads(ln))
            if len(out) >= max_rows:
                break
        except Exception:
            continue
    return out


def _live_fetch(site: str, kw: str, limit: int) -> list[dict[str, Any]]:
    try:
        headers = {"Authorization": f"Bearer {TOKEN}"}
        with httpx.Client(timeout=15) as c:
            r = c.post(f"{SCRAPER_URL}/scraper/task",
                       json={"site": site, "keyword": kw, "limit": limit},
                       headers=headers)
        if r.status_code == 200:
            return r.json().get("items") or []
    except Exception:
        pass
    return []


def _normalize(items: list[dict[str, Any]], origin: str,
               kind: str, default_score: float = 0.5) -> list[dict[str, Any]]:
    out = []
    for it in items:
        title = (it.get("title") or it.get("full_name") or it.get("topic")
                 or it.get("name") or "")
        url = it.get("url") or it.get("pdf") or it.get("source_url") or ""
        score = float(it.get("score") or it.get("stars") or it.get("likes")
                      or default_score)
        ts = it.get("ts") or it.get("pushed_at") or it.get("published") or ""
        ts_int = 0
        if isinstance(ts, str) and ts:
            try:
                import datetime as _dt
                ts_int = int(_dt.datetime.fromisoformat(
                    ts.replace("Z", "+00:00")).timestamp())
            except Exception:
                pass
        elif isinstance(ts, (int, float)):
            ts_int = int(ts)
        out.append({
            "topic": str(title)[:120],
            "kind": kind, "origin": origin,
            "url": url, "score": score, "ts": ts_int,
            "snippet": str(it.get("description") or it.get("summary") or "")[:200],
            "language": it.get("language") or "",
        })
    return out


@router.get("/aggregate")
def trends_aggregate(live: bool = False, limit_per_source: int = 15) -> dict[str, Any]:
    bubbles: list[dict[str, Any]] = []
    p17_rows = _read_jsonl(EVOLVERS_DATA / "p17_trend_monitor.jsonl", max_rows=30)
    p2_rows = _read_jsonl(EVOLVERS_DATA / "p2_paper_intake.jsonl", max_rows=10)
    arxiv_total = sum(int(r.get("papers_fetched", 0)) for r in p2_rows[:3])

    if live:
        bubbles.extend(_normalize(_live_fetch("hacker_news", "", limit_per_source),
                                  "HackerNews", "tech_news"))
        bubbles.extend(_normalize(_live_fetch(
            "github_trending", "stars:>1000 created:>2026-01-01",
            limit_per_source), "GitHubTrending", "repo"))
        bubbles.extend(_normalize(_live_fetch("arxiv", "agent self-improvement",
                                               limit_per_source), "arxiv", "paper"))
        bubbles.extend(_normalize(_live_fetch("huggingface", "",
                                               limit_per_source), "HuggingFace", "model"))

    bubbles.sort(key=lambda b: b["score"], reverse=True)
    bubbles = bubbles[:60]
    cards = sorted(bubbles, key=lambda b: b.get("ts", 0), reverse=True)

    ORIGIN_POS = {
        "HackerNews": (0.20, 0.40),
        "GitHubTrending": (0.55, 0.30),
        "arxiv": (0.80, 0.50),
        "HuggingFace": (0.40, 0.65),
    }
    map_points = []
    for i, b in enumerate(bubbles):
        cx, cy = ORIGIN_POS.get(b["origin"], (0.5, 0.5))
        offset_x = ((i * 31) % 17) / 100 - 0.085
        offset_y = ((i * 47) % 13) / 100 - 0.065
        map_points.append({
            **b,
            "x": max(0.02, min(0.98, cx + offset_x)),
            "y": max(0.02, min(0.98, cy + offset_y)),
        })

    return {
        "ts": int(time.time()),
        "live": live,
        "bubbles": bubbles,
        "cards": cards[:40],
        "map_points": map_points,
        "summary": {
            "total": len(bubbles),
            "by_origin": _count_by(bubbles, "origin"),
            "by_kind": _count_by(bubbles, "kind"),
            "p17_runs": len(p17_rows),
            "p2_papers_total": arxiv_total,
        },
    }


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items:
        k = str(it.get(key) or "?")
        out[k] = out.get(k, 0) + 1
    return out
