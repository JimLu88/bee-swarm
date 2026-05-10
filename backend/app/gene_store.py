from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class GeneStore:
    """
    MVP gene store (per mode_id):
    - active genes: data/<mode_id>/genes/active/<dept>.json
    - shadow genes: data/<mode_id>/genes/shadow/<dept>/<version>.json
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def _safe_mode_dir(self, mode_id: str) -> Path:
        safe = "".join(c for c in mode_id if c.isalnum() or c in ("_", "-"))[:64] or "default"
        return self._base_dir / safe

    def _genes_dir(self, mode_id: str) -> Path:
        return self._safe_mode_dir(mode_id) / "genes"

    def get_active(self, *, mode_id: str, dept: str) -> dict[str, Any] | None:
        p = self._genes_dir(mode_id) / "active" / f"{dept}.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def set_active(self, *, mode_id: str, dept: str, prompt: str, version: int | None = None) -> dict[str, Any]:
        d = self._genes_dir(mode_id) / "active"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{dept}.json"
        record = {
            "dept": dept,
            "version": int(version or int(time.time())),
            "prompt": prompt,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "active",
        }
        p.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return record

    def add_shadow(self, *, mode_id: str, dept: str, prompt: str) -> dict[str, Any]:
        shadow_root = self._genes_dir(mode_id) / "shadow" / dept
        shadow_root.mkdir(parents=True, exist_ok=True)
        version = int(time.time())
        p = shadow_root / f"{version}.json"
        record = {
            "dept": dept,
            "version": version,
            "prompt": prompt,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "shadow",
        }
        p.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return record

    def list_shadows(self, *, mode_id: str, dept: str, limit: int = 20) -> list[dict[str, Any]]:
        shadow_root = self._genes_dir(mode_id) / "shadow" / dept
        if not shadow_root.exists():
            return []
        items: list[tuple[int, dict[str, Any]]] = []
        for p in shadow_root.glob("*.json"):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
                items.append((int(rec.get("version") or 0), rec))
            except Exception:
                continue
        items.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in items[: max(1, min(limit, 200))]]

