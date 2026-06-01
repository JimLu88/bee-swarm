"""知识收件箱 — 决策时联网搜索命中先落这里 (pending), 等 20:00 CEO 梳理.

为什么要收件箱 (而不是搜到就直接进 bee-memory):
  - 联网结果含大量噪音/广告/重复, 直接入库会污染人设知识库
  - 统一在 20:00 让 CEO 模型批量去重+提炼, 省 token 且质量高
  - 可观测: /api/learning/inbox/stats 看进度

表 knowledge_inbox (app/auto_learning/data/learning.sqlite):
  id TEXT PK, ts INTEGER(unix秒), mode_id, dept_id, persona_id,
  query, title, content, source_url, domain,
  status('pending'|'digested'|'discarded'), digest_ts INTEGER, url_hash TEXT
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = _DATA_DIR / "learning.sqlite"

# 单条正文截断 (防爆), 单次决策最多记多少条 (防刷)
_MAX_CONTENT = 4000
_MAX_PER_CALL = 12


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.execute(
        """CREATE TABLE IF NOT EXISTS knowledge_inbox (
            id TEXT PRIMARY KEY,
            ts INTEGER,
            mode_id TEXT,
            dept_id TEXT,
            persona_id TEXT,
            query TEXT,
            title TEXT,
            content TEXT,
            source_url TEXT,
            domain TEXT,
            status TEXT DEFAULT 'pending',
            digest_ts INTEGER DEFAULT 0,
            url_hash TEXT
        )"""
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_inbox_status ON knowledge_inbox(status, mode_id, ts)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_inbox_dedup ON knowledge_inbox(mode_id, persona_id, url_hash)")
    c.row_factory = sqlite3.Row
    return c


def _url_hash(mode_id: str, persona_id: str, url: str, title: str) -> str:
    raw = f"{mode_id}|{persona_id}|{url or title}".encode("utf-8", "ignore")
    return hashlib.sha1(raw).hexdigest()[:16]


def record_web_hits(
    *,
    mode_id: str,
    dept_id: str,
    persona_id: str,
    query: str,
    chunks: list[dict[str, Any]],
) -> int:
    """决策时调用. chunks 为 RagChunk.__dict__ 或 {title,content,meta:{source_url,domain}} 列表.

    去重: 同 (mode_id, persona_id, url) 若 30 天内已记过就跳过. best-effort, 任何异常吞掉
    (绝不能因为记日志失败而中断决策主链路).
    Returns: 实际新增条数.
    """
    if not chunks:
        return 0
    persona_id = persona_id or f"_dept_{dept_id}"
    now = int(time.time())
    cutoff = now - 30 * 86400
    stored = 0
    try:
        with _conn() as c:
            for ch in chunks[:_MAX_PER_CALL]:
                meta = ch.get("meta") or {}
                title = str(ch.get("title") or meta.get("title") or "web")[:300]
                content = str(ch.get("content") or "")[:_MAX_CONTENT]
                url = str(meta.get("source_url") or ch.get("source_url") or "")
                domain = str(meta.get("domain") or ch.get("domain") or "")
                if len(content.strip()) < 30:
                    continue  # 太短没价值
                uh = _url_hash(mode_id, persona_id, url, title)
                dup = c.execute(
                    "SELECT 1 FROM knowledge_inbox "
                    "WHERE mode_id=? AND persona_id=? AND url_hash=? AND ts>=? LIMIT 1",
                    (mode_id, persona_id, uh, cutoff),
                ).fetchone()
                if dup:
                    continue
                c.execute(
                    "INSERT INTO knowledge_inbox "
                    "(id,ts,mode_id,dept_id,persona_id,query,title,content,source_url,domain,status,digest_ts,url_hash) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,'pending',0,?)",
                    (f"in-{uuid.uuid4().hex[:12]}", now, mode_id, dept_id, persona_id,
                     str(query or "")[:500], title, content, url, domain, uh),
                )
                stored += 1
    except Exception:
        return stored
    return stored


def list_pending(mode_id: str | None = None, limit: int = 300) -> list[dict[str, Any]]:
    try:
        with _conn() as c:
            if mode_id:
                rows = c.execute(
                    "SELECT * FROM knowledge_inbox WHERE status='pending' AND mode_id=? "
                    "ORDER BY ts ASC LIMIT ?",
                    (mode_id, int(limit)),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM knowledge_inbox WHERE status='pending' "
                    "ORDER BY ts ASC LIMIT ?",
                    (int(limit),),
                ).fetchall()
            return [dict(r) for r in rows]
    except Exception:
        return []


def pending_mode_ids() -> list[str]:
    """有 pending 条目的场景列表 (20:00 digest 用来分组逐场景处理)."""
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT DISTINCT mode_id FROM knowledge_inbox WHERE status='pending'"
            ).fetchall()
            return [str(r["mode_id"]) for r in rows]
    except Exception:
        return []


def mark(ids: list[str], status: str) -> int:
    if not ids or status not in ("digested", "discarded", "pending"):
        return 0
    now = int(time.time())
    try:
        with _conn() as c:
            c.executemany(
                "UPDATE knowledge_inbox SET status=?, digest_ts=? WHERE id=?",
                [(status, now, i) for i in ids],
            )
        return len(ids)
    except Exception:
        return 0


def stats() -> dict[str, Any]:
    out: dict[str, Any] = {"by_status": {}, "by_mode_pending": {}, "total": 0}
    try:
        with _conn() as c:
            for r in c.execute("SELECT status, COUNT(*) n FROM knowledge_inbox GROUP BY status"):
                out["by_status"][str(r["status"])] = int(r["n"])
                out["total"] += int(r["n"])
            for r in c.execute(
                "SELECT mode_id, COUNT(*) n FROM knowledge_inbox "
                "WHERE status='pending' GROUP BY mode_id ORDER BY n DESC"
            ):
                out["by_mode_pending"][str(r["mode_id"])] = int(r["n"])
    except Exception as e:
        out["error"] = repr(e)
    return out
