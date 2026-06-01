from __future__ import annotations


def _bootstrap_tiktoken_plugins() -> None:
    """
    PyInstaller onefile: ``pkgutil.iter_modules(tiktoken_ext.__path__)`` often returns no
    modules, so ``tiktoken.registry`` never discovers ``tiktoken_ext.openai_public`` and
    ``get_encoding('cl100k_base')`` raises — LiteLLM then fails to import. Merge OpenAI's
    encoding constructors when the registry is empty or missing ``cl100k_base``.
    """
    try:
        import tiktoken.registry as reg
        import tiktoken_ext.openai_public as pub
    except Exception:
        return
    with reg._lock:
        if reg.ENCODING_CONSTRUCTORS is None:
            try:
                reg._find_constructors()
            except Exception:
                reg.ENCODING_CONSTRUCTORS = {}
        ec = reg.ENCODING_CONSTRUCTORS
        if ec is None:
            reg.ENCODING_CONSTRUCTORS = {}
            ec = reg.ENCODING_CONSTRUCTORS
        if ec.get("cl100k_base"):
            return
        for name, fn in pub.ENCODING_CONSTRUCTORS.items():
            ec.setdefault(name, fn)


_bootstrap_tiktoken_plugins()

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .decision_engine import run_decision
from .evolution_coordinator import coordinator_router
from .persona.team_api import router as team_router
from pathlib import Path

from .decision_memory import DecisionMemory
from .memory_compact import compact_decision_row
from .config_store import ConfigStore
from .gene_defaults import build_initial_gene_prompt
from .gene_evolve import evolve_gene_prompt
from .gene_store import GeneStore
from .catalog import list_dept_names
from .models import (
    DecisionStartRequest,
    DecisionEstimateRequest,
    DecisionEstimateResponse,
    PreflightRequest,
    DecisionFeedbackRequest,
    PriceCardResponse,
    PriceCardEntry,
    GeneEvolveRequest,
    GeneRegenerateSlotRequest,
    GenesBulkSaveRequest,
    GenesGenerateRequest,
    GenesTeamsSaveRequest,
    SandboxExecRequest,
    ScenarioRollbackRequest,
    ScenarioScaffoldRequest,
    ScenarioValidateRequest,
    ScenarioWriteRequest,
)
from .modes import list_modes, reload_mode_yaml_cache, resolve_mode
from .settings import settings
from .stream_bus import bus
from .shadow_testing import ShadowTester
from .status import get_status
from .hub_diagnostics import run_chat_probes, run_connectivity
from .hub_settings_store import (
    apply_merged_file,
    apply_stored_hub_on_startup,
    dept_routing_for_mode,
    hub_settings_path,
    load_hub_file,
    merge_put_with_existing,
    public_hub_view,
    save_hub_file,
)
from .runtime_paths import backend_data_dir


_DATA_DIR = backend_data_dir()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # v6 修脱节 #2: 启 APScheduler 让 P0-P16 evolvers 02:00 每天自动跑
    try:
        from .evolution_coordinator.coordinator import start_scheduler
        start_scheduler()
    except Exception:
        pass
    yield
    try:
        from .evolution_coordinator.coordinator import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    from .orchestration.decision_graph import shutdown_checkpoint_runtime

    await shutdown_checkpoint_runtime()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# bee_logs: JSONL 滚动日志 + /logs/* 端点 (蜂群侧, 给主程序自己也接上)
_log_router_ok = False
try:
    import sys as _bee_sys
    _bee_sys.path.insert(0, "D:/AI/observability")
    from bee_logs import setup_service_logging, log_router as _swarm_log_router  # type: ignore
    from pathlib import Path as _BeePath
    setup_service_logging("bee-swarm",
                          _BeePath(__file__).parent.parent / "data" / "logs")
    _log_router_ok = True
except Exception:
    pass

apply_stored_hub_on_startup()

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


# ============ v6-D 七剑客工具 (BeeServiceClient) ============
@app.get("/api/tools/list")
def tools_list(include_sensitive: bool = False) -> dict[str, Any]:
    from .tools import list_tools as _lt
    return {"tools": _lt(include_sensitive=include_sensitive)}


@app.get("/api/tools/healthcheck")
def tools_healthcheck() -> dict[str, Any]:
    from .tools import bee_clients as _bc
    return {"services": _bc.healthcheck()}


@app.post("/api/tools/call")
def tools_call(payload: dict[str, Any]) -> dict[str, Any]:
    """手动触发工具调用 (前端/调试用); allow_sensitive=true 才放敏感工具."""
    from .tools import execute_tool as _ex
    name = str(payload.get("tool", ""))
    args = payload.get("args") or {}
    allow_sensitive = bool(payload.get("allow_sensitive", False))
    return _ex(name, args if isinstance(args, dict) else {},
               allow_sensitive=allow_sensitive)


@app.get("/api/settings/hub")
def hub_settings_get(mode_id: str | None = None) -> dict[str, Any]:
    """Unified hub settings (masked secrets) for the business UI."""
    out: dict[str, Any] = {
        "settings": public_hub_view(),
        "persisted_file": hub_settings_path().is_file(),
        "hub_settings_path": str(hub_settings_path().resolve()),
    }
    mid = (mode_id or "").strip()
    if mid:
        try:
            out["dept_routing"] = dept_routing_for_mode(mid)
        except Exception as e:
            out["dept_routing"] = {"error": repr(e), "mode_id": mid}
    return out


@app.post("/api/settings/hub/diagnostics/connectivity")
async def hub_diagnostics_connectivity() -> dict[str, Any]:
    """Step 1: per-surface reachability (Qdrant, proxy, search, LLM key slots)."""
    return await run_connectivity()


@app.post("/api/settings/hub/diagnostics/chat")
async def hub_diagnostics_chat() -> dict[str, Any]:
    """Step 2: minimal chat completion per configured provider (may incur small cost)."""
    return await run_chat_probes()


@app.put("/api/settings/hub")
def hub_settings_put(body: dict[str, Any]) -> dict[str, Any]:
    """
    Merge JSON body into ``data/hub_settings.json`` and reload runtime LLM/RAG settings.
    Masked values (``***…``) are ignored so unchanged secrets stay in place.
    """
    if not settings.hsemas_hub_settings_write_enabled:
        raise HTTPException(status_code=404, detail="hub_settings_write_disabled")
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="expected_json_object")
    body = dict(body)
    if "llm_provider" in body and body["llm_provider"] not in (None, ""):
        lp = str(body["llm_provider"]).strip().lower()
        if lp not in ("simulated", "litellm"):
            raise HTTPException(
                status_code=422,
                detail="llm_provider 只能填写 litellm 或 simulated，不能填写店铺名、昵称或其它说明文字。",
            )
        body["llm_provider"] = lp
    merged = merge_put_with_existing(body, load_hub_file())
    save_hub_file(merged)
    apply_merged_file(merged)
    return {"ok": True, "settings": public_hub_view(), "hub_settings_path": str(hub_settings_path().resolve())}


@app.get("/api/status")
async def status() -> dict:
    return await get_status()


@app.get("/api/debug/graph-state/{decision_id}")
async def debug_graph_state(decision_id: str) -> dict:
    """LangGraph checkpoint snapshot for ``thread_id`` (= decision_id). Disabled unless HSEMAS_EXPOSE_GRAPH_STATE=true."""
    if not settings.hsemas_expose_graph_state:
        raise HTTPException(status_code=404, detail="graph_state_disabled")
    from .graph_debug import sanitize_checkpoint_values
    from .orchestration.decision_graph import ensure_compiled_graph

    g = await ensure_compiled_graph()
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


@app.get("/api/catalog/dept-names")
def catalog_dept_names() -> dict:
    """Authoring aid: valid ``DeptName`` values for ``scenarios/extra/*.yaml`` ``departments`` lists."""
    names = list_dept_names()
    return {"dept_names": names, "count": len(names)}

@app.post("/api/scenarios/validate")
def scenarios_validate(body: ScenarioValidateRequest) -> dict:
    """Phase 7: validate a would-be YAML file (root overlay or extra mode) without writing to disk."""
    from .scenario_authoring import validate_extra_mode, validate_root_overlay
    from .modes import MODES

    if body.kind == "root_overlay":
        v = validate_root_overlay(yaml_dict=body.yaml, mode_id=body.mode_id)
    else:
        v = validate_extra_mode(yaml_dict=body.yaml, builtin_mode_ids=frozenset(MODES.keys()))
    return {
        "ok": v.ok,
        "kind": v.kind,
        "errors": v.errors,
        "warnings": v.warnings,
        "normalized": v.normalized,
    }


@app.post("/api/scenarios/scaffold")
def scenarios_scaffold(body: ScenarioScaffoldRequest) -> dict:
    """Phase 7: generate a starter YAML string for a new extra mode."""
    from .scenario_authoring import scaffold_extra_mode_yaml

    return {"mode_id": body.mode_id, "yaml": scaffold_extra_mode_yaml(mode_id=body.mode_id)}


@app.post("/api/scenarios/write")
def scenarios_write(body: ScenarioWriteRequest) -> dict:
    """
    Phase 9: validate + write YAML to disk.
    - root_overlay -> backend/scenarios/{mode_id}.yaml
    - extra_mode   -> backend/scenarios/extra/{mode_id}.yaml
    Disabled unless HSEMAS_SCENARIO_WRITE_ENABLED=true.
    """
    if not settings.hsemas_scenario_write_enabled:
        raise HTTPException(status_code=404, detail="scenario_write_disabled")

    from .scenario_authoring import validate_extra_mode, validate_root_overlay
    from .scenario_files import HistoryEntry, append_history_log, compute_sha, load_text_if_exists, snapshot_to_history, target_path
    from .modes import MODES

    try:
        import yaml  # type: ignore
    except Exception:
        raise HTTPException(status_code=503, detail="yaml_unavailable")

    parsed = yaml.safe_load(body.yaml_text)
    if not isinstance(parsed, dict):
        return {"ok": False, "error": "yaml_not_a_map"}

    mode_id = body.mode_id
    if body.kind == "root_overlay":
        v = validate_root_overlay(yaml_dict=parsed, mode_id=mode_id)
    else:
        v = validate_extra_mode(yaml_dict=parsed, builtin_mode_ids=frozenset(MODES.keys()))
        # For extra modes, prefer declared mode_id.
        declared = str(parsed.get("mode_id") or "").strip()
        if declared:
            mode_id = declared

    if not v.ok:
        return {"ok": False, "kind": v.kind, "errors": v.errors, "warnings": v.warnings, "normalized": v.normalized}

    out_path = target_path(kind=body.kind, mode_id=mode_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    before_text = load_text_if_exists(out_path)
    if before_text is not None and not body.overwrite:
        return {"ok": False, "error": "file_exists", "path": str(out_path)}

    normalized_yaml = yaml.safe_dump(v.normalized, allow_unicode=True, sort_keys=False).strip() + "\n"
    before_snap = snapshot_to_history(mode_id=mode_id, kind=body.kind, label="before", text=before_text)
    after_snap = snapshot_to_history(mode_id=mode_id, kind=body.kind, label="after", text=normalized_yaml)
    out_path.write_text(normalized_yaml, encoding="utf-8")

    append_history_log(
        HistoryEntry(
            ts=time.strftime("%Y-%m-%d %H:%M:%S"),
            mode_id=mode_id,
            kind=body.kind,
            action="write",
            before_path=before_snap,
            after_path=after_snap,
            note=f"sha={compute_sha(normalized_yaml)}",
        )
    )

    if body.reload_modes and settings.hsemas_modes_yaml_reload_enabled:
        reload_mode_yaml_cache()

    return {
        "ok": True,
        "path": str(out_path),
        "kind": body.kind,
        "mode_id": mode_id,
        "sha": compute_sha(normalized_yaml),
        "reloaded": bool(body.reload_modes and settings.hsemas_modes_yaml_reload_enabled),
        "warnings": v.warnings,
    }


@app.get("/api/scenarios/history/{mode_id}")
def scenarios_history(mode_id: str, limit: int = 50) -> dict:
    """Phase 10: list scenario write/rollback events for one mode_id."""
    from .scenario_files import list_history

    return {"mode_id": mode_id, "items": list_history(mode_id=mode_id, limit=limit)}


@app.post("/api/scenarios/rollback")
def scenarios_rollback(body: ScenarioRollbackRequest) -> dict:
    """Phase 10: rollback scenario file to a saved snapshot under backend/scenarios/_history/{mode_id}/."""
    if not settings.hsemas_scenario_write_enabled:
        raise HTTPException(status_code=404, detail="scenario_write_disabled")

    from .scenario_files import HistoryEntry, append_history_log, compute_sha, load_text_if_exists, target_path

    out_path = target_path(kind=body.kind, mode_id=body.mode_id)
    # Only allow reading history under our history dir, and only for this mode_id.
    hp = Path(body.history_path)
    hist_root = Path(__file__).resolve().parent.parent / "scenarios" / "_history" / body.mode_id
    try:
        hp_rel = hp.resolve().relative_to(hist_root.resolve())
    except Exception:
        return {"ok": False, "error": "history_path_not_allowed"}

    snap_text = load_text_if_exists(hist_root / hp_rel)
    if snap_text is None:
        return {"ok": False, "error": "history_snapshot_missing"}

    before_text = load_text_if_exists(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(snap_text, encoding="utf-8")

    append_history_log(
        HistoryEntry(
            ts=time.strftime("%Y-%m-%d %H:%M:%S"),
            mode_id=body.mode_id,
            kind=body.kind,
            action="rollback",
            before_path=str(out_path) if before_text is not None else None,
            after_path=str(hist_root / hp_rel),
            note=f"sha={compute_sha(snap_text)}",
        )
    )

    if body.reload_modes and settings.hsemas_modes_yaml_reload_enabled:
        reload_mode_yaml_cache()

    return {"ok": True, "mode_id": body.mode_id, "kind": body.kind, "path": str(out_path), "sha": compute_sha(snap_text)}

@app.get("/api/modes/lookup/{mode_id}")
def modes_lookup(mode_id: str) -> dict:
    """Resolve a ``mode_id`` and report whether it came from built-ins, YAML extras, or fallback."""
    m, registry = resolve_mode(mode_id)
    mode_dict = m.model_dump()
    # v10 重新设计: 只合并"对本场景真正适用"的横切部门中文名, 不再无脑塞全部 6 个.
    #   - 通用视野拓展(每个场景都注入): UNIVERSAL_CROSSCUT_DEPTS = 外部·小众视角 / 破局思考
    #   - 技术专用(benchmark/xlab/security/arch): 只有当该场景自己 departments 里真的用到才显示
    # 避免"杭州吃什么"冒出 对标基准/安全合规/架构设计 这类技术部门。
    from .modes import CROSSCUTTING_DEPT_LABELS, UNIVERSAL_CROSSCUT_DEPTS
    own_labels = mode_dict.get("department_labels") or {}
    own_depts = set(own_labels.keys()) | set(mode_dict.get("departments") or [])
    applicable_cc = {
        k: v for k, v in CROSSCUTTING_DEPT_LABELS.items()
        if k in UNIVERSAL_CROSSCUT_DEPTS or k in own_depts
    }
    merged_labels = {**applicable_cc, **own_labels}
    mode_dict["department_labels"] = merged_labels
    return {
        "requested_mode_id": mode_id,
        "registry": registry,
        "fallback_to_program_management": registry == "fallback",
        "mode": mode_dict,
    }


@app.post("/api/modes/classify")
async def modes_classify(body: dict = Body(...)) -> dict:
    """v10: AI 先判断用户问题属于哪个场景. 返回 {matched, mode_id, mode_label}.
    matched=False → 没有合适场景, 前端提示是否新建自定义场景."""
    task = str((body or {}).get("task") or "").strip()
    if not task:
        return {"matched": False, "mode_id": None, "reason": "empty_task"}
    from .modes import list_modes
    from .llm.litellm_client import litellm_client
    from .llm.parsing import _extract_json
    from .llm.router import router as _router
    import os as _os
    modes = list_modes()
    valid = {m.mode_id: m.label for m in modes}
    menu = "\n".join(f"  {mid}: {label}" for mid, label in valid.items())
    sys_prompt = (
        "你是场景路由器。下面是所有可用咨询场景, 格式 `场景id: 中文说明`:\n"
        f"{menu}\n\n"
        "任务: 判断用户问题最适合哪个场景。请尽量从列表里挑一个最接近的场景id, "
        "只有当问题和所有场景都明显不沾边时才返回 null。\n"
        "示例(仅示范格式, mode_id 必须用上面列表里真实存在的):\n"
        '  『想去日本玩7天帮我规划行程』→ {"mode_id":"travel_planning","matched":true}\n'
        '  『孩子发烧两天没退要不要去医院』→ {"mode_id":"family_doctor","matched":true}\n'
        '  『推荐附近好吃的火锅店』→ {"mode_id":"dining_recommendation","matched":true}\n'
        '  『帮我写一首抒情诗』→ {"mode_id":null,"matched":false}\n'
        "只输出 JSON(不要任何解释、不要 markdown 代码块)。mode_id 必须严格来自上面列表。"
    )
    # 场景判断只是短文本归类 → 直接用本地模型最省事(免费/本地/不烧 API/不超时).
    # 优先级: BEE_CLASSIFY_MODEL 显式指定 > 备用链里的本地 ollama 模型 > 第一个 flash/lite 小模型 > 链首 > deepseek-v4-flash.
    model = _os.environ.get("BEE_CLASSIFY_MODEL", "").strip()
    if not model:
        try:
            from .persona.team_generator import _hub_or_instance_get
            chain = [m.strip() for m in (_hub_or_instance_get("litellm_fallback_models") or "").split(",") if m.strip()]
            local = next((m for m in chain if m.lower().startswith(("ollama", "local"))), None)
            fast = next((m for m in chain if any(k in m.lower() for k in ("flash", "lite", "mini", "fast"))), None)
            model = local or fast or (chain[0] if chain else "") or "openai/deepseek-v4-flash"
        except Exception:
            model = "openai/deepseek-v4-flash"
    try:
        resp = await litellm_client.complete(
            model=model, fallbacks=_router.fallbacks(),
            system=sys_prompt, prompt=f"用户问题:\n{task[:1200]}",
        )
        obj = _extract_json(resp.text or "") or {}
    except Exception as e:
        return {"matched": False, "mode_id": None, "reason": repr(e)}
    mid = obj.get("mode_id")
    if isinstance(mid, str) and mid in valid:
        return {"matched": True, "mode_id": mid, "mode_label": valid[mid]}
    return {"matched": False, "mode_id": None}


@app.post("/api/modes/reload")
def modes_reload_registry() -> dict:
    """
    Drop in-memory extra-mode YAML cache (``scenarios/extra``). Disabled unless
    ``HSEMAS_MODES_YAML_RELOAD_ENABLED=true`` (trusted dev / staging only).
    """
    if not settings.hsemas_modes_yaml_reload_enabled:
        raise HTTPException(status_code=404, detail="modes_reload_disabled")
    reload_mode_yaml_cache()
    ms = list_modes()
    return {"ok": True, "count": len(ms), "mode_ids": [m.mode_id for m in ms]}


@app.get("/api/memory/{mode_id}")
def memory_list(mode_id: str, limit: int = 50, compact: bool = False) -> list[dict]:
    mem = DecisionMemory(_DATA_DIR)
    rows = mem.list_summaries(mode_id=mode_id, limit=limit)
    if compact:
        return [compact_decision_row(r) for r in rows]
    return rows


@app.get("/api/memory/{mode_id}/decision/{decision_id}")
def memory_one(mode_id: str, decision_id: str) -> dict:
    """Full persisted summary for one decision (loads from JSONL)."""
    mem = DecisionMemory(_DATA_DIR)
    row = mem.get_by_decision_id(mode_id=mode_id, decision_id=decision_id)
    if row is None:
        raise HTTPException(status_code=404, detail="decision_not_found")
    return row

@app.get("/api/config/{mode_id}")
def config_get(mode_id: str) -> dict:
    cs = ConfigStore(_DATA_DIR)
    return cs.get_config(mode_id=mode_id)

@app.post("/api/config/{mode_id}")
async def config_set(mode_id: str, body: dict) -> dict:
    cs = ConfigStore(_DATA_DIR)
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
        n = LocalRagStore(_DATA_DIR).upsert(
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


@app.get("/api/genes/{mode_id}/prompts")
def genes_list_prompts(mode_id: str) -> dict[str, Any]:
    """Return merged prompt + 3+1 team per department."""
    from .gene_team import merged_gene_prompt, team_from_record
    from .modes import get_mode

    gs = GeneStore(_DATA_DIR)
    mode = get_mode(mode_id)
    prompts: dict[str, str] = {}
    teams: dict[str, Any] = {}
    for d in mode.departments:
        rec = gs.get_active(mode_id=mode_id, dept=d)
        teams[d] = team_from_record(rec)
        fb = build_initial_gene_prompt(mode_id, d)
        prompts[d] = merged_gene_prompt(rec, mode_id, d, fb) if rec else ""
    return {"mode_id": mode_id, "prompts": prompts, "teams": teams}


@app.get("/api/genes/{mode_id}/teams")
def genes_list_teams(mode_id: str) -> dict[str, Any]:
    """Convenience alias; same as ``/prompts`` (includes teams + prompts)."""
    return genes_list_prompts(mode_id)


@app.put("/api/genes/{mode_id}/teams")
def genes_put_teams(mode_id: str, body: GenesTeamsSaveRequest) -> dict[str, Any]:
    from .gene_team import merge_team_to_prompt, normalize_team, team_has_content
    from .modes import get_mode

    gs = GeneStore(_DATA_DIR)
    mode = get_mode(mode_id)
    allowed = set(mode.departments)
    saved = 0
    errors: list[str] = []
    for dept, raw in (body.teams or {}).items():
        if dept not in allowed:
            errors.append(f"unknown_dept:{dept}")
            continue
        team = normalize_team(raw)
        if not team_has_content(team):
            continue
        merged = merge_team_to_prompt(mode_id, dept, team)
        gs.set_active(mode_id=mode_id, dept=dept, team=team, prompt=merged)
        saved += 1
    return {"ok": True, "saved": saved, "errors": errors}


@app.post("/api/genes/{mode_id}/{dept}/team/regenerate")
async def genes_regenerate_team_slot(mode_id: str, dept: str, body: GeneRegenerateSlotRequest) -> dict[str, Any]:
    from .gene_bootstrap import regenerate_team_slot
    from .gene_team import merge_team_to_prompt, normalize_team, team_from_record
    from .modes import get_mode

    mode = get_mode(mode_id)
    if dept not in mode.departments:
        raise HTTPException(status_code=422, detail={"error": "unknown_dept", "dept": dept})
    gs = GeneStore(_DATA_DIR)
    rec = gs.get_active(mode_id=mode_id, dept=dept)
    cur = normalize_team(team_from_record(rec))
    new_role = await regenerate_team_slot(
        mode_id=mode_id,
        dept=dept,
        slot=body.slot,
        preference=body.preference,
        current_team=cur,
    )
    cur[body.slot] = new_role
    merged = merge_team_to_prompt(mode_id, dept, cur)
    out = gs.set_active(mode_id=mode_id, dept=dept, team=cur, prompt=merged)
    return {"ok": True, "slot": body.slot, "role": new_role, "record": out}


@app.put("/api/genes/{mode_id}/prompts")
def genes_bulk_save(mode_id: str, body: GenesBulkSaveRequest) -> dict[str, Any]:
    """Save multiple department prompts; skips unknown dept keys and empty strings (does not erase)."""
    from .modes import get_mode

    gs = GeneStore(_DATA_DIR)
    mode = get_mode(mode_id)
    allowed = set(mode.departments)
    saved = 0
    errors: list[str] = []
    for dept, text in (body.prompts or {}).items():
        if dept not in allowed:
            errors.append(f"unknown_dept:{dept}")
            continue
        t = str(text or "").strip()
        if not t:
            continue
        gs.set_active(mode_id=mode_id, dept=dept, prompt=t)
        saved += 1
    return {"ok": True, "saved": saved, "errors": errors}


@app.post("/api/genes/{mode_id}/generate")
async def genes_generate_all(
    mode_id: str,
    body: GenesGenerateRequest | None = Body(default=None),
) -> dict[str, Any]:
    """Use LiteLLM (per-dept routing) to generate and persist department gene prompts for this mode."""
    from .gene_bootstrap import generate_all_dept_prompts

    overwrite = True if body is None else bool(body.overwrite)
    return await generate_all_dept_prompts(mode_id, overwrite=overwrite)


@app.get("/api/genes/{mode_id}/{dept}")
def genes_get_active(mode_id: str, dept: str) -> dict:
    gs = GeneStore(_DATA_DIR)
    rec = gs.get_active(mode_id=mode_id, dept=dept)
    if rec is None:
        rec = gs.set_active(mode_id=mode_id, dept=dept, prompt=build_initial_gene_prompt(mode_id, dept))
    return rec

@app.post("/api/genes/{mode_id}/{dept}")
async def genes_set_active(mode_id: str, dept: str, body: dict) -> dict:
    prompt = str(body.get("prompt") or "")
    if not prompt.strip():
        return {"error": "prompt_required"}
    gs = GeneStore(_DATA_DIR)
    return gs.set_active(mode_id=mode_id, dept=dept, prompt=prompt)

@app.post("/api/genes/{mode_id}/{dept}/evolve")
async def genes_evolve_dspy_style(mode_id: str, dept: str, body: GeneEvolveRequest) -> dict:
    """
    Phase 4: DSPy-style meta-prompt — propose an improved gene from active + task sample;
    optionally persist as a new shadow version for A/B scoring.
    """
    gs = GeneStore(_DATA_DIR)
    active = gs.get_active(mode_id=mode_id, dept=dept)
    if active is None:
        active = gs.set_active(mode_id=mode_id, dept=dept, prompt=build_initial_gene_prompt(mode_id, dept))
    from .gene_team import merged_gene_prompt

    ap = merged_gene_prompt(active, mode_id, dept, str(active.get("prompt") or ""))
    new_prompt, meta = await evolve_gene_prompt(
        mode_id=mode_id,
        dept=dept,
        active_prompt=ap,
        task_sample=body.task_sample,
    )
    gate: dict | None = None
    if body.require_gate:
        from .decision_memory import DecisionMemory
        from .gene_scoring import delta_stats, gene_score

        mem = DecisionMemory(_DATA_DIR)
        rows = mem.list_summaries(mode_id=mode_id, limit=80)
        tasks: list[str] = []
        for r in reversed(rows):
            t = r.get("task")
            if isinstance(t, str) and t.strip() and t not in tasks:
                tasks.append(t.strip())
            if len(tasks) >= body.gate_trials:
                break
        if len(tasks) < body.gate_trials:
            gate = {"ok": False, "reason": f"need_more_tasks({len(tasks)}/{body.gate_trials})", "n": len(tasks)}
        else:
            deltas = [gene_score(new_prompt, t) - gene_score(ap, t) for t in tasks[: body.gate_trials]]
            s = delta_stats(deltas)
            gate = {"ok": s.lb95 >= body.min_lb95_delta, "n": s.n, "mean": s.mean, "lb95": s.lb95, "min_lb95_delta": body.min_lb95_delta}
    saved_shadow: dict | None = None
    if body.save_shadow and new_prompt.strip() and (gate is None or gate.get("ok") is True):
        saved_shadow = gs.add_shadow(mode_id=mode_id, dept=dept, prompt=new_prompt)
    return {"prompt": new_prompt, "saved_shadow": saved_shadow, "meta": meta, "gate": gate}


@app.post("/api/genes/{mode_id}/{dept}/shadow")
async def genes_add_shadow(mode_id: str, dept: str, body: dict) -> dict:
    prompt = str(body.get("prompt") or "")
    if not prompt.strip():
        return {"error": "prompt_required"}
    gs = GeneStore(_DATA_DIR)
    return gs.add_shadow(mode_id=mode_id, dept=dept, prompt=prompt)

@app.get("/api/genes/{mode_id}/{dept}/shadow")
def genes_list_shadow(mode_id: str, dept: str, limit: int = 20) -> list[dict]:
    gs = GeneStore(_DATA_DIR)
    return gs.list_shadows(mode_id=mode_id, dept=dept, limit=limit)

@app.get("/api/shadow/{mode_id}/{dept}/{shadow_version}")
def shadow_status(mode_id: str, dept: str, shadow_version: int, trials: int = 3) -> dict:
    st = ShadowTester(_DATA_DIR)
    verdict = st.should_promote(mode_id=mode_id, dept=dept, shadow_version=shadow_version, trials=trials)
    scores = st.list_scores(mode_id=mode_id, dept=dept, shadow_version=shadow_version, limit=50)
    return {"verdict": {"promote": verdict.promote, "reason": verdict.reason, "shadow_version": verdict.shadow_version}, "scores": scores}


@app.post("/api/decision/start")
async def decision_start(req: DecisionStartRequest) -> dict[str, str]:
    if req.reject_unknown_mode:
        _, reg = resolve_mode(req.mode_id)
        if reg == "fallback":
            raise HTTPException(
                status_code=422,
                detail={"error": "unknown_mode_id", "mode_id": req.mode_id, "hint": "Use GET /api/modes/lookup/{mode_id} or add scenarios/extra/*.yaml"},
            )
    # Run in background so caller can connect websocket immediately.
    decision_id = "dec-" + uuid.uuid4().hex[:12]

    async def _bg() -> None:
        await run_decision(decision_id=decision_id, task=req.task, mode_id=req.mode_id, debate_rounds=req.debate_rounds, thinking_frameworks=req.thinking_frameworks, tier=req.tier, images=req.images, files=[f.model_dump() for f in req.files], route=req.route, departments_override=req.departments_override)

    asyncio.create_task(_bg())
    return {"decision_id": decision_id}


@app.post("/api/decision/preflight")
async def decision_preflight(req: PreflightRequest) -> dict[str, Any]:
    """v6-Z CEO 预分析: 便宜 LLM 读任务 → 推荐启动哪些部门 + 路线 + 轮数 (前端 5×3 选择器)."""
    from .decision_engine import ceo_preflight
    return await ceo_preflight(
        task=req.task,
        mode_id=req.mode_id,
        images=req.images,
        files=[f.model_dump() for f in req.files],
    )


@app.post("/api/decision/feedback")
def decision_feedback(req: DecisionFeedbackRequest) -> dict[str, Any]:
    """v6-Z 👍👎 奖励回填 → sop_bandit 学习 (Thompson 后验更新 + 时间衰减)."""
    from . import sop_bandit
    result = sop_bandit.record(
        mode_id=req.mode_id,
        difficulty=req.difficulty,
        route=req.route,
        rounds_band=req.rounds_band,
        reward=req.reward,
    )
    return {"ok": True, "recorded": result}


@app.get("/api/sop/bandit/{mode_id}")
def sop_bandit_stats(mode_id: str) -> dict[str, Any]:
    """v6-Z 查看某场景学到的路线/轮数偏好 (诊断/可视化用)."""
    from . import sop_bandit
    return {"stats": sop_bandit.stats(mode_id), "summary": sop_bandit.summary_for_sop(mode_id)}


@app.post("/api/decision/rerun-dept/{decision_id}/{dept_id}")
async def decision_rerun_dept(decision_id: str, dept_id: str) -> dict[str, Any]:
    """v6-S6 只重跑某个部门 (保留其它部门已有结果). 重跑后追加新 decision 到 jsonl, 原行不动."""
    from .decision_engine import _run_dept, _memory  # type: ignore[attr-defined]
    from .runtime_paths import backend_data_dir

    base = backend_data_dir()
    found_row: dict[str, Any] | None = None
    found_mode: str | None = None
    for mode_dir in base.iterdir():
        if not mode_dir.is_dir():
            continue
        p = mode_dir / "decisions.jsonl"
        if not p.exists():
            continue
        try:
            with p.open("r", encoding="utf-8") as f:
                for line in f:
                    if f'"decision_id": "{decision_id}"' in line or f'"decision_id":"{decision_id}"' in line:
                        try:
                            found_row = json.loads(line)
                            found_mode = mode_dir.name
                            break
                        except Exception:
                            continue
        except Exception:
            continue
        if found_row:
            break

    if not found_row or not found_mode:
        raise HTTPException(status_code=404, detail=f"decision {decision_id} 没找到")

    task = str(found_row.get("task") or "").strip()
    if not task:
        raise HTTPException(status_code=422, detail="原决策没有 task 字段, 无法重跑")

    new_decision_id = "dec-" + uuid.uuid4().hex[:12]
    try:
        new_report = await _run_dept(
            decision_id=new_decision_id,
            mode_id=found_mode,
            dept=dept_id,
            task=task,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"rerun_failed: {e}")

    new_summary = dict(found_row)
    reports = list(new_summary.get("dept_reports") or [])
    new_report_dict = new_report.model_dump() if hasattr(new_report, "model_dump") else dict(new_report)
    patched = False
    for i, r in enumerate(reports):
        if str(r.get("dept") or "") == dept_id:
            reports[i] = new_report_dict
            patched = True
            break
    if not patched:
        reports.append(new_report_dict)
    new_summary["dept_reports"] = reports
    new_summary["decision_id"] = new_decision_id
    new_summary["rerun_of"] = decision_id
    new_summary["rerun_dept"] = dept_id

    try:
        _memory.append_summary(mode_id=found_mode, summary=new_summary)
    except Exception:
        pass

    return {"summary": new_summary}


@app.websocket("/api/decision/stream/{decision_id}")
async def decision_stream(ws: WebSocket, decision_id: str) -> None:
    await ws.accept()
    try:
        async for event in bus.subscribe(decision_id):
            await ws.send_text(json.dumps(event.model_dump(), ensure_ascii=False))
    except WebSocketDisconnect:
        return



# ============================================================
# v4-B  /api/decision/estimate  + /api/llm/price-card  (新增)
# ============================================================

@app.post("/api/decision/estimate", response_model=DecisionEstimateResponse)
async def decision_estimate(req: DecisionEstimateRequest) -> DecisionEstimateResponse:
    """Haiku-style 4-tier triage (v4-B). Cheap pre-flight; never spawns a real decision."""
    text = (req.task or "").strip()
    n = len(text)

    # cheap deterministic heuristic (real Haiku call to be added later)
    keywords = text.lower()
    if any(k in keywords for k in ["ppt", "excel", "word", "pdf", "邮件", "截图", "翻译", "总结"]):
        diff, ttype, reason = 1, "office", "短任务关键词 → 轻办公"
    elif any(k in keywords for k in ["写代码", "重构", "bug", "实现", "function", "class "]):
        diff, ttype, reason = 3, "coding", "涉及编码 → 重"
    elif any(k in keywords for k in ["战略", "路线图", "未来", "下半年", "规划"]) and n > 80:
        diff, ttype, reason = 4, "decision", "战略级长任务 → 极重"
    elif n < 30:
        diff, ttype, reason = 1, "decision", "短任务 → 轻"
    elif n < 120:
        diff, ttype, reason = 2, "decision", "中等任务"
    elif n < 300:
        diff, ttype, reason = 3, "decision", "较长任务 → 重"
    else:
        diff, ttype, reason = 4, "decision", "超长任务 → 极重"

    # naive token / cost estimate
    base_tok = max(500, int(n * 3))
    multiplier = {1: 1, 2: 4, 3: 12, 4: 30}[diff] * max(1, req.debate_rounds)
    est_tokens = base_tok * multiplier
    # rough avg sonnet price: input ~$3/M, output ~$15/M → call it ~$8/M blended, ×7.2 fx
    est_yuan = est_tokens / 1_000_000 * 8.0 * 7.2
    eta = {1: 3, 2: 12, 3: 30, 4: 90}[diff]

    suggested: list[str] = []
    if ttype == "decision" and diff >= 3:
        suggested = ["first_principles", "inversion", "pre_mortem"]
    elif diff == 4:
        suggested = ["first_principles", "inversion", "triz", "pre_mortem", "constraint_flip"]

    return DecisionEstimateResponse(
        difficulty=diff,
        type=ttype,
        confidence=0.65,
        reason=reason,
        estimate_tokens=est_tokens,
        estimate_yuan=round(est_yuan, 3),
        eta_sec=eta,
        suggested_frameworks=suggested,
    )


@app.get("/api/llm/price-card", response_model=PriceCardResponse)
def llm_price_card() -> PriceCardResponse:
    """LiteLLM-aligned price table + ¥7.2/$ fx rate (v1.2)."""
    fx = 7.2
    # Curated subset; full table grows from LiteLLM registry later (v5-C model auto-discovery)
    raw = [
        ("claude-opus-4-5",        15.0,   75.0),
        ("claude-sonnet-4-5",       3.0,   15.0),
        ("claude-haiku-4-5",        1.0,    5.0),
        ("gpt-4o",                  2.5,   10.0),
        ("gpt-4o-mini",             0.15,   0.6),
        ("gemini-1.5-pro",          1.25,   5.0),
        ("gemini-1.5-flash",        0.075,  0.3),
        ("deepseek-chat",           0.27,   1.1),
        ("doubao-pro",              0.8,    2.0),
        ("glm-4-air",               0.1,    0.1),
        ("moonshot-v1-8k",          1.7,    1.7),
        ("qwen2.5-72b",             0.4,    1.2),
    ]
    entries: list[PriceCardEntry] = []
    for m, inp_usd, out_usd in raw:
        entries.append(PriceCardEntry(
            model=m,
            input_per_million_usd=inp_usd,
            output_per_million_usd=out_usd,
            input_per_million_yuan=round(inp_usd * fx, 3),
            output_per_million_yuan=round(out_usd * fx, 3),
        ))
    return PriceCardResponse(fx_rate_cny_per_usd=fx, entries=entries)

app.include_router(coordinator_router, prefix="/coordinator", tags=["coordinator"])
app.include_router(team_router)  # v6-A 动态部门 + 人设池 (/api/team/**)
from .persona.wizard_api import router as wizard_router  # v7 W4 自定义场景向导
app.include_router(wizard_router)
# v3-K 主动交互 (修脱节: proactive.py 现在有 HTTP 端点 /api/proactive/**)
from .assistant.api import router as proactive_router  # noqa: E402
app.include_router(proactive_router)

# v6-F 意图澄清节点 (/api/intent/probe + /api/intent/resolve)
from .intent_clarify import router as intent_router  # noqa: E402
app.include_router(intent_router)

# v6-G PendingChanges 审批通道 (/api/pending/**)
from .pending_changes import router as pending_router  # noqa: E402
app.include_router(pending_router)

# v6-K 趋势仪表盘 (/api/trends/aggregate)
from .trends_api import router as trends_router  # noqa: E402
app.include_router(trends_router)

# v6-M 收藏功能 (/api/favorites/*)
from .favorites import router as favorites_router  # noqa: E402
app.include_router(favorites_router)

# v9 自学习闭环 (/api/learning/*): 联网新知收件箱 + 20:00 CEO 梳理 + 后台场景懒加载灌书
from .auto_learning.api import router as learning_router  # noqa: E402
app.include_router(learning_router)


# ============ v6-O bee-memory 代理 (解决前端跨域 + bearer 问题) ============
def _proxy_memory_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    import httpx as _hx
    import os as _o
    base = _o.environ.get("BEE_MEMORY_URL", "http://127.0.0.1:8004")
    headers = {"Authorization": f"Bearer {_o.environ.get('BEE_BEARER_TOKEN', 'dev-token-change-me')}"}
    try:
        with _hx.Client(timeout=10) as c:
            r = c.get(f"{base.rstrip('/')}{path}", params=params or {}, headers=headers)
        if r.status_code >= 400:
            return {"_proxy_error": f"HTTP {r.status_code}", "_path": path, "detail": r.text[:300]}
        return r.json()
    except Exception as e:
        return {"_proxy_error": f"network: {e!r}", "_path": path}


def _proxy_memory_post(path: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
    import httpx as _hx
    import os as _o
    base = _o.environ.get("BEE_MEMORY_URL", "http://127.0.0.1:8004")
    headers = {"Authorization": f"Bearer {_o.environ.get('BEE_BEARER_TOKEN', 'dev-token-change-me')}"}
    try:
        with _hx.Client(timeout=15) as c:
            r = c.post(f"{base.rstrip('/')}{path}", json=json_body or {}, headers=headers)
        if r.status_code >= 400:
            return {"_proxy_error": f"HTTP {r.status_code}", "_path": path, "detail": r.text[:300]}
        return r.json()
    except Exception as e:
        return {"_proxy_error": f"network: {e!r}", "_path": path}


@app.get("/api/memory/review/due")
def memory_review_due_proxy(limit: int = 20) -> dict[str, Any]:
    return _proxy_memory_get("/memory/review/due", {"limit": limit})


@app.get("/api/memory/review/stats")
def memory_review_stats_proxy() -> dict[str, Any]:
    return _proxy_memory_get("/memory/review/stats")


@app.post("/api/memory/review/grade")
def memory_review_grade_proxy(payload: dict[str, Any]) -> dict[str, Any]:
    return _proxy_memory_post("/memory/review/grade", payload)


@app.get("/api/memory/backup/stats")
def memory_backup_stats_proxy() -> dict[str, Any]:
    return _proxy_memory_get("/memory/backup/stats")


@app.post("/api/memory/backup/retry")
def memory_backup_retry_proxy(limit: int = 100) -> dict[str, Any]:
    return _proxy_memory_post(f"/memory/backup/retry?limit={limit}")


@app.post("/api/memory/backup/config")
def memory_backup_config_proxy(payload: dict[str, Any]) -> dict[str, Any]:
    """前端 5 池 Key 输入框提交; 转发给 bee-memory 持久化."""
    return _proxy_memory_post("/memory/backup/config", payload)


# v6-L /api/budget — 顶部预算环 (代理 bee-ledger /ledger/status)
@app.get("/api/budget")
def budget_summary() -> dict[str, Any]:
    """直接代理 bee-ledger /ledger/status; 不可达时返默认值."""
    try:
        from .tools import bee_clients as _bc
        return {"ok": True, **_bc.ledger_status()}
    except Exception as e:
        return {"ok": False, "error": repr(e)[:200],
                "today_yuan": 0.0, "month_yuan": 0.0,
                "budget_yuan": 800.0, "budget_used_pct": 0.0, "tier": "unknown"}

# 蜂群自己的日志端点 (没 bearer; 主程序聚合页面拉这里)
if _log_router_ok:
    app.include_router(_swarm_log_router)


# ============ /api/logs/aggregate — 把 6 微服务 + 蜂群自身日志聚合 ============
@app.get("/api/logs/aggregate")
def logs_aggregate(per_service_limit: int = 100, level: str = "") -> dict[str, Any]:
    """同步轮询 6 微服务 + 蜂群自身的 /logs/recent 与 /logs/stats; 不阻塞太久."""
    import httpx as _httpx_a
    from .tools import bee_clients as _bc_a
    import os as _os
    bearer = {"Authorization": f"Bearer {_os.environ.get('BEE_BEARER_TOKEN', 'dev-token-change-me')}"}
    targets = {
        "scraper": _bc_a.scraper_url, "hands": _bc_a.hands_url,
        "light": _bc_a.light_url, "vision": _bc_a.vision_url,
        "ledger": _bc_a.ledger_url, "memory": _bc_a.memory_url,
    }
    services: dict[str, Any] = {}
    aggregated_errors = 0
    aggregated_warnings = 0
    qparam = {"limit": per_service_limit}
    if level:
        qparam["level"] = level

    for name, base in targets.items():
        svc: dict[str, Any] = {"name": name, "url": base, "reachable": False,
                               "items": [], "stats": {}}
        try:
            with _httpx_a.Client(timeout=5) as c:
                r1 = c.get(f"{base.rstrip('/')}/logs/recent",
                           params=qparam, headers=bearer)
                r2 = c.get(f"{base.rstrip('/')}/logs/stats", headers=bearer)
            if r1.status_code == 200:
                svc["items"] = (r1.json() or {}).get("items") or []
            if r2.status_code == 200:
                svc["stats"] = r2.json() or {}
                aggregated_errors += int(svc["stats"].get("ERROR", 0) or 0)
                aggregated_warnings += int(svc["stats"].get("WARNING", 0) or 0)
            svc["reachable"] = (r1.status_code == 200 or r2.status_code == 200)
        except Exception as e:
            svc["error"] = repr(e)[:200]
        services[name] = svc

    # 蜂群自己 (本进程直接读 _LOG_PATH, 不走 HTTP)
    swarm_svc: dict[str, Any] = {"name": "swarm", "url": "local",
                                 "reachable": True, "items": [], "stats": {}}
    try:
        from bee_logs import logs_recent as _lr, logs_stats as _ls  # type: ignore
        rec = _lr(limit=per_service_limit, level=level)
        st = _ls()
        swarm_svc["items"] = rec.get("items", [])
        swarm_svc["stats"] = st
        aggregated_errors += int(st.get("ERROR", 0) or 0)
        aggregated_warnings += int(st.get("WARNING", 0) or 0)
    except Exception as e:
        swarm_svc["error"] = repr(e)[:200]
    services["swarm"] = swarm_svc

    return {
        "services": services,
        "summary": {
            "total_errors": aggregated_errors,
            "total_warnings": aggregated_warnings,
            "service_count": len(services),
        },
    }


# Optional B2: serve exported frontend from backend process.
# Must be mounted after all /api routes so the UI doesn't shadow them.
from .static_site import static_ui_dir

_ui_dir = static_ui_dir()
if _ui_dir.exists() and any(_ui_dir.iterdir()):
    app.mount("/", StaticFiles(directory=str(_ui_dir), html=True), name="ui")

