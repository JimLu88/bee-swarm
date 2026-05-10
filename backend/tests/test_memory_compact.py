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


if __name__ == "__main__":
    unittest.main()
