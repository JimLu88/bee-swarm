import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class DecisionGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_graph_compiles(self) -> None:
        from app.orchestration.decision_graph import ensure_compiled_graph

        g = await ensure_compiled_graph()
        self.assertIsNotNone(g)


class DecisionGraphAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_invoke_single_department_smoke(self) -> None:
        from app.orchestration.decision_graph import invoke_decision_graph

        s = await invoke_decision_graph(
            decision_id="dec-graph-smoke",
            task="graph smoke",
            mode_id="program_management",
            mode_label="项目管理",
            departments=["finance"],
        )
        self.assertEqual(s.decision_id, "dec-graph-smoke")
        self.assertEqual(s.mode_id, "program_management")
        self.assertEqual(s.mode_label, "项目管理")
        self.assertEqual(len(s.dept_reports), 1)
        self.assertEqual(s.dept_reports[0].dept, "finance")
        meta = s.dept_reports[0].rag_retrieval_meta
        self.assertIsInstance(meta, dict)
        self.assertIn("rag_backend", meta)
        self.assertIn("total_chunks", meta)
        agg = s.rag_aggregate
        self.assertIsInstance(agg, dict)
        self.assertEqual(agg.get("chunks_sum_across_depts"), s.dept_reports[0].rag_retrieval_meta.get("total_chunks"))
        self.assertTrue(s.ceo_decision)
        self.assertIsNotNone(s.dispatcher)

    async def test_invoke_two_depts_reports_follow_department_order(self) -> None:
        from app.orchestration.decision_graph import invoke_decision_graph

        s = await invoke_decision_graph(
            decision_id="dec-graph-two",
            task="multi dept order",
            mode_id="program_management",
            mode_label="项目管理",
            departments=["arch", "logic"],
        )
        self.assertEqual(len(s.dept_reports), 2)
        self.assertEqual([r.dept for r in s.dept_reports], ["arch", "logic"])


class DecisionGraphSqliteTests(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_checkpoint_survives_process_style_reopen(self) -> None:
        """AsyncSqliteSaver + same DB file: new compile/reconnect still sees thread state."""
        from app.orchestration import decision_graph as dg
        from app.settings import settings

        fd, tmp = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        did = "dec-sqlite-reopen"
        try:
            await dg.shutdown_checkpoint_runtime()
            with patch.object(settings, "hsemas_graph_checkpoint_backend", "sqlite"), patch.object(
                settings, "hsemas_graph_checkpoint_sqlite_path", tmp
            ):
                await dg.invoke_decision_graph(
                    decision_id=did,
                    task="sqlite persist",
                    mode_id="program_management",
                    mode_label="项目管理",
                    departments=["finance"],
                )
            await dg.shutdown_checkpoint_runtime()

            with patch.object(settings, "hsemas_graph_checkpoint_backend", "sqlite"), patch.object(
                settings, "hsemas_graph_checkpoint_sqlite_path", tmp
            ):
                g = await dg.ensure_compiled_graph()
                snap = await g.aget_state({"configurable": {"thread_id": did}})
            vals = snap.values
            self.assertIsNotNone(vals)
            self.assertEqual(vals.get("decision_id"), did)
        finally:
            await dg.shutdown_checkpoint_runtime()
            Path(tmp).unlink(missing_ok=True)
