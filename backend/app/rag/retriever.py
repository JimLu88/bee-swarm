from __future__ import annotations

from ..settings_llm_rag import llm_rag_settings
from ..vision_scope import is_vision_dept
from .hybrid import merge_vector_and_fts_hits
from .qdrant_store import store as qdrant_store
from .local_store import LocalRagStore
from .types import RagChunk
from .trusted_weights import sort_rag_chunks_by_trusted
from ..config_store import ConfigStore
from ..runtime_paths import backend_data_dir


class RagRetriever:
    """
    Phase 2 retrieval (production-shaped):

    - ``simulated``: small built-in chunks (stable for UI / tests).
    - ``local``: SQLite FTS5 per ``mode_id`` under ``backend/data/``.
    - ``qdrant``: vector search via ``qdrant_store`` (hash or LiteLLM embeddings).
    - Optional ``RAG_HYBRID_LOCAL_FTS`` when backend is ``qdrant``: merge with local FTS hits.
    - ``benchmark`` / ``xlab`` (vision depts): trusted-source weighting when config is set.
    """

    def retrieve(self, *, mode_id: str, dept: str, task: str, k: int = 5) -> list[RagChunk]:
        if llm_rag_settings.rag_backend == "local":
            base = backend_data_dir()
            hits = LocalRagStore(base).search(mode_id=mode_id, query=task, k=k)
            if is_vision_dept(dept) and hits:
                cfg = ConfigStore(base).get_config(mode_id=mode_id)
                trusted = cfg.get("trusted_sources") or {}
                return sort_rag_chunks_by_trusted(hits, trusted, k=k)
            if hits:
                return hits
            return [
                RagChunk(
                    chunk_id="local-empty",
                    title="Local RAG empty",
                    content="当前 mode 的本地 RAG 为空；可用 /api/rag/ingest/{mode_id} 写入数据。",
                    score=0.01,
                    meta={"source": "local"},
                )
            ]
        if llm_rag_settings.rag_backend == "qdrant":
            base = backend_data_dir()
            try:
                kk = max(k, 8) if is_vision_dept(dept) else k
                hits = qdrant_store.search(mode_id=mode_id, query=task, k=kk)
                if llm_rag_settings.rag_hybrid_local_fts:
                    fts_k = max(kk, 12)
                    fts_hits = LocalRagStore(base).search(mode_id=mode_id, query=task, k=fts_k)
                    hits = merge_vector_and_fts_hits(hits, fts_hits)[:kk]
                # Benchmark: apply trusted_sources weight decay/boost based on domain
                if is_vision_dept(dept) and hits:
                    cfg = ConfigStore(base).get_config(mode_id=mode_id)
                    trusted = cfg.get("trusted_sources") or {}
                    hits = sort_rag_chunks_by_trusted(hits, trusted, k=k)
                else:
                    hits = hits[:k]
                if hits:
                    return hits
                return [
                    RagChunk(
                        chunk_id="qdrant-empty",
                        title="Qdrant empty",
                        content="当前 mode 的向量库为空；可用 /api/rag/ingest/{mode_id} 写入数据。",
                        score=0.01,
                        meta={"source": "qdrant"},
                    )
                ]
            except Exception as e:
                return [
                    RagChunk(
                        chunk_id="qdrant-unavailable",
                        title="Qdrant unavailable",
                        content=f"Qdrant 未就绪：{e!r}。临时回退到内置上下文。",
                        score=0.01,
                        meta={"source": "qdrant"},
                    ),
                    RagChunk(
                        chunk_id="mvp-001",
                        title="MVP 目标",
                        content="先跑通状态流与 WebSocket，再接入真实模型与向量库。",
                        score=1.0,
                        meta={"source": "builtin"},
                    ),
                ]
        return [
            RagChunk(
                chunk_id="mvp-001",
                title="MVP 目标",
                content="先跑通状态流与 WebSocket，再接入真实模型与向量库。",
                score=1.0,
                meta={"source": "builtin"},
            )
        ]


retriever = RagRetriever()

