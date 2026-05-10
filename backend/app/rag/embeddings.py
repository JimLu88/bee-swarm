"""
Vector embeddings for Qdrant: deterministic hash (default) or LiteLLM when configured.

When switching between hash and real embeddings, Qdrant collection vector size changes —
drop the old collection or use a new mode_id / collection.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from ..settings_llm_rag import llm_rag_settings

logger = logging.getLogger(__name__)


def _any_llm_key() -> bool:
    return any(
        [
            llm_rag_settings.anthropic_api_key,
            llm_rag_settings.openai_api_key,
            llm_rag_settings.gemini_api_key,
            llm_rag_settings.deepseek_api_key,
            llm_rag_settings.doubao_api_key,
        ]
    )


def use_litellm_embeddings() -> bool:
    """Use LiteLLM embedding API when model is set and at least one provider key exists."""
    m = (llm_rag_settings.litellm_embedding_model or "").strip()
    return bool(m) and _any_llm_key()


def infer_litellm_embedding_dim(model: str) -> int:
    ml = model.lower()
    if "3-large" in ml or "embedding-3-large" in ml:
        return 3072
    if "3-small" in ml or "embedding-3-small" in ml:
        return 1536
    if "ada" in ml:
        return 1536
    return 1536


def embedding_dimension() -> int:
    """Vector size for Qdrant collections and placeholder hash vectors."""
    if llm_rag_settings.embedding_vector_dim is not None:
        return int(llm_rag_settings.embedding_vector_dim)
    if use_litellm_embeddings():
        return infer_litellm_embedding_dim(llm_rag_settings.litellm_embedding_model)
    return 64


def _hash_vector(text: str, dim: int) -> list[float]:
    h = hashlib.sha256(text.encode("utf-8")).digest()
    out: list[float] = []
    cur = h
    while len(out) < dim:
        for b in cur:
            out.append((b / 255.0) * 2.0 - 1.0)
            if len(out) >= dim:
                break
        cur = hashlib.sha256(cur).digest()
    return out


def _litellm_extra() -> dict[str, Any]:
    extra: dict[str, Any] = {}
    if llm_rag_settings.litellm_base_url:
        extra["api_base"] = llm_rag_settings.litellm_base_url
    return extra


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Batch embed for ingest/search. Uses hash vectors when LiteLLM embeddings are not configured.
    """
    if not texts:
        return []
    dim = embedding_dimension()
    if not use_litellm_embeddings():
        return [_hash_vector(t, dim) for t in texts]

    from litellm import embedding as litellm_embedding  # type: ignore

    model = (llm_rag_settings.litellm_embedding_model or "").strip()
    resp = litellm_embedding(model=model, input=texts, **_litellm_extra())
    data = list(resp.get("data") or [])
    data.sort(key=lambda x: int(x.get("index", 0)))
    out: list[list[float]] = []
    for row in data:
        vec = row.get("embedding")
        if not isinstance(vec, list):
            raise RuntimeError("litellm_embedding_missing_embedding")
        out.append([float(x) for x in vec])
    if len(out) != len(texts):
        raise RuntimeError("litellm_embedding_count_mismatch")
    for i, v in enumerate(out):
        if len(v) != dim:
            raise RuntimeError(f"litellm_embedding_dim_mismatch expected={dim} got={len(v)} item={i}")
    return out


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]


def embedding_rag_status_fields() -> dict[str, Any]:
    """Payload fragments for /api/status.rag."""
    model = (llm_rag_settings.litellm_embedding_model or "").strip()
    dim = embedding_dimension()
    ready = use_litellm_embeddings()
    misconfigured = bool(model) and not ready
    if ready:
        mode = "litellm"
        note = f"litellm:{model}"
    else:
        mode = "hash"
        note = f"placeholder_sha256_expanded_{dim}d"
    return {
        "embedding_mode": mode,
        "embedding_model": model or None,
        "embedding_dim": dim,
        "embedding_litellm_ready": ready,
        "embedding_misconfigured": misconfigured,
        "embedding_note": note + (" (set API key for LITELLM_EMBEDDING_MODEL)" if misconfigured else ""),
        "hybrid_local_fts": llm_rag_settings.rag_hybrid_local_fts,
    }
