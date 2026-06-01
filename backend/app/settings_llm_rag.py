from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class LlmRagSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM gateway (LiteLLM)
    llm_provider: str = "simulated"  # "simulated" | "litellm"
    litellm_base_url: str | None = None  # optional if using local proxy
    litellm_default_model: str = "gpt-4o-mini"
    litellm_fallback_models: str = "gpt-4o-mini,gpt-4.1-mini"
    litellm_max_retries: int = 2
    litellm_retry_base_ms: int = 600

    # API keys (env only)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    deepseek_api_key: str | None = None
    doubao_api_key: str | None = None

    # RAG (Qdrant)
    rag_backend: str = "simulated"  # "simulated" | "qdrant" | "local"
    # When RAG_BACKEND=qdrant: also search SQLite FTS (same backend/data as RAG_BACKEND=local) and merge.
    rag_hybrid_local_fts: bool = False
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    # Empty => deterministic hash vectors for Qdrant. Set when OPENAI_API_KEY (or other provider) is present.
    litellm_embedding_model: str = ""
    # Override vector dimension for Qdrant collection + hash expansion (optional).
    embedding_vector_dim: int | None = None

    # Phase 3: Vision-layer web search for benchmark + xlab (Tavily preferred, Exa fallback)
    benchmark_web_search: bool = True
    tavily_api_key: str | None = None
    exa_api_key: str | None = None

    # v11 高德 Web 服务 Key (地图钉店). 可在网页「AI 大脑」里填, 存 hub_settings.json; 留空禁用地图.
    amap_key: str | None = None


llm_rag_settings = LlmRagSettings()

