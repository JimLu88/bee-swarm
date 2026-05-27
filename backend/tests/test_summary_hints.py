"""rag/summary_hints rollup (shared by compact + DecisionSummary.rag_aggregate)."""

from __future__ import annotations

import unittest

from app.models import DeptLeadReport
from app.rag.summary_hints import compact_rag_hint_from_dept_rows


class SummaryHintsTests(unittest.TestCase):
    def test_accept_dept_lead_report_models(self) -> None:
        r = DeptLeadReport(
            dept="finance",
            consensus="c",
            conflicts=[],
            confidence_score=0.5,
            dissent_intensity=0.2,
            debate_log_id="x",
            rag_retrieval_meta={"total_chunks": 2, "rag_backend": "simulated"},
        )
        agg = compact_rag_hint_from_dept_rows([r])
        self.assertIsNotNone(agg)
        assert agg is not None
        self.assertEqual(agg["chunks_sum_across_depts"], 2)


if __name__ == "__main__":
    unittest.main()
