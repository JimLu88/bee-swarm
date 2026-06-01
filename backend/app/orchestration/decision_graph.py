"""
LangGraph: triage -> Send fan-out (one task per dept) -> deferred finalize.

Parallel branches merge ``reports`` via ``operator.add``; ``finalize`` uses ``defer=True``
so it runs once after all ``dept_worker`` tasks complete.
"""

from __future__ import annotations

import asyncio
import operator
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

if TYPE_CHECKING:
    from ..models import DecisionSummary

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send


class DecisionGraphState(TypedDict, total=False):
    decision_id: str
    task: str
    mode_id: str
    mode_label: str
    departments: list[str]
    debate_rounds: int  # v1.2 N 轮辩论, default 1
    # v10 关键修复: 这些字段必须声明为 channel, 否则 LangGraph 在节点间传递时丢弃,
    # 导致 tier/档位 永远拿不到 → 默认 "A" → 经济档/中等档失效, 永远跑最贵的旗舰。
    tier: str  # A 旗舰 / B 便宜云 / C 本地 ollama
    task_level: str
    task_urgency: str
    dispatcher_context: str
    dispatcher_notes: str
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
    # v6-X 多模态: 整场共享, route_depts 透传到每个 dept_worker.
    images: list[str]
    # v6-X-5 一次性图像摘要 (vision LLM 跑一次, 后续 staff/瞎子模型读文本)
    image_summary: str


_compiled_graph: Any = None
_sqlite_conn: Any = None
_compile_lock: asyncio.Lock | None = None


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _sqlite_checkpoint_path() -> Path:
    from ..settings import settings

    raw = settings.hsemas_graph_checkpoint_sqlite_path
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else _backend_root() / p
    return _backend_root() / "data" / "langgraph_checkpoints.sqlite3"


def _compile_graph(checkpointer: Any) -> Any:
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

        # v6-X-5 图像摘要: 有图就用 image_summary_model[tier] 跑一次 vision, 后续节点都读这段文字.
        image_summary = ""
        images = list(state.get("images") or [])
        if images:
            from ..decision_engine import build_image_summary
            tier = str(state.get("tier") or "A").upper()
            try:
                image_summary = await build_image_summary(images=images, tier=tier, task=state["task"])
                bus.publish(StreamEvent(
                    type="image_summary_ready",
                    decision_id=state["decision_id"],
                    payload={"chars": len(image_summary), "image_count": len(images)},
                ))
            except Exception as e:
                image_summary = f"[图像摘要失败: {e}]"

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
            "image_summary": image_summary,
        }

    def route_depts(state: DecisionGraphState) -> list[Send]:
        depts = list(state.get("departments") or [])
        dept_briefs = dict(state.get("dept_briefs") or {})
        notes = str(state.get("notes") or "")
        lvl = str(state.get("lvl") or "")
        urg = str(state.get("urg") or "")
        images = list(state.get("images") or [])
        image_summary = str(state.get("image_summary") or "")
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
                    "debate_rounds": int(state.get("debate_rounds") or 1),
                    "tier": str(state.get("tier") or "A"),
                    "images": images,
                    "image_summary": image_summary,
                },
            )
            for d in depts
        ]

    async def dept_worker(state: DecisionGraphState) -> dict[str, Any]:
        """v1.2 N 轮辩论 + v6-W 本地档限流."""
        from ..decision_engine import _run_dept, _LOCAL_TIER_SEMAPHORE
        from ..stream_bus import bus
        from ..models import StreamEvent

        d = str(state.get("dept") or "")
        notes = str(state.get("dispatcher_notes") or state.get("notes") or "")
        lvl = str(state.get("task_level") or state.get("lvl") or "")
        urg = str(state.get("task_urgency") or state.get("urg") or "")
        ctx = str(state.get("dispatcher_context") or "")
        rounds = int(state.get("debate_rounds") or 1)
        tier = str(state.get("tier") or "A").upper()
        decision_id = state["decision_id"]
        # v6-X 多模态: head 在第 1 轮收原图; staff/瞎子模型读 image_summary 文字.
        images = list(state.get("images") or [])
        image_summary = str(state.get("image_summary") or "")
        # 图像摘要作为 ctx 附加, 让所有 staff 都能"读到"图
        if image_summary:
            ctx = f"{ctx}\n\n[用户上传图片摘要]\n{image_summary}".strip()

        last_report = None
        last_consensus = ""
        for r_idx in range(rounds):
            if rounds > 1:
                bus.publish(StreamEvent(
                    type="debate_round_start",
                    decision_id=decision_id,
                    payload={"dept": d, "round": r_idx + 1, "total": rounds},
                ))
            # v6-W 本地档限流: tier=C 时同时只跑 2 个 dept (ollama 单实例并发弱)
            if tier == "C":
                async with _LOCAL_TIER_SEMAPHORE:
                    last_report = await _run_dept(
                        decision_id, state["mode_id"], d, state["task"],
                        dispatcher_context=ctx, dispatcher_notes=notes,
                        task_level=lvl, task_urgency=urg, tier=tier,
                        images=images,
                    )
            else:
                last_report = await _run_dept(
                    decision_id, state["mode_id"], d, state["task"],
                    dispatcher_context=ctx, dispatcher_notes=notes,
                    task_level=lvl, task_urgency=urg, tier=tier,
                    images=images,
                )
            # 简单早停: 跟上一轮共识完全一样 → 收敛
            if r_idx >= 1 and last_report.consensus.strip() == last_consensus.strip():
                bus.publish(StreamEvent(
                    type="debate_converged",
                    decision_id=decision_id,
                    payload={"dept": d, "rounds_used": r_idx + 1, "rounds_planned": rounds},
                ))
                break
            last_consensus = last_report.consensus
            # 下轮的上下文: 本轮 conflicts + 上一轮的共识
            if r_idx + 1 < rounds and last_report.conflicts:
                ctx = (
                    f"{ctx}\n\n[上一轮({r_idx+1}/{rounds})本部门的共识] {last_report.consensus}\n"
                    f"[上一轮分歧] " + "; ".join(last_report.conflicts) + "\n"
                    "请基于此重新评估, 尽量缩小分歧."
                )

        return {"reports": [last_report.model_dump()]}

    async def node_finalize(state: DecisionGraphState) -> dict[str, Any]:
        from ..decision_engine import finalize_decision_bundle
        from ..models import DeptLeadReport

        raw = list(state.get("reports") or [])
        order = list(state.get("departments") or [])
        rank = {str(dept): i for i, dept in enumerate(order)}
        raw_sorted = sorted(raw, key=lambda row: rank.get(str(row.get("dept")), 10_000))

        reports = [DeptLeadReport(**r) for r in raw_sorted]
        # v6-W-fix CEO 之前看不到图片 → 把图像摘要拼进 task 给 CEO (之前只给了部门 ctx).
        _task = state["task"]
        _img_sum = str(state.get("image_summary") or "")
        if _img_sum and "[用户上传图片摘要]" not in _task:
            _task = f"{_task}\n\n[用户上传图片摘要]\n{_img_sum}"
        summary = await finalize_decision_bundle(
            decision_id=state["decision_id"],
            task=_task,
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
    # Per-decision thread id = decision_id (resume / inspect checkpoint).
    return workflow.compile(checkpointer=checkpointer)


async def _make_checkpointer() -> Any:
    from ..settings import settings

    if settings.hsemas_graph_checkpoint_backend != "sqlite":
        return MemorySaver()

    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    global _sqlite_conn
    path = _sqlite_checkpoint_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(path))
    _sqlite_conn = conn
    return AsyncSqliteSaver(conn)


async def ensure_compiled_graph() -> Any:
    """Compile graph once with MemorySaver or AsyncSqliteSaver (matches ``ainvoke`` async checkpoint API)."""
    global _compiled_graph, _compile_lock
    if _compile_lock is None:
        _compile_lock = asyncio.Lock()
    async with _compile_lock:
        if _compiled_graph is not None:
            return _compiled_graph
        cp = await _make_checkpointer()
        _compiled_graph = _compile_graph(cp)
        return _compiled_graph


async def shutdown_checkpoint_runtime() -> None:
    """Close SQLite checkpoint connection (e.g. FastAPI lifespan); next ``ensure_compiled_graph`` reconnects."""
    global _compiled_graph, _sqlite_conn
    if _sqlite_conn is not None:
        await _sqlite_conn.close()
        _sqlite_conn = None
    _compiled_graph = None


def orchestration_checkpoint_path_fields() -> dict[str, Any]:
    """Relative path hints for ``/api/status`` when SQLite checkpoints are configured (no secrets)."""
    from ..settings import settings

    if settings.hsemas_graph_checkpoint_backend != "sqlite":
        return {}
    p = _sqlite_checkpoint_path()
    try:
        rel = p.relative_to(_backend_root())
        return {"checkpoint_sqlite_relative": rel.as_posix()}
    except ValueError:
        return {"checkpoint_sqlite_filename": p.name}


async def invoke_decision_graph(
    *,
    decision_id: str,
    task: str,
    mode_id: str,
    mode_label: str,
    departments: list[str],
    debate_rounds: int = 1,
    tier: str = "A",
    images: list[str] | None = None,
) -> "DecisionSummary":
    """Run compiled graph; raises if finalize did not populate ``summary``."""
    from ..models import DecisionSummary

    app = await ensure_compiled_graph()
    out = await app.ainvoke(
        {
            "decision_id": decision_id,
            "task": task,
            "mode_id": mode_id,
            "mode_label": mode_label,
            "departments": departments,
            "debate_rounds": int(debate_rounds or 1),
            "tier": str(tier or "A").upper(),
            "images": list(images or []),
        },
        config={"configurable": {"thread_id": decision_id}},
    )
    summary_dict = out.get("summary") or {}
    return DecisionSummary(**summary_dict)
