from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .extra_mode_loader import extra_modes_dir
from .scenario_loader import scenarios_dir

ScenarioKind = Literal["root_overlay", "extra_mode"]


def target_path(*, kind: ScenarioKind, mode_id: str) -> Path:
    safe = "".join(c for c in (mode_id or "") if c.isalnum() or c in ("_", "-"))[:64] or "default"
    if kind == "extra_mode":
        return extra_modes_dir() / f"{safe}.yaml"
    return scenarios_dir() / f"{safe}.yaml"


def history_dir() -> Path:
    return scenarios_dir() / "_history"


@dataclass(frozen=True)
class HistoryEntry:
    ts: str
    mode_id: str
    kind: ScenarioKind
    action: str  # write|rollback
    before_path: str | None = None
    after_path: str | None = None
    note: str | None = None


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot_to_history(*, mode_id: str, kind: ScenarioKind, label: str, text: str | None) -> str | None:
    if text is None:
        return None
    d = history_dir() / mode_id
    d.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    p = d / f"{ts}-{kind}-{label}.yaml"
    p.write_text(text, encoding="utf-8")
    return str(p)


def append_history_log(entry: HistoryEntry) -> None:
    d = history_dir() / entry.mode_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / "history.jsonl"
    row: dict[str, Any] = {
        "ts": entry.ts,
        "mode_id": entry.mode_id,
        "kind": entry.kind,
        "action": entry.action,
        "before_path": entry.before_path,
        "after_path": entry.after_path,
        "note": entry.note,
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def list_history(*, mode_id: str, limit: int = 50) -> list[dict[str, Any]]:
    p = history_dir() / mode_id / "history.jsonl"
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
        except Exception:
            continue
    return rows[-max(1, min(limit, 200)) :]


def load_text_if_exists(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def compute_sha(text: str) -> str:
    return _sha256_text(text)

