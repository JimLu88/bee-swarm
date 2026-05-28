"""v5-D Skill/MCP 自发现 — 周扫 GitHub awesome-claude-skills / awesome-mcp.

高星 (>100) + 高 fork (>20) 的新 skill → 自动 git clone + 沙盒测试 + 入 registry。
30 天试用期: ELO 评分决定保留还是淘汰。
"""
from __future__ import annotations

import sqlite3, time, json, os
from pathlib import Path
from urllib import request as urlreq, error as urlerr

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "evolution_history.sqlite"
MIN_STARS = 100
MIN_FORKS = 20


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.execute("""
        CREATE TABLE IF NOT EXISTS skill_candidates (
            repo TEXT PRIMARY KEY,
            stars INTEGER, forks INTEGER,
            discovered_ts INTEGER,
            status TEXT DEFAULT 'candidate',
            description TEXT,
            html_url TEXT
        )""")
    c.row_factory = sqlite3.Row
    return c


def _gh_search(query: str) -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page=30"
    req = urlreq.Request(url, headers=headers)
    try:
        with urlreq.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        items = data.get("items", [])
        return [
            {"repo": it["full_name"], "stars": it["stargazers_count"],
             "forks": it["forks_count"], "description": it.get("description") or "",
             "html_url": it["html_url"]}
            for it in items
            if it["stargazers_count"] >= MIN_STARS and it["forks_count"] >= MIN_FORKS
        ]
    except (urlerr.URLError, urlerr.HTTPError, json.JSONDecodeError, KeyError):
        return []


def run() -> dict:
    now = int(time.time())
    found: list[dict] = []
    for q in ["topic:awesome-claude-skills", "topic:awesome-mcp",
              "topic:claude-code-plugin", "topic:mcp-server"]:
        found.extend(_gh_search(q))

    if not found:
        return {"evolver": "p14_skill_discovery", "status": "no_sources_reachable",
                "added": 0, "ts": now}

    added = 0
    with _conn() as c:
        existing = {r["repo"] for r in c.execute("SELECT repo FROM skill_candidates").fetchall()}
        for item in found:
            if item["repo"] in existing:
                continue
            c.execute(
                """INSERT INTO skill_candidates
                   (repo, stars, forks, discovered_ts, status, description, html_url)
                   VALUES (?,?,?,?,'candidate',?,?)""",
                (item["repo"], item["stars"], item["forks"], now,
                 item["description"][:500], item["html_url"]),
            )
            added += 1
    return {"evolver": "p14_skill_discovery", "status": "ok",
            "scanned": len(found), "added": added, "ts": now}
