# -*- coding: utf-8 -*-
"""书库存储 + 混合检索:sqlite-vec(向量语义) + FTS5(关键词精确) + RRF 融合。

- 向量表 vec_chunks(rowid=chunks.id, embedding float[dim]):语义召回。
- 关键词表 fts_chunks(content, tokenize=trigram):中文无需分词即可子串匹配。
- 无嵌入器时自动降级为 FTS5 纯关键词(vector_enabled=False)。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

from .embed import serialize_f32

RRF_K = 60  # Reciprocal Rank Fusion 常数


class BookStore:
    def __init__(self, db_path: str | Path, dim: Optional[int] = None):
        self.path = str(db_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.vector_enabled = bool(dim)
        if self.vector_enabled:
            import sqlite_vec
            self.db.enable_load_extension(True)
            sqlite_vec.load(self.db)
            self.db.enable_load_extension(False)
        self.dim = dim
        self._init_schema()

    def _init_schema(self) -> None:
        c = self.db
        c.execute("""CREATE TABLE IF NOT EXISTS chunks(
            id INTEGER PRIMARY KEY, book_key TEXT, title TEXT, author TEXT,
            scenario TEXT, dept TEXT, chunk_ix INTEGER, content TEXT)""")
        c.execute("CREATE INDEX IF NOT EXISTS ix_chunks_book ON chunks(book_key)")
        c.execute("""CREATE TABLE IF NOT EXISTS books(
            book_key TEXT PRIMARY KEY, title TEXT, file TEXT, scenario TEXT,
            n_chunks INTEGER, size INTEGER)""")
        c.execute("CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT)")
        c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(content, tokenize='trigram')")
        if self.vector_enabled:
            c.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding float[{self.dim}])")
        c.commit()

    # ---- 写入 ----
    def has_book(self, book_key: str, size: int) -> bool:
        r = self.db.execute("SELECT size FROM books WHERE book_key=?", (book_key,)).fetchone()
        return bool(r) and int(r["size"]) == int(size)

    def commit(self) -> None:
        self.db.commit()

    def add_book(self, book_key, title, author, scenario, dept, file, size,
                 chunks: List[str], embeddings: Optional[List[List[float]]],
                 commit: bool = True) -> int:
        c = self.db
        # 幂等:先删旧
        old = [r["id"] for r in c.execute("SELECT id FROM chunks WHERE book_key=?", (book_key,))]
        if old:
            c.executemany("DELETE FROM chunks WHERE id=?", [(i,) for i in old])
            c.executemany("DELETE FROM fts_chunks WHERE rowid=?", [(i,) for i in old])
            if self.vector_enabled:
                c.executemany("DELETE FROM vec_chunks WHERE rowid=?", [(i,) for i in old])
        n = 0
        for ix, ch in enumerate(chunks):
            cur = c.execute(
                "INSERT INTO chunks(book_key,title,author,scenario,dept,chunk_ix,content) VALUES(?,?,?,?,?,?,?)",
                (book_key, title, author, scenario, dept, ix, ch))
            rid = cur.lastrowid
            c.execute("INSERT INTO fts_chunks(rowid,content) VALUES(?,?)", (rid, ch))
            if self.vector_enabled and embeddings is not None:
                c.execute("INSERT INTO vec_chunks(rowid,embedding) VALUES(?,?)",
                          (rid, serialize_f32(embeddings[ix])))
            n += 1
        c.execute("INSERT OR REPLACE INTO books(book_key,title,file,scenario,n_chunks,size) VALUES(?,?,?,?,?,?)",
                  (book_key, title, file, scenario, n, size))
        c.commit()
        return n

    def set_meta(self, k: str, v: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)", (k, v))
        self.db.commit()

    def stats(self) -> dict:
        nb = self.db.execute("SELECT COUNT(*) n FROM books").fetchone()["n"]
        nc = self.db.execute("SELECT COUNT(*) n FROM chunks").fetchone()["n"]
        return {"books": nb, "chunks": nc, "vector": self.vector_enabled, "dim": self.dim}

    # ---- 检索 ----
    @staticmethod
    def _fts_query(q: str) -> str:
        # trigram 分词器:用双引号包成短语,转义内部引号,避免 MATCH 语法错误
        return '"' + (q or "").replace('"', '""') + '"'

    def hybrid_search(self, query: str, query_emb: Optional[List[float]] = None,
                      k: int = 5, scenario: Optional[str] = None, pool: int = 30) -> List[dict]:
        ranks: dict[int, float] = {}
        # 1) 向量召回
        if self.vector_enabled and query_emb is not None:
            try:
                rows = self.db.execute(
                    "SELECT rowid, distance FROM vec_chunks WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                    (serialize_f32(query_emb), pool)).fetchall()
                for rank, r in enumerate(rows):
                    ranks[r["rowid"]] = ranks.get(r["rowid"], 0.0) + 1.0 / (RRF_K + rank)
            except Exception:
                pass
        # 2) 关键词召回
        try:
            rows = self.db.execute(
                "SELECT rowid, rank FROM fts_chunks WHERE fts_chunks MATCH ? ORDER BY rank LIMIT ?",
                (self._fts_query(query), pool)).fetchall()
            for rank, r in enumerate(rows):
                ranks[r["rowid"]] = ranks.get(r["rowid"], 0.0) + 1.0 / (RRF_K + rank)
        except Exception:
            pass
        if not ranks:
            return []
        ids = sorted(ranks, key=lambda i: ranks[i], reverse=True)
        out: List[dict] = []
        qmarks = ",".join("?" * len(ids))
        rowmap = {r["id"]: r for r in self.db.execute(
            f"SELECT id,title,author,scenario,dept,content FROM chunks WHERE id IN ({qmarks})", ids)}
        for i in ids:
            r = rowmap.get(i)
            if not r:
                continue
            if scenario and r["scenario"]:
                # scenario 字段可能是逗号拼接的多场景串 → 按成员匹配, 不做精确相等
                owners = {s.strip() for s in str(r["scenario"]).split(",")}
                if scenario not in owners:
                    continue
            out.append({"id": i, "title": r["title"], "author": r["author"],
                        "scenario": r["scenario"], "dept": r["dept"],
                        "content": r["content"], "score": round(ranks[i], 5)})
            if len(out) >= k:
                break
        return out

    def close(self) -> None:
        try:
            self.db.close()
        except Exception:
            pass
