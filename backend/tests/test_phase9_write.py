"""Phase 9: scenario write endpoint (guarded)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings


class ScenarioWriteTests(unittest.TestCase):
    def test_write_disabled_by_default(self) -> None:
        with TestClient(app) as c:
            r = c.post("/api/scenarios/write", json={"kind": "root_overlay", "mode_id": "program_management", "yaml_text": "mode_id: program_management\n"})
        self.assertEqual(r.status_code, 404)

    def test_write_extra_mode_when_enabled(self) -> None:
        tmp_mode = "zz_test_mode_write"
        path = Path(__file__).resolve().parent.parent / "scenarios" / "extra" / f"{tmp_mode}.yaml"
        try:
            with patch.object(settings, "hsemas_scenario_write_enabled", True):
                with TestClient(app) as c:
                    r = c.post(
                        "/api/scenarios/write",
                        json={
                            "kind": "extra_mode",
                            "mode_id": tmp_mode,
                            "yaml_text": f"mode_id: {tmp_mode}\nlabel: T\ndepartments:\n  - security\n  - benchmark\n  - xlab\n",
                            "overwrite": True,
                            "reload_modes": False,
                        },
                    )
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertTrue(body.get("ok"))
            self.assertTrue(path.exists())
            # history exists
            h = Path(__file__).resolve().parent.parent / "scenarios" / "_history" / tmp_mode / "history.jsonl"
            self.assertTrue(h.exists())
        finally:
            if path.exists():
                path.unlink()
