"""
LangGraph: triage -> Send fan-out (one task per dept) -> deferred finalize.

Parallel branches merge ``reports`` via ``operator.add``; ``finalize`` uses ``defer=True``
so it runs once after all ``dept_worker`` tasks complete.
"""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

if TYPE_CHECKING:
    from ..models import DecisionSummary

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send


class DecisionGraphState(TypedDict, total=False):
    decision_id: str
    task: str
    mode_id: str
    mode_label: str
    departments: list[str]
    dsp: dict[str, Any]
    dsp_meta: dict[str, Any]
    notes: str
    lvl: str
    urg: str
    dept_briefs: dict[str, str]
    # Per Send(payload): which department this parallel branch runs.
    dept: str
    reports: Annotated[list[dict[str, Any]], operator.add]
    summary: dict[str, Any]


_compiled_graph: Any = None


def _compile_graph() -> Any:
    workflow = StateGraph(DecisionGraphState)

    async def node_triage(state: DecisionGraphState) -> dict[str, Any]:
        from ..dispatcher import run_dispatcher
        from ..models import StreamEvent
        from ..stream_bus import bus

        depts = list(state["departments"])
        dsp = run_dispatcher(task=state["task"], departments=depts)
        dept_briefs_raw = dsp.get("dept_briefs") or {}
        dept_briefs = {str(k): str(v) for k, v in dict(dept_briefs_raw).items()}
        brief_preview = {
            d: str(dept_briefs.get(d, ""))[:400] + ("…" if len(str(dept_briefs.get(d, ""))) > 400 else "")
            for d in depts
        }
        dsp_meta: dict[str, Any] = {
            "level": dsp.get("level"),
            "urgency": dsp.get("urgency"),
            "task_chars": dsp.get("task_chars"),
            "notes": dsp.get("notes"),
            "version": dsp.get("version"),
            "department_count": len(depts),
            "dept_brief_lens": {d: len(str(dept_briefs.get(d, ""))) for d in depts},
            "dept_brief_preview": brief_preview,
        }
        dispatcher_payload_preview = {
            "level": dsp.get("level"),
            "urgency": dsp.get("urgency"),
            "task_chars": dsp.get("task_chars"),
            "notes": dsp.get("notes"),
            "version": dsp.get("version"),
            "dept_brief_preview": brief_preview,
        }
        bus.publish(StreamEvent(type="dispatcher_ready", decision_id=state["decision_id"], payload=dispatcher_payload_preview))
        bus.publish(
            StreamEvent(
                type="fanout_started",
                decision_id=state["decision_id"],
                payload={"depts": depts, "count": len(depts)},
            )
        )
        return {
            "dsp": dsp,
            "dsp_meta": dsp_meta,
            "notes": str(dsp.get("notes") or ""),
            "lvl": str(dsp.get("level") or ""),
            "urg": str(dsp.get("urgency") or ""),
            "dept_briefs": dept_briefs,
        }

    def route_depts(state: DecisionGraphState) -> list[Send]:
        depts = list(state.get("departments") or [])
        dept_briefs = dict(state.get("dept_briefs") or {})
        notes = str(state.get("notes") or "")
        lvl = str(state.get("lvl") or "")
        urg = str(state.get("urg") or "")
        # Send(arg) is the sole input to dept_worker — include everything _run_dept needs.
        return [
            Send(
                "dept_worker",
                {
                    "decision_id": state["decision_id"],
                    "task": state["task"],
                    "mode_id": state["mode_id"],
                    "dept": d,
                    "dispatcher_context": str(dept_briefs.get(d, "")),
                    "dispatcher_notes": notes,
                    "task_level": lvl,
                    "task_urgency": urg,
                },
            )
            for d in depts
        ]

    async def dept_worker(state: DecisionGraphState) -> dict[str, Any]:
        from ..decision_engine import _run_dept

        d = str(state.get("dept") or "")
        notes = str(state.get("dispatcher_notes") or state.get("notes") or "")
        lvl = str(state.get("task_level") or state.get("lvl") or "")
        urg = str(state.get("task_urgency") or state.get("urg") or "")
        ctx = str(state.get("dispatcher_context") or "")

        report = await _run_dept(
            state["decision_id"],
            state["mode_id"],
            d,
            state["task"],
            dispatcher_context=ctx,
            dispatcher_notes=notes,
            task_level=lvl,
            task_urgency=urg,
        )
        return {"reports": [report.model_dump()]}

    def node_finalize(state: DecisionGraphState) -> dict[str, Any]:
        from ..decision_engine import finalize_decision_bundle
        from ..models import DeptLeadReport

        raw = list(state.get("reports") or [])
        order = list(state.get("departments") or [])
        rank = {str(dept): i for i, dept in enumerate(order)}
        raw_sorted = sorted(raw, key=lambda row: rank.get(str(row.get("dept")), 10_000))

        reports = [DeptLeadReport(**r) for r in raw_sorted]
        summary = finalize_decision_bundle(
            decision_id=state["decision_id"],
            task=state["task"],
            mode_id=state["mode_id"],
            mode_label=state["mode_label"],
            dsp_meta=dict(state.get("dsp_meta") or {}),
            reports=reports,
        )
        return {"summary": summary.model_dump()}

    workflow.add_node("triage", node_triage)
    workflow.add_node("dept_worker", dept_worker)
    workflow.add_node("finalize", node_finalize, defer=True)

    workflow.add_edge(START, "triage")
    workflow.add_conditional_edges("triage", route_depts, ["dept_worker"])
    workflow.add_edge("dept_worker", "finalize")
    workflow.add_edge("finalize", END)
    return workflow.compile()


def get_decision_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _compile_graph()
    return _compiled_graph


async def invoke_decision_graph(
    *,
    decision_id: str,
    task: str,
    mode_id: str,
    mode_label: str,
    departments: list[str],
) -> DecisionSummary:
    """Run compiled graph; raises if finalize did not populate ``summary``."""
    from ..models import DecisionSummary

    app = get_decision_graph()
    out = await app.ainvoke(
        {
            "decision_id": decision_id,
            "task": task,
            "mode_id": mode_id,
            "mode_label": mode_label,
            "departments": departments,
        }
    )
    summary_dict = out.get("summary") or {}
    return DecisionSummary(**summary_dict)
