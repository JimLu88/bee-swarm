"""
Runtime hub settings: ``backend/data/hub_settings.json`` overlays ``LlmRagSettings``
(.env) for UI-driven configuration (aligned with multi-tenant / hub-style projects).

GET masks secrets; PUT treats ``***xxxx`` as "keep previous value" from the saved file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .runtime_paths import backend_data_dir

HUB_FIELD_NAMES = frozenset(
    {
        "llm_provider",
        "litellm_base_url",
        "litellm_default_model",
        "litellm_fallback_models",
        "litellm_max_retries",
        "litellm_retry_base_ms",
        "litellm_embedding_model",
        "embedding_vector_dim",
        "anthropic_api_key",
        "openai_api_key",
        "gemini_api_key",
        "deepseek_api_key",
        "doubao_api_key",
        "rag_backend",
        "rag_hybrid_local_fts",
        "qdrant_url",
        "qdrant_api_key",
        "benchmark_web_search",
        "tavily_api_key",
        "exa_api_key",
        "amap_key",
        "app_password",
    }
)

SECRET_FIELDS = frozenset(
    {
        "anthropic_api_key",
        "openai_api_key",
        "gemini_api_key",
        "deepseek_api_key",
        "doubao_api_key",
        "qdrant_api_key",
        "tavily_api_key",
        "exa_api_key",
        "amap_key",
        "app_password",
    }
)

# Persisted alongside flat hub fields: department id -> LiteLLM model id string;
# named AI profiles; department id -> profile id.
HUB_EXTRA_SAVE_KEYS = frozenset({"dept_llm_models", "ai_profiles", "dept_ai_profile"})

_dept_llm_models: dict[str, str] = {}
_ai_profiles: list[dict[str, Any]] = []
_dept_ai_profile: dict[str, str] = {}


def get_dept_llm_models() -> dict[str, str]:
    return dict(_dept_llm_models)


def dept_llm_model_for(dept: str) -> str:
    """Resolved LiteLLM model: optional named profile, then per-dept model override, then global default."""
    from .settings_llm_rag import llm_rag_settings

    pid = _dept_ai_profile.get(dept)
    if isinstance(pid, str) and pid.strip():
        for p in _ai_profiles:
            if str(p.get("id", "")).strip() == pid.strip():
                m = str(p.get("model") or "").strip()
                if m:
                    return m

    ov = _dept_llm_models.get(dept)
    if isinstance(ov, str) and ov.strip():
        return ov.strip()
    d = (llm_rag_settings.litellm_default_model or "").strip()
    return d or "gpt-4o-mini"


def dept_routing_for_mode(mode_id: str) -> dict[str, Any]:
    from .modes import get_mode

    mode = get_mode(mode_id)
    labels = mode.department_labels or {}
    rows: list[dict[str, Any]] = []
    for d in mode.departments:
        ov = _dept_llm_models.get(d)
        prof_id = _dept_ai_profile.get(d)
        prof_label = None
        if prof_id:
            for p in _ai_profiles:
                if str(p.get("id", "")).strip() == str(prof_id).strip():
                    prof_label = str(p.get("label") or p.get("id") or "").strip()
                    break
        src = "default"
        if prof_id:
            src = "profile"
        elif ov:
            src = "override"
        rows.append(
            {
                "dept_id": d,
                "label": labels.get(d, d),
                "ai_profile_id": prof_id if prof_id else None,
                "ai_profile_label": prof_label,
                "override_model": ov if ov else None,
                "resolved_model": dept_llm_model_for(d),
                "source": src,
            }
        )
    from .settings_llm_rag import llm_rag_settings

    return {
        "mode_id": mode_id,
        "mode_label": mode.label,
        "default_model": llm_rag_settings.litellm_default_model,
        "rows": rows,
    }


def _normalize_ai_profiles(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw[:64]:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or "").strip()
        if not pid:
            continue
        label = str(item.get("label") or pid).strip()
        model = str(item.get("model") or "").strip()
        if not model:
            continue
        out.append({"id": pid, "label": label, "model": model})
    return out


def _normalize_dept_ai_profile_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        ks = str(k).strip()
        if not ks:
            continue
        if v is None or (isinstance(v, str) and not str(v).strip()):
            continue
        out[ks] = str(v).strip()
    return out


def _normalize_dept_llm_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        ks = str(k).strip()
        if not ks:
            continue
        if v is None or (isinstance(v, str) and not str(v).strip()):
            continue
        out[ks] = str(v).strip()
    return out


_ENV_FOR_SECRET: dict[str, tuple[str, ...]] = {
    "anthropic_api_key": ("ANTHROPIC_API_KEY",),
    "openai_api_key": ("OPENAI_API_KEY",),
    "gemini_api_key": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "deepseek_api_key": ("DEEPSEEK_API_KEY",),
    "doubao_api_key": ("DOUBAO_API_KEY",),
    "qdrant_api_key": ("QDRANT_API_KEY",),
    "tavily_api_key": ("TAVILY_API_KEY",),
    "exa_api_key": ("EXA_API_KEY",),
    "amap_key": ("AMAP_KEY",),
    "app_password": ("HSEMAS_APP_PASSWORD",),
}


def hub_settings_path() -> Path:
    return backend_data_dir() / "hub_settings.json"


def load_hub_file() -> dict[str, Any]:
    p = hub_settings_path()
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def save_hub_file(data: dict[str, Any]) -> None:
    p = hub_settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    allow = HUB_FIELD_NAMES | HUB_EXTRA_SAVE_KEYS
    clean = {k: v for k, v in data.items() if k in allow}
    p.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")


def _mask_secret(value: Any) -> Any:
    if value is None:
        return None
    s = str(value)
    if not s:
        return None
    if len(s) <= 4:
        return "***"
    return "***" + s[-4:]


def _is_masked_preserve(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith("***")


def _coerce(name: str, value: Any) -> Any:
    if name == "llm_provider":
        if value is None or value == "":
            return None
        s = str(value).strip().lower()
        return s if s in ("simulated", "litellm") else None
    if name == "litellm_max_retries":
        if value is None or value == "":
            return None
        return int(value)
    if name == "litellm_retry_base_ms":
        return int(value) if value not in (None, "") else 600
    if name == "embedding_vector_dim":
        if value is None or value == "":
            return None
        return int(value)
    if name in ("rag_hybrid_local_fts", "benchmark_web_search"):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    if isinstance(value, str):
        return value.strip() or None
    return value


def _clear_hub_secret_env() -> None:
    for _field, env_names in _ENV_FOR_SECRET.items():
        for envk in env_names:
            os.environ.pop(envk, None)


def _sync_os_from_merged(merged: dict[str, Any]) -> None:
    _clear_hub_secret_env()
    for field, env_names in _ENV_FOR_SECRET.items():
        v = merged.get(field)
        if isinstance(v, str) and v.strip() and not _is_masked_preserve(v):
            for envk in env_names:
                os.environ[envk] = v.strip()


def merge_put_with_existing(body: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    out = dict(existing)
    if "ai_profiles" in body:
        ap = body["ai_profiles"]
        if ap is None:
            out.pop("ai_profiles", None)
        elif isinstance(ap, list):
            norm = _normalize_ai_profiles(ap)
            if norm:
                out["ai_profiles"] = norm
            else:
                out.pop("ai_profiles", None)
    if "dept_ai_profile" in body:
        dam = body["dept_ai_profile"]
        if dam is None:
            out.pop("dept_ai_profile", None)
        elif isinstance(dam, dict):
            base_dap: dict[str, Any] = dict(out.get("dept_ai_profile") or {})
            for k, v in dam.items():
                ks = str(k).strip()
                if not ks:
                    continue
                if v is None or (isinstance(v, str) and not str(v).strip()):
                    base_dap.pop(ks, None)
                else:
                    base_dap[ks] = str(v).strip()
            if base_dap:
                out["dept_ai_profile"] = base_dap
            else:
                out.pop("dept_ai_profile", None)
    if "dept_llm_models" in body:
        dm = body["dept_llm_models"]
        if dm is None:
            out.pop("dept_llm_models", None)
        elif isinstance(dm, dict):
            base: dict[str, Any] = dict(out.get("dept_llm_models") or {})
            for k, v in dm.items():
                ks = str(k).strip()
                if not ks:
                    continue
                if v is None or (isinstance(v, str) and not str(v).strip()):
                    base.pop(ks, None)
                else:
                    base[ks] = str(v).strip()
            if base:
                out["dept_llm_models"] = base
            else:
                out.pop("dept_llm_models", None)
    for k, v in body.items():
        if k in ("dept_llm_models", "ai_profiles", "dept_ai_profile"):
            continue
        if k not in HUB_FIELD_NAMES:
            continue
        if _is_masked_preserve(v):
            continue
        if v is None or v == "":
            out.pop(k, None)
            continue
        out[k] = v
    return out


def public_hub_view() -> dict[str, Any]:
    from .settings_llm_rag import llm_rag_settings

    s = llm_rag_settings
    data: dict[str, Any] = {}
    for name in sorted(HUB_FIELD_NAMES):
        if not hasattr(s, name):
            continue
        v = getattr(s, name)
        if name in SECRET_FIELDS:
            data[name] = _mask_secret(v)
        else:
            data[name] = v
    data["dept_llm_models"] = dict(_dept_llm_models)
    data["ai_profiles"] = list(_ai_profiles)
    data["dept_ai_profile"] = dict(_dept_ai_profile)
    return data


def apply_merged_file(merged: dict[str, Any]) -> None:
    """
    Reset hub-managed fields from a fresh ``LlmRagSettings()`` (.env), then overlay ``merged``,
    then sync secret env vars for LiteLLM.
    """
    from .settings_llm_rag import LlmRagSettings, llm_rag_settings

    fresh = LlmRagSettings()
    for name in HUB_FIELD_NAMES:
        if hasattr(fresh, name):
            setattr(llm_rag_settings, name, getattr(fresh, name))

    for k, v in merged.items():
        if k not in HUB_FIELD_NAMES:
            continue
        if _is_masked_preserve(v):
            continue
        if v is None or v == "":
            continue
        coerced = _coerce(k, v)
        if coerced is None:
            continue
        try:
            setattr(llm_rag_settings, k, coerced)
        except Exception:
            continue

    _sync_os_from_merged(merged)

    global _dept_llm_models, _ai_profiles, _dept_ai_profile
    _dept_llm_models = _normalize_dept_llm_map(merged.get("dept_llm_models"))
    _ai_profiles = _normalize_ai_profiles(merged.get("ai_profiles"))
    _dept_ai_profile = _normalize_dept_ai_profile_map(merged.get("dept_ai_profile"))

    _normalize_llm_provider_runtime()


def _normalize_llm_provider_runtime() -> None:
    """
    If ``llm_provider`` is not a valid token (e.g. user typed a display name in the UI),
    fall back: use litellm when any provider key is set, else simulated.
    """
    from .settings_llm_rag import llm_rag_settings

    v = (llm_rag_settings.llm_provider or "").strip().lower()
    if v in ("simulated", "litellm"):
        return
    any_key = any(
        bool(str(getattr(llm_rag_settings, n, None) or "").strip())
        for n in (
            "anthropic_api_key",
            "openai_api_key",
            "gemini_api_key",
            "deepseek_api_key",
            "doubao_api_key",
        )
    )
    llm_rag_settings.llm_provider = "litellm" if any_key else "simulated"


def apply_stored_hub_on_startup() -> None:
    merged = load_hub_file()
    if merged:
        apply_merged_file(merged)
