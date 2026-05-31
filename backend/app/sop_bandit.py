"""v6-Z 路线×轮数的上下文老虎机 (Contextual Thompson Sampling).

为什么用 Thompson Sampling (而非 p13 那种固定 10% epsilon):
- 自动按不确定性探索: 某个臂数据少 → 后验方差大 → 采样波动大 → 自然多试;
  数据多且稳 → 收敛到利用. (世界先进做法, 见 Russo et al. "A Tutorial on Thompson Sampling")
- 能感知漂移: 配合时间衰减, 旧数据慢慢褪色, 环境变了系统会重新探索 → 防"一成不变".

设计:
- 上下文 context = (mode_id, 难度桶 light/medium/heavy)
- 臂 arm = (route, rounds_band)
    route ∈ all/multi/key/single/ceo_only
    rounds_band ∈ heavy(3-5轮)/medium(1-3轮)/light(1轮)
- 奖励 reward ∈ [0,1]: 👍=1.0, 👎=0.0, 或 1-5 星归一化
- 每个 (context, arm) 维护 Beta(α,β) 后验; 推荐时各臂采样 θ~Beta, 取 argmax
- 防僵化三件套:
    1. 5% 探索下限 (epsilon floor): 即便高度收敛也偶尔随机换臂
    2. 时间衰减 (decay 0.99): 每次 record 把该 context 所有臂的"伪计数"乘 0.99, 旧数据褪色
    3. Thompson 本身的不确定性探索
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path
from threading import Lock
from typing import Any

from .runtime_paths import backend_data_dir

_STORE_PATH = backend_data_dir() / "sop_bandit.json"
_LOCK = Lock()

ROUTES = ["all", "multi", "key", "single", "ceo_only"]
ROUNDS_BANDS = ["heavy", "medium", "light"]
DIFFICULTIES = ["light", "medium", "heavy"]

# rounds_band → 实际辩论轮数 (CEO 可在 band 内推荐具体值; 这里给默认)
BAND_TO_ROUNDS = {"heavy": 4, "medium": 2, "light": 1}

_EPSILON_FLOOR = 0.05      # 永远保留 5% 随机探索
_DECAY = 0.99              # 每次 record 旧伪计数衰减系数
_PRIOR_A = 1.0             # Beta 先验 (1,1) = 均匀, 无偏见
_PRIOR_B = 1.0


def difficulty_bucket(task: str, level: str = "") -> str:
    """task 长度 + dispatcher 分级 → light/medium/heavy 难度桶."""
    n = len((task or "").strip())
    if level == "strategic" or n >= 400:
        return "heavy"
    if n < 80:
        return "light"
    return "medium"


def _key(mode_id: str, diff: str, route: str, band: str) -> str:
    return f"{mode_id}|{diff}|{route}|{band}"


def _load() -> dict[str, Any]:
    if not _STORE_PATH.exists():
        return {"version": 1, "arms": {}}
    try:
        data = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "arms" not in data:
            return {"version": 1, "arms": {}}
        return data
    except Exception:
        return {"version": 1, "arms": {}}


def _save(data: dict[str, Any]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _STORE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_STORE_PATH)


def _arm(data: dict[str, Any], key: str) -> dict[str, Any]:
    arms = data.setdefault("arms", {})
    if key not in arms:
        arms[key] = {"alpha": _PRIOR_A, "beta": _PRIOR_B, "n": 0, "last_ts": 0}
    return arms[key]


def _sample_beta(alpha: float, beta: float) -> float:
    # random.betavariate 要求 α,β > 0
    return random.betavariate(max(alpha, 1e-6), max(beta, 1e-6))


def recommend(mode_id: str, difficulty: str) -> dict[str, Any]:
    """汤普森采样: 各臂采样 θ, 取最高. 返回推荐 + 全部臂的均值(供前端展示学到的偏好).

    返回 {
      recommended_route, recommended_rounds_band, recommended_rounds,
      explored: bool (这次是否触发 5% 随机探索),
      arms: { "route|band": {mean, n, sampled} }  # 给前端可视化
    }
    """
    with _LOCK:
        data = _load()
        explored = random.random() < _EPSILON_FLOOR
        arms_view: dict[str, Any] = {}
        best_key = None
        best_sample = -1.0
        for route in ROUTES:
            for band in ROUNDS_BANDS:
                a = _arm(data, _key(mode_id, difficulty, route, band))
                alpha, beta = float(a["alpha"]), float(a["beta"])
                mean = alpha / (alpha + beta)
                sampled = random.random() if explored else _sample_beta(alpha, beta)
                arms_view[f"{route}|{band}"] = {
                    "mean": round(mean, 3), "n": int(a["n"]), "sampled": round(sampled, 3),
                }
                if sampled > best_sample:
                    best_sample = sampled
                    best_key = (route, band)
        route, band = best_key or ("multi", "medium")
        return {
            "recommended_route": route,
            "recommended_rounds_band": band,
            "recommended_rounds": BAND_TO_ROUNDS.get(band, 2),
            "explored": explored,
            "arms": arms_view,
        }


def record(mode_id: str, difficulty: str, route: str, rounds_band: str, reward: float) -> dict[str, Any]:
    """回填奖励: 先衰减该 context 所有臂(旧数据褪色), 再更新选中臂的 Beta."""
    reward = max(0.0, min(1.0, float(reward)))
    with _LOCK:
        data = _load()
        now = int(time.time())
        # 时间衰减: 该 context 下所有臂的"超出先验的伪计数"乘 _DECAY
        for r in ROUTES:
            for b in ROUNDS_BANDS:
                a = _arm(data, _key(mode_id, difficulty, r, b))
                a["alpha"] = _PRIOR_A + (float(a["alpha"]) - _PRIOR_A) * _DECAY
                a["beta"] = _PRIOR_B + (float(a["beta"]) - _PRIOR_B) * _DECAY
        # 更新选中臂
        key = _key(mode_id, difficulty, route, rounds_band)
        a = _arm(data, key)
        a["alpha"] = float(a["alpha"]) + reward
        a["beta"] = float(a["beta"]) + (1.0 - reward)
        a["n"] = int(a["n"]) + 1
        a["last_ts"] = now
        _save(data)
        return {"key": key, "alpha": round(a["alpha"], 3), "beta": round(a["beta"], 3), "n": a["n"]}


def summary_for_sop(mode_id: str) -> str:
    """给 CEO 读的人类可读摘要: 每个难度桶, 历史最优路线+轮数 + 样本量.

    CEO 把它当"软参考"(不是硬规则), 配合 5% 探索, 避免一成不变.
    """
    with _LOCK:
        data = _load()
    lines: list[str] = []
    for diff in DIFFICULTIES:
        best = None
        best_mean = -1.0
        total_n = 0
        for route in ROUTES:
            for band in ROUNDS_BANDS:
                key = _key(mode_id, diff, route, band)
                a = data.get("arms", {}).get(key)
                if not a or int(a.get("n", 0)) == 0:
                    continue
                total_n += int(a["n"])
                alpha, beta = float(a["alpha"]), float(a["beta"])
                mean = alpha / (alpha + beta)
                if mean > best_mean:
                    best_mean = mean
                    best = (route, band, int(a["n"]))
        if best:
            route, band, n = best
            lines.append(
                f"- {diff} 难度: 历史最佳 = 路线[{route}] + {band}轮 "
                f"(好评率 {best_mean:.0%}, 样本 {total_n} 次)"
            )
        else:
            lines.append(f"- {diff} 难度: 暂无历史数据, 按 CEO 当前判断 + 适度探索")
    return "## 路线/轮数历史偏好 (软参考, 非硬规则; 系统保留 5% 探索避免僵化)\n" + "\n".join(lines)


def stats(mode_id: str | None = None) -> dict[str, Any]:
    """诊断/前端展示用: 导出原始臂数据."""
    with _LOCK:
        data = _load()
    arms = data.get("arms", {})
    if mode_id:
        arms = {k: v for k, v in arms.items() if k.startswith(f"{mode_id}|")}
    return {"version": data.get("version", 1), "arms": arms, "count": len(arms)}
