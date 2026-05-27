"""Smoke tests for compact memory rows (stdlib unittest — no pytest required)."""

from __future__ import annotations

import unittest

from app.memory_compact import _trunc, compact_decision_row


class MemoryCompactTests(unittest.TestCase):
    def test_trunc_none(self) -> None:
        self.assertIsNone(_trunc(None, max_chars=10))

    def test_trunc_short(self) -> None:
        self.assertEqual(_trunc("hi", max_chars=10), "hi")

    def test_trunc_long(self) -> None:
        s = "a" * 50
        out = _trunc(s, max_chars=10)
        self.assertTrue(out.endswith("…"))
        self.assertLessEqual(len(out), 10)

    def test_compact_strips_dept_reports(self) -> None:
        row = {
            "decision_id": "dec-x",
            "task": "short",
            "heatmap": [{"dept": "arch", "alert": "green", "confidence_score": 0.9, "dissent_intensity": 0.1}],
            "dept_reports": [{"dept": "arch", "consensus": "x" * 5000}],
            "execution": {"qa_sandbox": {"ok": True}, "executor": {"status": "ready"}},
        }
        c = compact_decision_row(row)
        self.assertEqual(c.get("_compact"), True)
        self.assertNotIn("dept_reports", c)
        self.assertEqual(c.get("dept_reports_preview"), {"count": 1, "depts": ["arch"]})
        self.assertEqual(c.get("execution", {}).get("qa_sandbox", {}).get("ok"), True)

    def test_compact_rag_hint_from_meta(self) -> None:
        row = {
            "decision_id": "dec-rag",
            "task": "t",
            "dept_reports": [
                {
                    "dept": "finance",
                    "consensus": "c",
                    "rag_retrieval_meta": {"total_chunks": 3, "rag_backend": "simulated", "hybrid_overlap_hits": 0},
                },
                {
                    "dept": "arch",
                    "consensus": "c2",
                    "rag_retrieval_meta": {"total_chunks": 5, "rag_backend": "simulated"},
                },
            ],
        }
        c = compact_decision_row(row)
        rh = c.get("rag_hint")
        self.assertIsInstance(rh, dict)
        self.assertEqual(rh.get("chunks_sum_across_depts"), 8)
        self.assertEqual(rh.get("max_chunks_in_one_dept"), 5)
        self.assertEqual(rh.get("dept_with_max_chunks"), "arch")
        self.assertEqual(rh.get("rag_backend"), "simulated")

    def test_compact_rag_hint_legacy_from_rag_context_length(self) -> None:
        row = {
            "decision_id": "dec-old",
            "task": "t",
            "dept_reports": [
                {"dept": "finance", "consensus": "c", "rag_context": [{"chunk_id": "a"}, {"chunk_id": "b"}]},
            ],
        }
        c = compact_decision_row(row)
        rh = c.get("rag_hint")
        self.assertIsInstance(rh, dict)
        self.assertEqual(rh.get("chunks_sum_across_depts"), 2)
        self.assertEqual(rh.get("legacy_chunk_counts"), True)


if __name__ == "__main__":
    unittest.main()
