from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from ..settings_llm_rag import llm_rag_settings
from .types import RagChunk


def _safe_mode(mode_id: str) -> str:
    return "".join(c for c in mode_id if c.isalnum() or c in ("_", "-"))[:64] or "default"


def _collection_name(mode_id: str) -> str:
    return f"h_semas__{_safe_mode(mode_id)}"


def _hash_vector(text: str, dim: int = 64) -> list[float]:
    """
    Deterministic placeholder embedding.
    Phase 2.1 will replace this with real embeddings (LiteLLM embeddings).
    """
    h = hashlib.sha256(text.encode("utf-8")).digest()
    out: list[float] = []
    # expand to dim using repeated hashing
    cur = h
    while len(out) < dim:
        for b in cur:
            out.append((b / 255.0) * 2.0 - 1.0)
            if len(out) >= dim:
                break
        cur = hashlib.sha256(cur).digest()
    return out


@dataclass(frozen=True)
class IngestItem:
    chunk_id: str
    title: str
    content: str
    meta: dict[str, Any]


class QdrantStore:
    def __init__(self) -> None:
        self._client = QdrantClient(
            url=llm_rag_settings.qdrant_url,
            api_key=llm_rag_settings.qdrant_api_key,
            timeout=2.5,
            check_compatibility=False,
        )

    def ensure_collection(self, *, mode_id: str, vector_size: int = 64) -> str:
        name = _collection_name(mode_id)
        existing = self._client.get_collections().collections
        if any(c.name == name for c in existing):
            return name
        self._client.create_collection(
            collection_name=name,
            vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
        )
        return name

    def upsert(self, *, mode_id: str, items: list[IngestItem]) -> int:
        name = self.ensure_collection(mode_id=mode_id)
        points: list[qm.PointStruct] = []
        for it in items:
            vec = _hash_vector(f"{it.title}\n{it.content}")
            meta = dict(it.meta or {})
            source_url = str(meta.get("source_url") or "")
            if source_url:
                try:
                    meta["domain"] = urlparse(source_url).netloc.lower()
                except Exception:
                    pass
            payload = {"chunk_id": it.chunk_id, "title": it.title, "content": it.content, "meta": meta}
            pid = int.from_bytes(hashlib.sha256(it.chunk_id.encode("utf-8")).digest()[:8], "big", signed=False)
            points.append(qm.PointStruct(id=pid, vector=vec, payload=payload))
        self._client.upsert(collection_name=name, points=points)
        return len(points)

    def search(self, *, mode_id: str, query: str, k: int = 5) -> list[RagChunk]:
        name = self.ensure_collection(mode_id=mode_id)
        qv = _hash_vector(query)
        hits = self._client.search(collection_name=name, query_vector=qv, limit=max(1, min(k, 20)))
        out: list[RagChunk] = []
        for h in hits:
            payload = h.payload or {}
            out.append(
                RagChunk(
                    chunk_id=str(payload.get("chunk_id") or ""),
                    title=str(payload.get("title") or ""),
                    content=str(payload.get("content") or ""),
                    score=float(h.score or 0.0),
                    meta=dict(payload.get("meta") or {}),
                )
            )
        return out


store = QdrantStore()

