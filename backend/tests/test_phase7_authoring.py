"""Phase 7: YAML authoring tools (validate + scaffold endpoints)."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import app


class ScenarioAuthoringApiTests(unittest.TestCase):
    def test_scaffold_returns_yaml_string(self) -> None:
        with TestClient(app) as c:
            r = c.post("/api/scenarios/scaffold", json={"mode_id": "my_mode"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body.get("mode_id"), "my_mode")
        self.assertIn("mode_id: my_mode", body.get("yaml") or "")

    def test_validate_extra_mode_ok(self) -> None:
        payload = {
            "kind": "extra_mode",
            "mode_id": "ignored_for_extra",
            "yaml": {
                "mode_id": "tmp_mode_1",
                "label": "Tmp",
                "departments": ["security", "benchmark", "xlab"],
                "department_labels": {"security": "sec"},
            },
        }
        with TestClient(app) as c:
            r = c.post("/api/scenarios/validate", json=payload)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("kind"), "extra_mode")

    def test_validate_extra_mode_rejects_empty_departments(self) -> None:
        payload = {"kind": "extra_mode", "mode_id": "x", "yaml": {"mode_id": "m", "departments": []}}
        with TestClient(app) as c:
            r = c.post("/api/scenarios/validate", json=payload)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body.get("ok"))
        self.assertIn("departments_must_be_nonempty_list", body.get("errors") or [])

    def test_validate_root_overlay_mode_id_mismatch(self) -> None:
        payload = {"kind": "root_overlay", "mode_id": "program_management", "yaml": {"mode_id": "other"}}
        with TestClient(app) as c:
            r = c.post("/api/scenarios/validate", json=payload)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body.get("ok"))
        self.assertTrue(any("mode_id_mismatch" in e for e in (body.get("errors") or [])))

