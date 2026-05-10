from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .decision_engine import run_decision
from pathlib import Path

from .decision_memory import DecisionMemory
from .memory_compact import compact_decision_row
from .config_store import ConfigStore
from .gene_store import GeneStore
from .modes import list_modes
from .models import DecisionStartRequest, SandboxExecRequest
from .settings import settings
from .stream_bus import bus
from .shadow_testing import ShadowTester
from .status import get_status


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/api/status")
async def status() -> dict:
    return await get_status()


@app.get("/api/debug/graph-state/{decision_id}")
async def debug_graph_state(decision_id: str) -> dict:
    """LangGraph MemorySaver snapshot for ``thread_id`` (= decision_id). Disabled unless HSEMAS_EXPOSE_GRAPH_STATE=true."""
    if not settings.hsemas_expose_graph_state:
        raise HTTPException(status_code=404, detail="graph_state_disabled")
    from .graph_debug import sanitize_checkpoint_values
    from .orchestration.decision_graph import get_decision_graph

    g = get_decision_graph()
    snap = await g.aget_state({"configurable": {"thread_id": decision_id}})
    vals = snap.values
    raw = dict(vals) if vals is not None else None
    return {
        "thread_id": decision_id,
        "next": list(snap.next) if snap.next else [],
        "values": sanitize_checkpoint_values(raw),
    }


@app.post("/api/sandbox/exec", response_model=None)
async def sandbox_exec(body: SandboxExecRequest) -> dict | JSONResponse:
    """Optional Phase 3: run allow-listed binary under backend/, no shell splitting."""
    from .execution.safe_shell import run_allowlisted

    out = await run_allowlisted([str(a) for a in body.argv])
    if out.get("ok"):
        return out  # type: ignore[return-value]

    err = str(out.get("error") or "")
    status_map = {
        "sandbox_disabled": 503,
        "allowlist_empty": 503,
        "denylisted_binary": 403,
        "not_on_allowlist": 403,
        "executable_not_found": 404,
        "timeout": 504,
    }
    code = status_map.get(err, 400)
    return JSONResponse(status_code=code, content=out)  # type: ignore[arg-type]

@app.get("/api/modes")
def modes() -> list[dict]:
    return [m.model_dump() for m in list_modes()]

@app.get("/api/memory/{mode_id}")
def memory_list(mode_id: str, limit: int = 50, compact: bool = False) -> list[dict]:
    mem = DecisionMemory(Path(__file__).resolve().parent.parent / "data")
    rows = mem.list_summaries(mode_id=mode_id, limit=limit)
    if compact:
        return [compact_decision_row(r) for r in rows]
    return rows


@app.get("/api/memory/{mode_id}/decision/{decision_id}")
def memory_one(mode_id: str, decision_id: str) -> dict:
    """Full persisted summary for one decision (loads from JSONL)."""
    mem = DecisionMemory(Path(__file__).resolve().parent.parent / "data")
    row = mem.get_by_decision_id(mode_id=mode_id, decision_id=decision_id)
    if row is None:
        raise HTTPException(status_code=404, detail="decision_not_found")
    return row

@app.get("/api/config/{mode_id}")
def config_get(mode_id: str) -> dict:
    cs = ConfigStore(Path(__file__).resolve().parent.parent / "data")
    return cs.get_config(mode_id=mode_id)

@app.post("/api/config/{mode_id}")
async def config_set(mode_id: str, body: dict) -> dict:
    cs = ConfigStore(Path(__file__).resolve().parent.parent / "data")
    return cs.set_config(mode_id=mode_id, cfg=body)

@app.post("/api/rag/ingest/{mode_id}")
async def rag_ingest(mode_id: str, body: dict) -> dict:
    """
    Phase 2 MVP ingest endpoint.
    body: { items: [{chunk_id,title,content,meta?}, ...] }
    """
    from .settings_llm_rag import llm_rag_settings
    from .rag.local_store import LocalRagStore
    from .rag.qdrant_store import IngestItem, store as qdrant_store

    items_in = list(body.get("items") or [])
    items: list[IngestItem] = []
    for it in items_in[:200]:
        meta_in = dict(it.get("meta") or {})
        source_url = it.get("source_url") or meta_in.get("source_url")
        if source_url:
            meta_in["source_url"] = str(source_url)
        items.append(
            IngestItem(
                chunk_id=str(it.get("chunk_id") or ""),
                title=str(it.get("title") or ""),
                content=str(it.get("content") or ""),
                meta=meta_in,
            )
        )
    if llm_rag_settings.rag_backend == "local":
        n = LocalRagStore(Path(__file__).resolve().parent.parent / "data").upsert(
            mode_id=mode_id,
            items=[
                {"chunk_id": it.chunk_id, "title": it.title, "content": it.content, "source_url": (it.meta or {}).get("source_url"), "meta": it.meta}
                for it in items
            ],
        )
        return {"upserted": n, "backend": "local"}

    if llm_rag_settings.rag_backend != "qdrant":
        # simulated: accept request but no-op, so UI can stay stable without Docker.
        return {"upserted": 0, "backend": llm_rag_settings.rag_backend, "note": "no-op"}

    try:
        n = qdrant_store.upsert(mode_id=mode_id, items=items)
        return {"upserted": n, "backend": "qdrant"}
    except Exception as e:
        return {
            "error": "qdrant_unavailable",
            "detail": repr(e),
            "hint": "Install and run Qdrant (Docker), or set RAG_BACKEND=local to use SQLite-FTS.",
        }

@app.get("/api/rag/search/{mode_id}")
def rag_search(mode_id: str, q: str, k: int = 5, dept: str | None = None) -> list[dict]:
    """Delegates to RagRetriever (same logic as decision pipeline: hybrid FTS optional when qdrant)."""
    from .rag.retriever import retriever

    d = dept or "finance"
    hits = retriever.retrieve(mode_id=mode_id, dept=d, task=q, k=k)
    return [c.__dict__ for c in hits]

@app.get("/api/genes/{mode_id}/{dept}")
def genes_get_active(mode_id: str, dept: str) -> dict:
    gs = GeneStore(Path(__file__).resolve().parent.parent / "data")
    rec = gs.get_active(mode_id=mode_id, dept=dept)
    if rec is None:
        # Default minimal prompt; in Phase 2 this will become per-role (A/B/C/Lead) and editable in UI.
        rec = gs.set_active(mode_id=mode_id, dept=dept, prompt=f"你是 {dept} 部门的 Lead。请给出可执行建议，并输出 confidence_score 与 dissent_intensity。")
    return rec

@app.post("/api/genes/{mode_id}/{dept}")
async def genes_set_active(mode_id: str, dept: str, body: dict) -> dict:
    prompt = str(body.get("prompt") or "")
    if not prompt.strip():
        return {"error": "prompt_required"}
    gs = GeneStore(Path(__file__).resolve().parent.parent / "data")
    return gs.set_active(mode_id=mode_id, dept=dept, prompt=prompt)

@app.post("/api/genes/{mode_id}/{dept}/shadow")
async def genes_add_shadow(mode_id: str, dept: str, body: dict) -> dict:
    prompt = str(body.get("prompt") or "")
    if not prompt.strip():
        return {"error": "prompt_required"}
    gs = GeneStore(Path(__file__).resolve().parent.parent / "data")
    return gs.add_shadow(mode_id=mode_id, dept=dept, prompt=prompt)

@app.get("/api/genes/{mode_id}/{dept}/shadow")
def genes_list_shadow(mode_id: str, dept: str, limit: int = 20) -> list[dict]:
    gs = GeneStore(Path(__file__).resolve().parent.parent / "data")
    return gs.list_shadows(mode_id=mode_id, dept=dept, limit=limit)

@app.get("/api/shadow/{mode_id}/{dept}/{shadow_version}")
def shadow_status(mode_id: str, dept: str, shadow_version: int, trials: int = 3) -> dict:
    st = ShadowTester(Path(__file__).resolve().parent.parent / "data")
    verdict = st.should_promote(mode_id=mode_id, dept=dept, shadow_version=shadow_version, trials=trials)
    scores = st.list_scores(mode_id=mode_id, dept=dept, shadow_version=shadow_version, limit=50)
    return {"verdict": {"promote": verdict.promote, "reason": verdict.reason, "shadow_version": verdict.shadow_version}, "scores": scores}


@app.post("/api/decision/start")
async def decision_start(req: DecisionStartRequest) -> dict[str, str]:
    # Run in background so caller can connect websocket immediately.
    decision_id = "dec-" + uuid.uuid4().hex[:12]

    async def _bg() -> None:
        await run_decision(decision_id=decision_id, task=req.task, mode_id=req.mode_id)

    asyncio.create_task(_bg())
    return {"decision_id": decision_id}


@app.websocket("/api/decision/stream/{decision_id}")
async def decision_stream(ws: WebSocket, decision_id: str) -> None:
    await ws.accept()
    try:
        async for event in bus.subscribe(decision_id):
            await ws.send_text(json.dumps(event.model_dump(), ensure_ascii=False))
    except WebSocketDisconnect:
        return

