from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "H-SEMAS Backend"
    cors_allow_origins: str = "http://localhost:3000"

    # Phase 3 optional: whitelist-only subprocess sandbox (never shell=True)
    hsemas_sandbox_exec_enabled: bool = False
    """Set true only in trusted dev laptops; requires explicit HSEMAS_EXEC_ALLOWLIST."""
    hsemas_exec_allowlist: str = ""
    """Comma-separated executable stems, e.g. pytest,ruff. Basename match (.exe stripped)."""
    hsemas_exec_cwd: str | None = None
    """Working directory relative to backend/ or absolute; must stay inside backend/workspace root."""
    hsemas_exec_timeout_sec: int = 120
    hsemas_exec_max_args: int = 40
    hsemas_exec_max_arg_len: int = 768
    hsemas_exec_max_output_chars: int = 65536

    # Dev-only: expose GET /api/debug/graph-state/{decision_id} (LangGraph checkpoint snapshot).
    hsemas_expose_graph_state: bool = False

    # LangGraph checkpoints: memory (ephemeral) or sqlite (survives process restarts; async API).
    hsemas_graph_checkpoint_backend: Literal["memory", "sqlite"] = "memory"
    hsemas_graph_checkpoint_sqlite_path: str | None = None
    """Absolute or backend-relative path; default backend/data/langgraph_checkpoints.sqlite3 when backend is sqlite."""

    # Phase 5+: allow POST /api/modes/reload to drop cached YAML mode registry (trusted dev only).
    hsemas_modes_yaml_reload_enabled: bool = False

    # Phase 9+: allow writing YAML scenarios to disk (trusted dev only).
    hsemas_scenario_write_enabled: bool = False

    # Hub UI: allow PUT /api/settings/hub to write backend/data/hub_settings.json (API keys, LLM, RAG).
    # Disable on internet-facing deployments unless protected by auth / VPN.
    hsemas_hub_settings_write_enabled: bool = True


settings = Settings()

