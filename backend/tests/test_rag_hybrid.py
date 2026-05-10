"""Hybrid merge (vector + FTS) for Qdrant backend."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.rag.hybrid import merge_vector_and_fts_hits
from app.rag.types import RagChunk


class HybridMergeTests(unittest.TestCase):
    def test_overlap_boosts_score_and_marks_hybrid(self) -> None:
        vec = [RagChunk("id1", "Title", "body", 0.55, {"source": "qdrant"})]
        fts = [RagChunk("id1", "Title", "body", 0.50, {"source": "local"})]
        out = merge_vector_and_fts_hits(vec, fts)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].meta.get("hybrid"))
        self.assertGreaterEqual(out[0].score, 0.55)

    def test_union_keeps_disjoint(self) -> None:
        vec = [RagChunk("a", "", "", 0.9, {})]
        fts = [RagChunk("b", "", "", 0.8, {})]
        out = merge_vector_and_fts_hits(vec, fts)
        ids = {x.chunk_id for x in out}
        self.assertEqual(ids, {"a", "b"})


class RetrieverHybridTests(unittest.TestCase):
    def test_qdrant_hybrid_merges(self) -> None:
        from app.rag import retriever as retriever_mod
        from app.rag.retriever import RagRetriever
        from app.settings_llm_rag import llm_rag_settings

        q_hit = RagChunk("q1", "Qt", "Qc", 0.9, {})
        l_hit = RagChunk("l2", "Lt", "Lc", 0.85, {})

        with patch.object(llm_rag_settings, "rag_backend", "qdrant"):
            with patch.object(llm_rag_settings, "rag_hybrid_local_fts", True):
                with patch.object(retriever_mod.qdrant_store, "search", return_value=[q_hit]):
                    with patch.object(retriever_mod, "LocalRagStore") as cls_mock:
                        cls_mock.return_value.search.return_value = [l_hit]
                        hits = RagRetriever().retrieve(mode_id="m", dept="finance", task="x", k=5)
        ids = {h.chunk_id for h in hits}
        self.assertEqual(ids, {"q1", "l2"})
