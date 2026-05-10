"""Merge dense (Qdrant) and lexical (SQLite FTS) hits for optional hybrid retrieval."""

from __future__ import annotations

from .types import RagChunk


def merge_vector_and_fts_hits(vector_hits: list[RagChunk], fts_hits: list[RagChunk]) -> list[RagChunk]:
    """
    Dedupe by chunk_id. Same id in both lanes gets a small score bonus; ordering by score desc.
    """
    merged: dict[str, RagChunk] = {}
    for c in vector_hits:
        m = dict(c.meta or {})
        m.setdefault("rag_lane", "vector")
        merged[c.chunk_id] = RagChunk(
            chunk_id=c.chunk_id,
            title=c.title,
            content=c.content,
            score=float(c.score),
            meta=m,
        )
    for c in fts_hits:
        if c.chunk_id in merged:
            v = merged[c.chunk_id]
            vm = dict(v.meta or {})
            fts_score = float(c.score)
            combined = max(float(v.score), fts_score) + 0.05
            vm["fts_score"] = fts_score
            vm["hybrid"] = True
            vm["rag_lane"] = "hybrid"
            merged[c.chunk_id] = RagChunk(
                chunk_id=v.chunk_id,
                title=v.title,
                content=v.content,
                score=combined,
                meta=vm,
            )
        else:
            m = dict(c.meta or {})
            m.setdefault("rag_lane", "fts")
            merged[c.chunk_id] = RagChunk(
                chunk_id=c.chunk_id,
                title=c.title,
                content=c.content,
                score=float(c.score) * 0.92,
                meta=m,
            )
    return sorted(merged.values(), key=lambda x: x.score, reverse=True)
