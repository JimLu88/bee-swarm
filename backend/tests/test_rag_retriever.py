"""Phase 2: RAG retriever paths (simulated / qdrant failure fallback)."""

from __future__ import annotations

import unittest
from unittest.mock import patch


class RagRetrieverTests(unittest.TestCase):
    def test_simulated_returns_builtin_chunk(self) -> None:
        from app.rag.retriever import RagRetriever
        from app.settings_llm_rag import llm_rag_settings

        with patch.object(llm_rag_settings, "rag_backend", "simulated"):
            hits = RagRetriever().retrieve(mode_id="program_management", dept="finance", task="hello", k=3)
        ids = {h.chunk_id for h in hits}
        self.assertIn("mvp-001", ids)

    def test_qdrant_backend_when_search_raises_returns_fallback_chunks(self) -> None:
        from app.rag import retriever as retriever_mod
        from app.rag.retriever import RagRetriever
        from app.settings_llm_rag import llm_rag_settings

        def boom(*_a: object, **_k: object):
            raise RuntimeError("qdrant down")

        with patch.object(llm_rag_settings, "rag_backend", "qdrant"):
            with patch.object(retriever_mod.qdrant_store, "search", side_effect=boom):
                hits = RagRetriever().retrieve(mode_id="m1", dept="finance", task="task", k=3)
        ids = [h.chunk_id for h in hits]
        self.assertIn("qdrant-unavailable", ids)
        self.assertIn("mvp-001", ids)
