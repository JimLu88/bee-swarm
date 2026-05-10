from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class ConfigStore:
    """
    Per-mode settings storage.

    Phase 1 MVP stores a single JSON file per mode:
      data/<mode_id>/config.json
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def _mode_dir(self, mode_id: str) -> Path:
        safe = "".join(c for c in mode_id if c.isalnum() or c in ("_", "-"))[:64] or "default"
        return self._base_dir / safe

    def get_config(self, *, mode_id: str) -> dict[str, Any]:
        p = self._mode_dir(mode_id) / "config.json"
        if not p.exists():
            return {
                "mode_id": mode_id,
                "updated_at": None,
                "trusted_sources": {
                    "arxiv.org": 1.0,
                    "github.com": 0.95,
                    "acm.org": 1.0,
                    "reuters.com": 0.85,
                    "bloomberg.com": 0.85,
                    "36kr.com": 0.7,
                    "zhihu.com": 0.4,
                    "twitter.com": 0.25,
                },
            }
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {"mode_id": mode_id, "updated_at": None, "trusted_sources": {}}

    def set_config(self, *, mode_id: str, cfg: dict[str, Any]) -> dict[str, Any]:
        d = self._mode_dir(mode_id)
        d.mkdir(parents=True, exist_ok=True)
        p = d / "config.json"
        enriched = dict(cfg)
        enriched["mode_id"] = mode_id
        enriched["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        p.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
        return enriched

