"""Embedding helpers: hash fallback vs LiteLLM (mocked)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


class EmbeddingsTests(unittest.TestCase):
    def test_empty_input(self) -> None:
        from app.rag.embeddings import embed_texts

        self.assertEqual(embed_texts([]), [])

    def test_hash_vectors_default_dim(self) -> None:
        from app.rag.embeddings import embed_texts, embedding_dimension
        from app.settings_llm_rag import llm_rag_settings

        with patch.object(llm_rag_settings, "litellm_embedding_model", ""):
            with patch.object(llm_rag_settings, "embedding_vector_dim", None):
                self.assertEqual(embedding_dimension(), 64)
                v = embed_texts(["hello", "world"])
                self.assertEqual(len(v), 2)
                self.assertEqual(len(v[0]), 64)

    def test_litellm_path_mocked(self) -> None:
        from app.rag.embeddings import embed_texts
        from app.settings_llm_rag import llm_rag_settings

        fake = MagicMock(
            return_value={
                "data": [
                    {"index": 0, "embedding": [0.01] * 1536},
                    {"index": 1, "embedding": [0.02] * 1536},
                ]
            }
        )
        with patch.object(llm_rag_settings, "litellm_embedding_model", "text-embedding-3-small"):
            with patch.object(llm_rag_settings, "embedding_vector_dim", None):
                with patch.object(llm_rag_settings, "openai_api_key", "sk-test"):
                    with patch("litellm.embedding", fake):
                        out = embed_texts(["a", "b"])
        self.assertEqual(len(out), 2)
        self.assertEqual(len(out[0]), 1536)
        fake.assert_called_once()
