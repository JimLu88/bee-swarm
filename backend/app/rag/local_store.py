from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .types import RagChunk


def _safe_mode(mode_id: str) -> str:
    return "".join(c for c in mode_id if c.isalnum() or c in ("_", "-"))[:64] or "default"


class LocalRagStore:
    """
    Docker-free RAG backend using SQLite FTS5 (per mode_id).

    File: backend/data/<mode_id>/rag.sqlite3
    Tables:
      - chunks: metadata + source_url/domain
      - chunks_fts: full-text index for title/content
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def _db_path(self, mode_id: str) -> Path:
        d = self._base_dir / _safe_mode(mode_id)
        d.mkdir(parents=True, exist_ok=True)
        return d / "rag.sqlite3"

    def _connect(self, mode_id: str) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path(mode_id))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        self._ensure_schema(conn)
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
              chunk_id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              content TEXT NOT NULL,
              source_url TEXT,
              domain TEXT,
              meta_json TEXT,
              updated_at TEXT NOT NULL
            );
            """
        )
        # FTS5 virtual table (contentless; we keep canonical row in chunks)
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
              chunk_id UNINDEXED,
              title,
              content
            );
            """
        )
        conn.commit()

    def upsert(self, *, mode_id: str, items: list[dict[str, Any]]) -> int:
        conn = self._connect(mode_id)
        try:
            n = 0
            for it in items:
                chunk_id = str(it.get("chunk_id") or "").strip()
                if not chunk_id:
                    continue
                title = str(it.get("title") or "untitled")
                content = str(it.get("content") or "")
                meta = dict(it.get("meta") or {})
                source_url = str(it.get("source_url") or meta.get("source_url") or "")
                domain = ""
                if source_url:
                    try:
                        domain = urlparse(source_url).netloc.lower()
                    except Exception:
                        domain = ""
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    """
                    INSERT INTO chunks(chunk_id,title,content,source_url,domain,meta_json,updated_at)
                    VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                      title=excluded.title,
                      content=excluded.content,
                      source_url=excluded.source_url,
                      domain=excluded.domain,
                      meta_json=excluded.meta_json,
                      updated_at=excluded.updated_at
                    """,
                    (chunk_id, title, content, source_url or None, domain or None, str(meta), now),
                )
                # Refresh FTS row (delete+insert)
                conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
                conn.execute("INSERT INTO chunks_fts(chunk_id,title,content) VALUES(?,?,?)", (chunk_id, title, content))
                n += 1
            conn.commit()
            return n
        finally:
            conn.close()

    def search(self, *, mode_id: str, query: str, k: int = 5) -> list[RagChunk]:
        q = (query or "").strip()
        if not q:
            return []
        conn = self._connect(mode_id)
        try:
            # bm25() is available for FTS5; lower is better so invert into score.
            rows = conn.execute(
                """
                SELECT f.chunk_id, bm25(chunks_fts) AS rank
                FROM chunks_fts f
                WHERE chunks_fts MATCH ?
                ORDER BY rank ASC
                LIMIT ?
                """,
                (q, max(1, min(k, 20))),
            ).fetchall()
            out: list[RagChunk] = []
            for r in rows:
                chunk_id = str(r["chunk_id"])
                meta_row = conn.execute("SELECT title, content, domain, source_url FROM chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()
                if not meta_row:
                    continue
                rank = float(r["rank"] or 0.0)
                score = 1.0 / (1.0 + max(0.0, rank))
                meta = {
                    "source": "local",
                    "domain": meta_row["domain"],
                    "source_url": meta_row["source_url"],
                }
                out.append(
                    RagChunk(
                        chunk_id=chunk_id,
                        title=str(meta_row["title"] or ""),
                        content=str(meta_row["content"] or ""),
                        score=score,
                        meta=meta,
                    )
                )
            return out
        finally:
            conn.close()

