"""dev_bandit — 编码 SOP 变体的 Contextual Thompson 采样 (仿 sop_bandit).

给开发任务挑一种"写码打法"(SOP 变体), 用每次跑批的 reward(records.compute_reward)回写学习。
首期: 照常 recommend + record 攒数据, 但不自动改 dev_sop.yaml(进化在 p17, 满 8 次 + 审批)。

存 backend/data/dev_bandit.json:
{ "version":1, "arms": { "<kind>|<variant>": {"alpha":float,"beta":float,"n":int,"last_ts":int} } }
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any

# 写码打法(SOP 变体)
SOP_VARIANTS = ["tdd", "prototype", "fix_loop"]
# 任务类型(上下文)
KINDS = ["feature", "bugfix", "refactor", "test"]

_EPSILON = 0.08      # 探索率
_DECAY = 0.99        # 旧数据时间衰减
_PRIOR = 1.0         # Beta(1,1) 均匀先验


def _path() -> Path:
    p = Path(__file__).resolve().parent.parent / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p / "dev_bandit.json"


def _load() -> dict[str, Any]:
    p = _path()
    if not p.is_file():
        return {"version": 1, "arms": {}}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {"version": 1, "arms": {}}
    except Exception:
        return {"version": 1, "arms": {}}


def _save(d: dict[str, Any]) -> None:
    try:
        _path().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _arm_key(kind: str, variant: str) -> str:
    return f"{kind}|{variant}"


def recommend(kind: str) -> dict[str, Any]:
    """Thompson 采样选一个 SOP 变体. 返回 {variant, arms:[{variant,mean,n}]}。"""
    kind = kind if kind in KINDS else "feature"
    arms = _load().get("arms", {})
    stats: list[dict[str, Any]] = []
    best_v, best_sample = SOP_VARIANTS[0], -1.0
    explore = random.random() < _EPSILON
    for v in SOP_VARIANTS:
        a = arms.get(_arm_key(kind, v), {})
        alpha = float(a.get("alpha", _PRIOR))
        beta = float(a.get("beta", _PRIOR))
        n = int(a.get("n", 0))
        sample = random.random() if explore else random.betavariate(max(alpha, 1e-6), max(beta, 1e-6))
        mean = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.5
        stats.append({"variant": v, "mean": round(mean, 3), "n": n})
        if sample > best_sample:
            best_sample, best_v = sample, v
    return {"variant": best_v, "kind": kind, "explore": explore, "arms": stats}


def record(kind: str, variant: str, reward: float) -> dict[str, Any]:
    """回写奖励 (reward∈[0,1]): 旧数据衰减后更新 Beta(α,β)。"""
    kind = kind if kind in KINDS else "feature"
    if variant not in SOP_VARIANTS:
        return {"ok": False, "reason": "unknown_variant"}
    reward = max(0.0, min(1.0, float(reward)))
    d = _load()
    arms = d.setdefault("arms", {})
    k = _arm_key(kind, variant)
    a = arms.get(k, {"alpha": _PRIOR, "beta": _PRIOR, "n": 0, "last_ts": 0})
    a["alpha"] = float(a.get("alpha", _PRIOR)) * _DECAY + reward
    a["beta"] = float(a.get("beta", _PRIOR)) * _DECAY + (1.0 - reward)
    a["n"] = int(a.get("n", 0)) + 1
    a["last_ts"] = int(time.time())
    arms[k] = a
    _save(d)
    return {"ok": True, "arm": k, "alpha": round(a["alpha"], 3), "beta": round(a["beta"], 3), "n": a["n"]}


def stats() -> dict[str, Any]:
    return _load()
