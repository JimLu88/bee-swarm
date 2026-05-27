from __future__ import annotations

import os
from pathlib import Path


def static_ui_dir() -> Path:
    """
    B2 packaging: directory containing exported frontend static files.
    Default: backend/app/static_ui
    Override with HSEMAS_STATIC_UI_DIR (absolute or backend-relative).
    """
    raw = (os.getenv("HSEMAS_STATIC_UI_DIR") or "").strip()
    base = Path(__file__).resolve().parent
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = (base.parent / raw).resolve()
        return p
    return (base / "static_ui").resolve()

