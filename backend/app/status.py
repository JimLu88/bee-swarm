from __future__ import annotations

from dataclasses import dataclass

import httpx

from .execution.safe_shell import effective_exec_cwd, sandbox_allowlist
from .orchestration.decision_graph import orchestration_checkpoint_path_fields
from .rag.embeddings import embedding_rag_status_fields
from .catalog import list_dept_names
from .extra_mode_loader import extra_modes_dir, list_extra_mode_yaml_basenames
from .modes import list_extra_mode_ids
from .scenario_loader import list_scenario_yaml_basenames, scenarios_dir
from .settings import settings as app_settings
from .settings_llm_rag import llm_rag_settings


@dataclass(frozen=True)
class ServiceStatus:
    ok: bool
    detail: str


async def check_qdrant() -> ServiceStatus:
    if llm_rag_settings.rag_backend == "local":
        return ServiceStatus(ok=True, detail="local_sqlite_fts")
    if llm_rag_settings.rag_backend == "simulated":
        return ServiceStatus(ok=True, detail="simulated_builtin")
    if llm_rag_settings.rag_backend != "qdrant":
        return ServiceStatus(ok=True, detail="disabled")
    url = llm_rag_settings.qdrant_url.rstrip("/")
    # Qdrant supports GET /readyz and /healthz on recent versions; fallback to /
    candidates = [f"{url}/readyz", f"{url}/healthz", f"{url}/"]
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            for u in candidates:
                r = await client.get(u, headers={"api-key": llm_rag_settings.qdrant_api_key} if llm_rag_settings.qdrant_api_key else None)
                if 200 <= r.status_code < 300:
                    return ServiceStatus(ok=True, detail=f"up ({u})")
        return ServiceStatus(ok=False, detail="no_2xx")
    except Exception as e:
        return ServiceStatus(ok=False, detail=repr(e))


async def check_llm() -> ServiceStatus:
    if llm_rag_settings.llm_provider != "litellm":
        return ServiceStatus(ok=True, detail="disabled")
    # Keys are env-only; we just check at least one key exists
    any_key = any(
        [
            llm_rag_settings.anthropic_api_key,
            llm_rag_settings.openai_api_key,
            llm_rag_settings.gemini_api_key,
            llm_rag_settings.deepseek_api_key,
            llm_rag_settings.doubao_api_key,
        ]
    )
    return ServiceStatus(ok=bool(any_key), detail="keys_present" if any_key else "no_api_keys_in_env")


def _search_status() -> dict:
    t = bool(llm_rag_settings.tavily_api_key)
    e = bool(llm_rag_settings.exa_api_key)
    enabled = llm_rag_settings.benchmark_web_search
    ready = enabled and (t or e)
    return {
        "benchmark_web_search_enabled": enabled,
        "tavily_configured": t,
        "exa_configured": e,
        "ok": ready,
        "detail": "ready" if ready else ("disabled_by_env" if not enabled else "no_api_keys"),
    }


def sandbox_exec_status() -> dict:
    allow = sandbox_allowlist()
    cwd, cwd_note = effective_exec_cwd()
    can_run = bool(app_settings.hsemas_sandbox_exec_enabled and len(allow) > 0)
    detail = (
        "ready"
        if can_run
        else ("disabled_by_env" if not app_settings.hsemas_sandbox_exec_enabled else "empty_allowlist")
    )
    return {
        "enabled": app_settings.hsemas_sandbox_exec_enabled,
        "allowlist_count": len(allow),
        "ok": can_run,
        "detail": detail,
        "exec_cwd": str(cwd),
        "cwd_resolution_note": cwd_note,
        "timeout_sec": app_settings.hsemas_exec_timeout_sec,
    }


async def get_status() -> dict:
    qdrant = await check_qdrant()
    llm = await check_llm()
    rb = llm_rag_settings.rag_backend
    emb_ctx = (
        embedding_rag_status_fields()
        if rb == "qdrant"
        else {
            "embedding_mode": "n/a",
            "embedding_model": None,
            "embedding_dim": None,
            "embedding_litellm_ready": False,
            "embedding_misconfigured": False,
            "embedding_note": "sqlite_fts5_no_embeddings" if rb == "local" else "builtin_chunks_only",
            "hybrid_local_fts": False,
        }
    )
    cp_backend = app_settings.hsemas_graph_checkpoint_backend
    checkpoint_label = "sqlite_async" if cp_backend == "sqlite" else "memory_saver"
    hybrid_merge_active = rb == "qdrant" and llm_rag_settings.rag_hybrid_local_fts
    return {
        "orchestration": {
            "backend": "langgraph",
            "graph": "decision_v2:send_dept_worker_defer_finalize",
            "checkpoint": checkpoint_label,
            "checkpoint_backend": cp_backend,
            "debug_graph_state_enabled": app_settings.hsemas_expose_graph_state,
            **orchestration_checkpoint_path_fields(),
        },
        "llm": {"provider": llm_rag_settings.llm_provider, "ok": llm.ok, "detail": llm.detail, "default_model": llm_rag_settings.litellm_default_model},
        "rag": {
            "backend": rb,
            "ok": qdrant.ok,
            "detail": qdrant.detail,
            "qdrant_url": llm_rag_settings.qdrant_url,
            "collection_prefix": "h_semas__",
            "hybrid_merge_active": hybrid_merge_active,
            "rag_hybrid_local_fts_env": llm_rag_settings.rag_hybrid_local_fts,
            **emb_ctx,
        },
        "search": _search_status(),
        "sandbox_exec": sandbox_exec_status(),
        # Product milestones for operators / UI (not env-configurable).
        "roadmap": {
            "phase2": "shipped",
            "phase2_scope": "langgraph_parallel_rag_litellm_embeddings_qdrant_local_hybrid",
            "phase3": "shipped",
            "phase3_scope": "vision_web_search_tavily_exa_execution_qa_sandbox_executor_cli_probe_optional_sandbox_exec",
            "phase4": "shipped",
            "phase4_scope": "dspy_genes_shadow_yaml_templates",
            "phase5": "shipped",
            "phase5_scope": "yaml_extra_modes_registry_scenarios_extra_optional_root_overlay",
            "phase6": "shipped",
            "phase6_scope": "dept_names_catalog_api_reject_unknown_mode_optional_on_decision_start",
            "phase7": "shipped",
            "phase7_scope": "yaml_authoring_tools_validate_scaffold_endpoints",
            "phase8": "shipped",
            "phase8_scope": "frontend_yaml_authoring_panel_scaffold_validate_dept_catalog",
            "phase9": "shipped",
            "phase9_scope": "scenario_write_api_save_to_disk_optional_reload",
            "phase10": "shipped",
            "phase10_scope": "scenario_history_and_rollback",
            "phase11": "shipped",
            "phase11_scope": "gene_evolve_quality_gate_shadow_promotion_taskset_ci",
            "phase12": "shipped",
            "phase12_scope": "product_ui_three_tiers_results_templates_onboarding_evidence",
        },
        "scenario_templates": {
            "dir": str(scenarios_dir()),
            "yaml_files": list_scenario_yaml_basenames(),
            "extra_modes_dir": str(extra_modes_dir()),
            "extra_mode_yaml_files": list_extra_mode_yaml_basenames(),
            "extra_mode_ids": list_extra_mode_ids(),
        },
        "modes_reload": {"enabled": app_settings.hsemas_modes_yaml_reload_enabled},
        "catalog": {
            "dept_name_count": len(list_dept_names()),
            "dept_names_endpoint": "/api/catalog/dept-names",
            "scenario_validate_endpoint": "/api/scenarios/validate",
            "scenario_scaffold_endpoint": "/api/scenarios/scaffold",
            "scenario_write_endpoint": "/api/scenarios/write",
            "scenario_history_endpoint": "/api/scenarios/history/{mode_id}",
            "scenario_rollback_endpoint": "/api/scenarios/rollback",
        },
    }

