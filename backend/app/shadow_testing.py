from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .gene_scoring import delta_stats


def _safe_mode(mode_id: str) -> str:
    return "".join(c for c in mode_id if c.isalnum() or c in ("_", "-"))[:64] or "default"


@dataclass(frozen=True)
class ShadowVerdict:
    promote: bool
    reason: str
    shadow_version: int | None = None


class ShadowTester:
    """
    MVP Shadow Mode:
    - Track per (mode_id, dept, shadow_version) recent scores in JSONL.
    - Promote shadow gene to active when it beats active for K trials.

    In Phase 2+ the score comes from "alignment with Jim final choice".
    For MVP we use a deterministic heuristic computed at decision time.
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def _score_dir(self, mode_id: str, dept: str) -> Path:
        return self._base_dir / _safe_mode(mode_id) / "shadow_scores" / dept

    def append_score(
        self,
        *,
        mode_id: str,
        dept: str,
        shadow_version: int,
        score_active: float,
        score_shadow: float,
        task_hash: str | None = None,
        decision_id: str | None = None,
    ) -> None:
        d = self._score_dir(mode_id, dept)
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{shadow_version}.jsonl"
        row = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "decision_id": decision_id,
            "task_hash": task_hash,
            "score_active": float(score_active),
            "score_shadow": float(score_shadow),
            "delta": float(score_shadow - score_active),
        }
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def should_promote(self, *, mode_id: str, dept: str, shadow_version: int, trials: int = 3, min_delta_avg: float = 0.02) -> ShadowVerdict:
        """
        Promote when we have >= `trials` distinct tasks and the 95% lower bound of delta >= min_delta_avg.
        """
        p = self._score_dir(mode_id, dept) / f"{shadow_version}.jsonl"
        if not p.exists():
            return ShadowVerdict(promote=False, reason="no_scores", shadow_version=shadow_version)

        # Keep the last delta per task_hash to avoid repeated same-task spam.
        per_task: dict[str, float] = {}
        tail: list[float] = []
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    dlt = float(obj.get("delta") or 0.0)
                    th = str(obj.get("task_hash") or "").strip()
                    if th:
                        per_task[th] = dlt
                    else:
                        tail.append(dlt)
                except Exception:
                    continue

        deltas = list(per_task.values())
        if len(deltas) < trials:
            # fall back to raw tail (legacy rows without task_hash)
            if len(tail) < trials:
                return ShadowVerdict(promote=False, reason=f"need_more_trials({len(deltas)}/{trials})", shadow_version=shadow_version)
            deltas = tail[-trials:]

        # Use at most last N distinct tasks (stable ordering not critical).
        s = delta_stats(deltas[-max(trials, min(len(deltas), 30)) :])
        if s.n < trials:
            return ShadowVerdict(promote=False, reason=f"need_more_trials({s.n}/{trials})", shadow_version=shadow_version)
        if s.lb95 >= min_delta_avg and not math.isnan(s.lb95):
            return ShadowVerdict(promote=True, reason=f"lb95={s.lb95:.4f} mean={s.mean:.4f} n={s.n}", shadow_version=shadow_version)
        return ShadowVerdict(promote=False, reason=f"lb95={s.lb95:.4f} mean={s.mean:.4f} n={s.n}", shadow_version=shadow_version)

    def list_scores(self, *, mode_id: str, dept: str, shadow_version: int, limit: int = 50) -> list[dict[str, Any]]:
        p = self._score_dir(mode_id, dept) / f"{shadow_version}.jsonl"
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
        return rows[-max(1, min(limit, 500)) :]

