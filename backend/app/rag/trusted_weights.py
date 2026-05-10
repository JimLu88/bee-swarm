from __future__ import annotations

from typing import Any

from .types import RagChunk

# When domain is missing or not listed in trusted_sources
UNKNOWN_DOMAIN_WEIGHT = 0.2


def weight_for_domain(domain: str, trusted: dict[str, Any]) -> float:
    d = (domain or "").lower()
    if d in trusted:
        return float(trusted[d])
    return UNKNOWN_DOMAIN_WEIGHT


def sort_rag_chunks_by_trusted(
    chunks: list[RagChunk],
    trusted: dict[str, Any],
    *,
    k: int,
) -> list[RagChunk]:
    """Re-rank by retrieval_score * trusted_weight; annotate meta for audit/UI."""

    def sort_key(h: RagChunk) -> float:
        meta = h.meta
        domain = str(meta.get("domain") or meta.get("source_domain") or "").lower()
        base = float(h.score)
        w = weight_for_domain(domain, trusted)
        try:
            meta["trusted_domain"] = domain
            meta["trusted_weight"] = w
            meta["weighted_score"] = base * w
        except Exception:
            pass
        return base * w

    return sorted(chunks, key=sort_key, reverse=True)[:k]


def sort_chunk_dicts_by_trusted(
    rows: list[dict[str, Any]],
    trusted: dict[str, Any],
    *,
    k: int,
) -> list[dict[str, Any]]:
    """Same scoring as sort_rag_chunks_by_trusted for serialized chunks (API responses)."""

    def sort_key(h: dict[str, Any]) -> float:
        meta = dict(h.get("meta") or {})
        domain = str(meta.get("domain") or meta.get("source_domain") or "").lower()
        base_score = float(h.get("score") or 0.0)
        w = weight_for_domain(domain, trusted)
        meta["trusted_domain"] = domain
        meta["trusted_weight"] = w
        meta["weighted_score"] = base_score * w
        h["meta"] = meta
        return base_score * w

    return sorted(rows, key=sort_key, reverse=True)[:k]
