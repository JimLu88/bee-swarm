"""`/api/status` payload fragments."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.status import get_status


class OrchestrationStatusFieldsTests(unittest.TestCase):
    def test_memory_backend_returns_no_sqlite_keys(self) -> None:
        from app.orchestration.decision_graph import orchestration_checkpoint_path_fields
        from app.settings import settings

        with patch.object(settings, "hsemas_graph_checkpoint_backend", "memory"):
            self.assertEqual(orchestration_checkpoint_path_fields(), {})

    def test_sqlite_backend_returns_relative_path(self) -> None:
        from app.orchestration.decision_graph import orchestration_checkpoint_path_fields
        from app.settings import settings

        with patch.object(settings, "hsemas_graph_checkpoint_backend", "sqlite"), patch.object(
            settings, "hsemas_graph_checkpoint_sqlite_path", "data/custom_ckpt.sqlite3"
        ):
            d = orchestration_checkpoint_path_fields()
        self.assertEqual(d.get("checkpoint_sqlite_relative"), "data/custom_ckpt.sqlite3")


class StatusRoadmapTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_status_includes_roadmap(self) -> None:
        s = await get_status()
        rm = s.get("roadmap")
        self.assertIsInstance(rm, dict)
        self.assertEqual(rm.get("phase2"), "shipped")
        self.assertEqual(rm.get("phase3"), "shipped")
        self.assertEqual(rm.get("phase4"), "shipped")
        self.assertEqual(rm.get("phase5"), "shipped")
        self.assertEqual(rm.get("phase6"), "shipped")
        self.assertEqual(rm.get("phase7"), "shipped")
        self.assertEqual(rm.get("phase8"), "shipped")
        self.assertEqual(rm.get("phase9"), "shipped")
        self.assertEqual(rm.get("phase10"), "shipped")
        self.assertEqual(rm.get("phase11"), "shipped")
        self.assertEqual(rm.get("phase12"), "shipped")
        self.assertIn("phase2_scope", rm)
        self.assertIn("phase3_scope", rm)
        st = s.get("scenario_templates")
        self.assertIsInstance(st, dict)
        self.assertIn("yaml_files", st or {})
        self.assertIn("extra_mode_ids", st or {})
        extra_ids = (st or {}).get("extra_mode_ids") or []
        self.assertIn("generic_consulting", extra_ids)
        self.assertIn("ops_review", extra_ids)
        mr = s.get("modes_reload")
        self.assertIsInstance(mr, dict)
        self.assertFalse((mr or {}).get("enabled"))
        cat = s.get("catalog")
        self.assertIsInstance(cat, dict)
        self.assertGreater(int((cat or {}).get("dept_name_count") or 0), 5)
        self.assertEqual((cat or {}).get("dept_names_endpoint"), "/api/catalog/dept-names")
        self.assertEqual((cat or {}).get("scenario_validate_endpoint"), "/api/scenarios/validate")
        self.assertEqual((cat or {}).get("scenario_scaffold_endpoint"), "/api/scenarios/scaffold")
        self.assertEqual((cat or {}).get("scenario_write_endpoint"), "/api/scenarios/write")
        self.assertEqual((cat or {}).get("scenario_rollback_endpoint"), "/api/scenarios/rollback")
