"""Integration tests for /api/memory routes (writes a temp JSONL under backend/data)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


_MODE = "__test_memory_api__"
_DECISION_ID = "dec-integration-test"


class MemoryApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._base = Path(__file__).resolve().parents[1] / "data"
        cls._mode_dir = cls._base / _MODE
        cls._mode_dir.mkdir(parents=True, exist_ok=True)
        cls._jsonl = cls._mode_dir / "decisions.jsonl"
        row = {
            "decision_id": _DECISION_ID,
            "task": "integration task",
            "mode_id": _MODE,
            "mode_label": "测试模式",
            "heatmap": [],
            "dept_reports": [
                {
                    "dept": "arch",
                    "consensus": "long " * 50,
                    "rag_context": [{"chunk_id": "legacy-a"}, {"chunk_id": "legacy-b"}],
                }
            ],
            "execution": {"qa_sandbox": {"ok": True}, "executor": {"status": "ready"}},
        }
        cls._jsonl.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._jsonl.exists():
            cls._jsonl.unlink()
        if cls._mode_dir.exists():
            try:
                cls._mode_dir.rmdir()
            except OSError:
                pass

    def test_memory_one_200(self) -> None:
        from app.main import app

        c = TestClient(app)
        r = c.get(f"/api/memory/{_MODE}/decision/{_DECISION_ID}")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body.get("decision_id"), _DECISION_ID)
        self.assertEqual(body.get("mode_id"), _MODE)
        self.assertEqual(body.get("mode_label"), "测试模式")
        self.assertEqual(len(body.get("dept_reports") or []), 1)
        rag_agg = body.get("rag_aggregate")
        self.assertIsInstance(rag_agg, dict)
        self.assertEqual(rag_agg.get("chunks_sum_across_depts"), 2)
        self.assertEqual(rag_agg.get("legacy_chunk_counts"), True)

    def test_memory_one_404(self) -> None:
        from app.main import app

        c = TestClient(app)
        r = c.get(f"/api/memory/{_MODE}/decision/does-not-exist")
        self.assertEqual(r.status_code, 404)

    def test_memory_list_compact(self) -> None:
        from app.main import app

        c = TestClient(app)
        r = c.get(f"/api/memory/{_MODE}?limit=10&compact=1")
        self.assertEqual(r.status_code, 200)
        rows = r.json()
        self.assertIsInstance(rows, list)
        self.assertGreaterEqual(len(rows), 1)
        first = rows[-1]
        self.assertEqual(first.get("_compact"), True)
        self.assertNotIn("dept_reports", first)
        self.assertEqual(first.get("dept_reports_preview", {}).get("count"), 1)
        self.assertEqual(first.get("mode_id"), _MODE)
        self.assertEqual(first.get("mode_label"), "测试模式")


if __name__ == "__main__":
    unittest.main()
