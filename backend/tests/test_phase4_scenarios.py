"""Phase 4: YAML scenario overlays, gene seeds, DSPy-style evolve (stub under simulated LLM)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.gene_defaults import build_initial_gene_prompt
from app.gene_evolve import evolve_gene_prompt
from app.modes import get_mode
from app.scenario_loader import load_scenario_dict, list_scenario_yaml_basenames


class ScenarioLoaderTests(unittest.TestCase):
    def test_list_includes_repo_yaml(self) -> None:
        names = list_scenario_yaml_basenames()
        self.assertIn("program_management.yaml", names)
        self.assertIn("family_doctor.yaml", names)
        self.assertIn("stock_trading.yaml", names)
        self.assertIn("travel_planning.yaml", names)

    def test_load_program_management(self) -> None:
        d = load_scenario_dict("program_management")
        self.assertIsInstance(d, dict)
        assert d is not None
        self.assertEqual(d.get("mode_id"), "program_management")
        self.assertIn("gene_seeds", d)


class ModesYamlOverlayTests(unittest.TestCase):
    def test_get_mode_merges_yaml(self) -> None:
        m = get_mode("program_management")
        self.assertEqual(m.scenario_yaml, "program_management.yaml")
        self.assertIn("YAML", m.label)
        self.assertTrue(m.scenario_description)
        self.assertIn("架构部（模板）", m.department_labels.get("arch", ""))

    def test_stock_trading_yaml_applied(self) -> None:
        m = get_mode("stock_trading")
        self.assertEqual(m.scenario_yaml, "stock_trading.yaml")
        self.assertTrue(m.scenario_description)
        self.assertIn("模板", m.department_labels.get("macro_policy", ""))


class GeneDefaultsTests(unittest.TestCase):
    def test_seed_appended_for_arch(self) -> None:
        p = build_initial_gene_prompt("program_management", "arch")
        self.assertIn("场景模板补充", p)
        self.assertIn("假设", p)

    def test_no_seed_for_dept_without_yaml_seed(self) -> None:
        p = build_initial_gene_prompt("program_management", "ui")
        self.assertNotIn("场景模板补充", p)


class GeneEvolveAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_evolve_under_simulated_provider(self) -> None:
        from app.settings_llm_rag import llm_rag_settings

        with patch.object(llm_rag_settings, "llm_provider", "simulated"):
            text, meta = await evolve_gene_prompt(
                mode_id="stock_trading",
                dept="macro_policy",
                active_prompt="你是宏观政策部 Lead。",
                task_sample="美联储加息路径对新兴市场影响",
            )
        self.assertIn("模拟进化", text)
        self.assertEqual(meta.get("provider"), "simulated")


class GeneEvolveGateHttpTests(unittest.TestCase):
    def test_gate_field_present(self) -> None:
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as c:
            r = c.post("/api/genes/program_management/arch/evolve", json={"task_sample": "t", "save_shadow": False, "require_gate": True, "gate_trials": 3})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("gate", body)
