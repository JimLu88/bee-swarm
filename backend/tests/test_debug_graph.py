"""Optional LangGraph debug HTTP surface."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


class DebugGraphStateTests(unittest.TestCase):
    def test_disabled_returns_404(self) -> None:
        from app.main import app
        from app.settings import settings

        with patch.object(settings, "hsemas_expose_graph_state", False):
            with TestClient(app) as c:
                r = c.get("/api/debug/graph-state/dec-x")
        self.assertEqual(r.status_code, 404)


class DebugGraphStateAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_enabled_returns_sanitized_values(self) -> None:
        from app.main import app
        from app.orchestration.decision_graph import invoke_decision_graph
        from app.settings import settings

        did = "dec-debug-http"
        with patch.object(settings, "hsemas_expose_graph_state", True):
            await invoke_decision_graph(
                decision_id=did,
                task="dbg",
                mode_id="program_management",
                mode_label="项目管理",
                departments=["finance"],
            )
            with TestClient(app) as c:
                r = c.get(f"/api/debug/graph-state/{did}")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["thread_id"], did)
        self.assertIn("values", body)
        self.assertEqual(body["values"].get("reports_count"), 1)
        self.assertEqual(body["values"].get("report_depts_order"), ["finance"])
        brief = body["values"].get("summary_brief")
        self.assertIsInstance(brief, dict)
        rag = brief.get("rag_aggregate") if isinstance(brief, dict) else None
        self.assertIsInstance(rag, dict)
        self.assertGreater(int(rag.get("chunks_sum_across_depts") or 0), 0)
