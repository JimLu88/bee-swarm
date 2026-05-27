from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass


def _stable_float(seed: str) -> float:
    h = hashlib.sha256(seed.encode("utf-8")).digest()
    n = int.from_bytes(h[:8], "big")
    return (n % 10_000) / 10_000


def gene_score(prompt: str, task: str) -> float:
    """
    Deterministic proxy score for Phase 11 gates + shadow promotion.
    We reward explicit structured fields + add a small task-conditioned tie-breaker.
    """
    p = prompt or ""
    base = 0.35
    base += 0.25 if "confidence_score" in p else 0.0
    base += 0.25 if "dissent_intensity" in p else 0.0
    base += 0.10 if ("json" in p.lower() or "JSON" in p) else 0.0
    base += 0.05 if ("冲突" in p or "conflicts" in p) else 0.0
    # small task-conditioned jitter so eval across tasksets is meaningful but stable
    jitter = (_stable_float(f"{task}||{p}") - 0.5) * 0.08
    s = min(1.0, max(0.0, base + jitter))
    if math.isnan(s):
        return 0.0
    return float(s)


@dataclass(frozen=True)
class DeltaStats:
    n: int
    mean: float
    se: float
    lb95: float


def delta_stats(deltas: list[float]) -> DeltaStats:
    n = len(deltas)
    if n <= 0:
        return DeltaStats(n=0, mean=0.0, se=float("inf"), lb95=float("-inf"))
    mean = sum(deltas) / n
    if n == 1:
        return DeltaStats(n=1, mean=float(mean), se=float("inf"), lb95=float("-inf"))
    var = sum((x - mean) ** 2 for x in deltas) / (n - 1)
    se = math.sqrt(var / n) if var >= 0 else float("inf")
    lb95 = mean - 1.96 * se if se != float("inf") else float("-inf")
    return DeltaStats(n=n, mean=float(mean), se=float(se), lb95=float(lb95))

