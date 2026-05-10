from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParsedDeptOutput:
    consensus: str
    conflicts: list[str]
    confidence_score: float
    dissent_intensity: float


def _clamp01(x: float) -> float:
    if x < 0:
        return 0.0
    if x > 1:
        return 1.0
    return float(x)


def _extract_json(text: str) -> dict[str, Any] | None:
    """
    Try hard to find a JSON object in free-form LLM output.
    """
    text = text.strip()
    if not text:
        return None

    # 1) direct json
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # 2) fenced code block ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

    # 3) first {...} block (greedy-ish, but bounded)
    m = re.search(r"(\{[\s\S]{10,5000}\})", text)
    if m:
        candidate = m.group(1)
        # remove trailing commentary after last }
        candidate = candidate[: candidate.rfind("}") + 1]
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

    return None


def parse_dept_output(text: str) -> ParsedDeptOutput | None:
    """
    Expected JSON schema (best effort):
      {
        "consensus": "string",
        "conflicts": ["..."],
        "confidence_score": 0.0-1.0,
        "dissent_intensity": 0.0-1.0
      }
    """
    obj = _extract_json(text)
    if not obj:
        return None

    consensus = str(obj.get("consensus") or "").strip()
    conflicts_raw = obj.get("conflicts")
    conflicts: list[str] = []
    if isinstance(conflicts_raw, list):
        conflicts = [str(x).strip() for x in conflicts_raw if str(x).strip()]
    elif isinstance(conflicts_raw, str) and conflicts_raw.strip():
        conflicts = [conflicts_raw.strip()]

    try:
        conf = float(obj.get("confidence_score"))
    except Exception:
        conf = 0.5
    try:
        dis = float(obj.get("dissent_intensity"))
    except Exception:
        dis = 0.5

    if not consensus:
        # fallback from common keys
        consensus = str(obj.get("recommendation") or obj.get("summary") or "").strip()
    if not consensus:
        return None

    return ParsedDeptOutput(
        consensus=consensus,
        conflicts=conflicts,
        confidence_score=_clamp01(conf),
        dissent_intensity=_clamp01(dis),
    )

