"""HTTP surface for mode listing and optional YAML registry reload."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.modes import MODES


class ModesApiTests(unittest.TestCase):
    def test_get_modes_includes_extra_yaml_modes(self) -> None:
        with TestClient(app) as c:
            r = c.get("/api/modes")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIsInstance(data, list)
        from app.modes import list_extra_mode_ids
        ids = [row["mode_id"] for row in data]
        self.assertEqual(len(ids), len(MODES) + len(list_extra_mode_ids()))
        self.assertIn("generic_consulting", ids)  # 已提升为 builtin, 仍应在列表里
        self.assertIn("ops_review", ids)           # 仍为 extra yaml 场景

    def test_post_modes_reload_disabled_by_default(self) -> None:
        with TestClient(app) as c:
            r = c.post("/api/modes/reload")
        self.assertEqual(r.status_code, 404)

    def test_post_modes_reload_when_enabled(self) -> None:
        from app.settings import settings

        with patch.object(settings, "hsemas_modes_yaml_reload_enabled", True):
            with TestClient(app) as c:
                r = c.post("/api/modes/reload")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertGreaterEqual(int(body.get("count") or 0), len(MODES) + 2)

    def test_modes_lookup_builtin_extra_fallback(self) -> None:
        with TestClient(app) as c:
            r1 = c.get("/api/modes/lookup/program_management")
            r2 = c.get("/api/modes/lookup/ops_review")
            r3 = c.get("/api/modes/lookup/no_such_mode_zzzz")
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json().get("registry"), "builtin")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json().get("registry"), "extra")
        self.assertEqual(r3.status_code, 200)
        b3 = r3.json()
        self.assertEqual(b3.get("registry"), "fallback")
        self.assertTrue(b3.get("fallback_to_program_management"))
        self.assertEqual((b3.get("mode") or {}).get("mode_id"), "program_management")

    def test_decision_start_reject_unknown_mode(self) -> None:
        with TestClient(app) as c:
            ok = c.post("/api/decision/start", json={"task": "t", "mode_id": "generic_consulting", "reject_unknown_mode": True})
            bad = c.post("/api/decision/start", json={"task": "t", "mode_id": "nope_nope_nope", "reject_unknown_mode": True})
        self.assertEqual(ok.status_code, 200)
        self.assertTrue((ok.json() or {}).get("decision_id"))
        self.assertEqual(bad.status_code, 422)
