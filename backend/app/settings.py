from __future__ import annotations

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

    # Dev-only: expose GET /api/debug/graph-state/{decision_id} (LangGraph MemorySaver snapshot).
    hsemas_expose_graph_state: bool = False


settings = Settings()

