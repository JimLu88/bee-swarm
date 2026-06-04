# -*- coding: utf-8 -*-
"""#4 现成开放数据集 → 灌进向量库(合法、零版权风险)。

目前内置:MedRAG Textbooks(AdarshDS/textbooks,18 本权威医学教科书的切块片段,合法开放),
打到医学相关场景上(家庭医生/慢病/体检/睡眠/营养/心理)。

诚实须知:
- 该数据集是**英文**。要让中文提问也能召回, 嵌入器最好用**多语**模型 bge-m3
  (BOOKS_EMBED_MODEL=BAAI/bge-m3);用 bge-small-zh 则跨语种效果一般, FTS5 对英文关键词仍可用。
- 需要 `pip install datasets`(在容器内)。片段多(~12万), 默认限量, 防止把群晖 CPU 跑爆。
"""
from __future__ import annotations

from .embed import get_embedder
from .pipeline import _db_path
from .store import BookStore

MED_SCENARIOS = "family_doctor, chronic_disease, health_checkup, sleep_health, nutrition_fitness, mental_wellness"


def fetch_medrag(limit_chunks: int = 8000, embed_vectors: bool = True) -> dict:
    """拉 MedRAG textbooks 片段灌进向量库(打医学场景标签)。

    limit_chunks: 最多灌多少片段(默认 8000, 防止 CPU 跑太久;设 0 = 全量~12万)。
    embed_vectors: True=算向量(慢但跨语种好);False=只进 FTS5 关键词(快、省, 但中文查英文弱)。
    """
    try:
        from datasets import load_dataset
    except Exception:
        return {"ok": False, "error": "需要先在容器内 pip install datasets"}

    ds = load_dataset("AdarshDS/textbooks", split="train")
    emb = get_embedder() if embed_vectors else None
    dim = emb.dim if emb else None
    store = BookStore(_db_path(), dim)
    if dim:
        store.set_meta("dim", str(dim))

    cur_title = None
    buf: list[str] = []
    n_books = n_chunks = 0

    def _flush(title, chunks: list[str]) -> None:
        nonlocal n_books, n_chunks
        if not chunks:
            return
        key = "medrag::" + str(title)
        vecs = emb.encode(chunks) if emb else None
        store.add_book(key, str(title), "MedRAG", MED_SCENARIOS, "opendata",
                       "medrag", len(chunks), chunks, vecs)
        n_books += 1
        n_chunks += len(chunks)

    total = 0
    for row in ds:
        if limit_chunks and total >= limit_chunks:
            break
        title = str(row.get("title") or "MedRAG")
        content = str(row.get("content") or row.get("contents") or "").strip()
        if not content:
            continue
        if cur_title is None:
            cur_title = title
        if title != cur_title:
            _flush(cur_title, buf)
            buf, cur_title = [], title
        buf.append(content)
        total += 1
    _flush(cur_title, buf)

    st = store.stats()
    store.close()
    return {"ok": True, "dataset": "MedRAG/AdarshDS-textbooks", "scenarios": MED_SCENARIOS,
            "books": n_books, "chunks": n_chunks, "vectors": bool(emb), **st}
