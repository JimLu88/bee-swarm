"""Phase 5: YAML-defined extra modes from backend/scenarios/extra/."""

from __future__ import annotations

import unittest

from app.extra_mode_loader import load_extra_modes, list_extra_mode_yaml_basenames
from app.modes import MODES, get_mode, list_extra_mode_ids, list_modes


class ExtraModeLoaderTests(unittest.TestCase):
    def test_builtin_skip_and_parse(self) -> None:
        modes = load_extra_modes(builtin_mode_ids=frozenset(["program_management"]))
        self.assertNotIn("program_management", modes)

    def test_extra_dir_lists_generic(self) -> None:
        names = list_extra_mode_yaml_basenames()
        self.assertIn("generic_consulting.yaml", names)
        self.assertIn("ops_review.yaml", names)


class ExtraModesIntegrationTests(unittest.TestCase):
    def test_list_extra_ids(self) -> None:
        ids = list_extra_mode_ids()
        self.assertIn("generic_consulting", ids)
        self.assertIn("ops_review", ids)

    def test_list_modes_includes_extra(self) -> None:
        ids = [m.mode_id for m in list_modes()]
        self.assertEqual(len(ids), len(MODES) + len(list_extra_mode_ids()))
        self.assertEqual(len(list_extra_mode_ids()), 2)
        self.assertIn("generic_consulting", ids)
        self.assertIn("ops_review", ids)

    def test_get_mode_resolves_extra(self) -> None:
        m = get_mode("generic_consulting")
        self.assertEqual(m.mode_id, "generic_consulting")
        self.assertGreaterEqual(len(m.departments), 3)
        self.assertIn("business", m.departments)
        # Root scenarios/generic_consulting.yaml overlays label
        self.assertIn("叠加", m.label)

    def test_unknown_mode_falls_back(self) -> None:
        m = get_mode("totally_unknown_mode_xyz")
        self.assertEqual(m.mode_id, "program_management")

    def test_ops_review_root_overlay(self) -> None:
        m = get_mode("ops_review")
        self.assertEqual(m.mode_id, "ops_review")
        self.assertIn("叠加", m.label)
        self.assertIn("叠加", m.department_labels.get("finance", ""))

    def test_gene_seed_merge_overlay(self) -> None:
        m = get_mode("generic_consulting")
        self.assertIn("Capex", (m.gene_seeds or {}).get("finance", ""))
