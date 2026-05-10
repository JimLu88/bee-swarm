from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any


class DecisionMemory:
    """
    Phase 1 persistence:
    - store per-mode decision summaries as JSONL
    - hard namespace isolation by mode_id directory
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def _mode_dir(self, mode_id: str) -> Path:
        safe = "".join(c for c in mode_id if c.isalnum() or c in ("_", "-"))[:64] or "default"
        return self._base_dir / safe

    def append_summary(self, *, mode_id: str, mode_label: str | None = None, summary: dict[str, Any]) -> None:
        d = self._mode_dir(mode_id)
        d.mkdir(parents=True, exist_ok=True)
        p = d / "decisions.jsonl"
        enriched = dict(summary)
        enriched.setdefault("mode_id", mode_id)
        if mode_label:
            enriched.setdefault("mode_label", mode_label)
        enriched.setdefault("created_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(enriched, ensure_ascii=False) + "\n")

    def read_all_summaries(self, *, mode_id: str) -> list[dict[str, Any]]:
        """Read entire JSONL (MVP scale). Used by list tail + lookup by decision_id."""
        d = self._mode_dir(mode_id)
        p = d / "decisions.jsonl"
        if not p.exists():
            return []
        rows: list[dict[str, Any]] = []
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        return rows

    def list_summaries(self, *, mode_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.read_all_summaries(mode_id=mode_id)
        return rows[-max(1, min(limit, 200)) :]

    def get_by_decision_id(self, *, mode_id: str, decision_id: str) -> dict[str, Any] | None:
        for row in reversed(self.read_all_summaries(mode_id=mode_id)):
            if row.get("decision_id") == decision_id:
                return row
        return None

