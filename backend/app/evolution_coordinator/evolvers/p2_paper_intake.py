"""arXiv 论文吸收 — 抓最新 agent 论文, 提关键 abstract 入 bee-memory."""
from __future__ import annotations
import os
import httpx
from ._utils import append_log

QUERIES = [
    "LLM agent self-improvement",
    "multi-agent system orchestration",
    "RAG retrieval augmented",
]
SCRAPER_URL = os.environ.get("BEE_SCRAPER_URL", "http://127.0.0.1:8003")
MEMORY_URL = os.environ.get("BEE_MEMORY_URL", "http://127.0.0.1:8004")
TOKEN = os.environ.get("BEE_BEARER_TOKEN", "dev-token-change-me")


def run() -> dict:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    fetched: list[dict] = []
    errors: list[str] = []
    for q in QUERIES:
        try:
            with httpx.Client(timeout=30) as c:
                r = c.post(f"{SCRAPER_URL}/scraper/task",
                           json={"site": "arxiv", "keyword": q, "limit": 5},
                           headers=headers)
            if r.status_code == 200:
                items = r.json().get("items", [])
                for it in items:
                    fetched.append({**it, "query": q})
        except Exception as e:
            errors.append(f"{q}: {e!r}")

    if not fetched:
        append_log("p2_paper_intake", {
            "status": "no_data", "errors": errors[:5], "queries": QUERIES,
        })
        return {"evolver": "p2_paper_intake", "status": "no_data",
                "summary": "未抓到论文 (爬虫未启或 arxiv 不可达)",
                "errors": errors[:3]}

    saved = 0
    save_errors: list[str] = []
    for p in fetched[:15]:
        try:
            with httpx.Client(timeout=15) as c:
                r = c.post(f"{MEMORY_URL}/memory/store", json={
                    "persona_id": "swarm_global",
                    "kind": "knowledge_trend",
                    "content": (f"[arxiv] {p.get('title','')}\n"
                                f"摘要: {p.get('summary','')[:600]}\n"
                                f"作者: {', '.join(p.get('authors',[])[:3])}\n"
                                f"PDF: {p.get('pdf','')}"),
                    "meta": {"source": "arxiv", "query": p.get("query"),
                             "arxiv_id": p.get("id", "")},
                    "importance": 0.6, "novelty": 0.7,
                }, headers=headers)
            if r.status_code in (200, 201):
                saved += 1
            else:
                save_errors.append(f"{p.get('id','')}: HTTP {r.status_code}")
        except Exception as e:
            save_errors.append(f"{p.get('id','')}: {e!r}")

    append_log("p2_paper_intake", {
        "papers_fetched": len(fetched), "saved_to_memory": saved,
        "fetch_errors": errors[:5], "save_errors": save_errors[:5],
        "queries": QUERIES,
    })
    return {
        "evolver": "p2_paper_intake", "status": "done",
        "papers_fetched": len(fetched), "saved_to_memory": saved,
        "summary": f"抓 {len(fetched)} 篇论文, 存 {saved} 篇入 bee-memory",
    }
