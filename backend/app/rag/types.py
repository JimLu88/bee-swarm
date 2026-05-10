from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RagChunk:
    chunk_id: str
    title: str
    content: str
    score: float
    meta: dict[str, Any]

