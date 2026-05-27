"""Phase 10: scenario history listing and rollback."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings


class ScenarioHistoryRollbackTests(unittest.TestCase):
    def test_history_and_rollback_flow(self) -> None:
        mode_id = "zz_hist_mode"
        target = Path(__file__).resolve().parent.parent / "scenarios" / f"{mode_id}.yaml"
        hist_dir = Path(__file__).resolve().parent.parent / "scenarios" / "_history" / mode_id
        try:
            with patch.object(settings, "hsemas_scenario_write_enabled", True):
                with TestClient(app) as c:
                    w = c.post(
                        "/api/scenarios/write",
                        json={
                            "kind": "root_overlay",
                            "mode_id": mode_id,
                            "yaml_text": f"mode_id: {mode_id}\nlabel: A\n",
                            "overwrite": True,
                            "reload_modes": False,
                        },
                    )
                    self.assertEqual(w.status_code, 200)
                    self.assertTrue(target.exists())

                    h = c.get(f"/api/scenarios/history/{mode_id}?limit=50")
                    self.assertEqual(h.status_code, 200)
                    items = (h.json() or {}).get("items") or []
                    self.assertGreaterEqual(len(items), 1)

            # pick an after snapshot file (exists under history dir)
            after_files = sorted(hist_dir.glob("*-root_overlay-after.yaml"))
            self.assertTrue(after_files)
            snap = after_files[-1]

            with patch.object(settings, "hsemas_scenario_write_enabled", True):
                with TestClient(app) as c:
                    rb = c.post(
                        "/api/scenarios/rollback",
                        json={"kind": "root_overlay", "mode_id": mode_id, "history_path": str(snap), "reload_modes": False},
                    )
            self.assertEqual(rb.status_code, 200)
            self.assertTrue((rb.json() or {}).get("ok"))
        finally:
            if target.exists():
                target.unlink()
