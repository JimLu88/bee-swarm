"""Dept catalog for YAML authoring."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.catalog import list_dept_names
from app.main import app


class CatalogTests(unittest.TestCase):
    def test_list_dept_names_nonempty(self) -> None:
        names = list_dept_names()
        self.assertGreater(len(names), 10)
        self.assertIn("benchmark", names)
        self.assertIn("arch", names)

    def test_get_catalog_http(self) -> None:
        with TestClient(app) as c:
            r = c.get("/api/catalog/dept-names")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body.get("count"), len(body.get("dept_names") or []))
        self.assertIn("security", body.get("dept_names") or [])
