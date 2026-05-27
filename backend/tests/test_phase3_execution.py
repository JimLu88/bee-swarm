"""Phase 3: deterministic QA bundle, executor plan, optional CLI hints; vision web search gate."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.execution.bundle import build_execution_bundle
from app.models import DeptLeadReport, HeatmapCell
from app.settings_llm_rag import llm_rag_settings
from app.search.benchmark_web import fetch_benchmark_web_chunks


def _report(dept: str, consensus: str = "ok") -> DeptLeadReport:
    return DeptLeadReport(
        dept=dept,  # type: ignore[arg-type]
        consensus=consensus,
        conflicts=[],
        confidence_score=0.75,
        dissent_intensity=0.25,
        debate_log_id=f"log-{dept}",
    )


def _heat(dept: str, alert: str = "green") -> HeatmapCell:
    return HeatmapCell(
        dept=dept,  # type: ignore[arg-type]
        confidence_score=0.75,
        dissent_intensity=0.25,
        alert=alert,  # type: ignore[arg-type]
        debate_log_id=f"log-{dept}",
    )


class ExecutionBundleTests(unittest.TestCase):
    def test_qa_passes_when_all_depts_present(self) -> None:
        reports = [_report("finance")]
        heat = [_heat("finance")]
        b = build_execution_bundle(
            expected_depts=["finance"],
            task="t",
            ceo_decision="ceo",
            dept_reports=reports,
            heatmap=heat,
        )
        self.assertTrue(b["qa_sandbox"]["ok"])
        self.assertIn("executor", b)
        self.assertIn("suggested_cli_probe", b["executor"])

    def test_qa_fails_when_dept_missing(self) -> None:
        reports = [_report("finance")]
        heat = [_heat("finance")]
        b = build_execution_bundle(
            expected_depts=["finance", "arch"],
            task="t",
            ceo_decision="ceo",
            dept_reports=reports,
            heatmap=heat,
        )
        self.assertFalse(b["qa_sandbox"]["ok"])
        hard = b["qa_sandbox"].get("hard_checks") or []
        names = [h.get("name") for h in hard if isinstance(h, dict)]
        self.assertIn("all_depts_present", names)


class BenchmarkWebSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_env_returns_empty(self) -> None:
        with patch.object(llm_rag_settings, "benchmark_web_search", False):
            chunks, meta = await fetch_benchmark_web_chunks("query", limit=2)
        self.assertEqual(chunks, [])
        self.assertEqual(meta.get("enabled"), False)


if __name__ == "__main__":
    unittest.main()
