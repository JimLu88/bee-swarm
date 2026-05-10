import unittest


class DecisionGraphTests(unittest.TestCase):
    def test_graph_compiles(self) -> None:
        from app.orchestration.decision_graph import get_decision_graph

        g = get_decision_graph()
        self.assertIsNotNone(g)


class DecisionGraphAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_invoke_single_department_smoke(self) -> None:
        from app.orchestration.decision_graph import invoke_decision_graph

        s = await invoke_decision_graph(
            decision_id="dec-graph-smoke",
            task="graph smoke",
            mode_id="program_management",
            mode_label="项目管理",
            departments=["finance"],
        )
        self.assertEqual(s.decision_id, "dec-graph-smoke")
        self.assertEqual(len(s.dept_reports), 1)
        self.assertEqual(s.dept_reports[0].dept, "finance")
        self.assertTrue(s.ceo_decision)
        self.assertIsNotNone(s.dispatcher)

    async def test_invoke_two_depts_reports_follow_department_order(self) -> None:
        from app.orchestration.decision_graph import invoke_decision_graph

        s = await invoke_decision_graph(
            decision_id="dec-graph-two",
            task="multi dept order",
            mode_id="program_management",
            mode_label="项目管理",
            departments=["arch", "logic"],
        )
        self.assertEqual(len(s.dept_reports), 2)
        self.assertEqual([r.dept for r in s.dept_reports], ["arch", "logic"])
