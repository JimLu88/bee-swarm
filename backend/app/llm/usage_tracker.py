# -*- coding: utf-8 -*-
"""usage_tracker — LLM 调用用量记账(省钱#1: 看不见的成本无法优化).

每次 LLM 调用后 record() 追加一行到 backend/data/llm_usage.jsonl:
  {ts, model, caller, ptok, ctok, latency_ms, cost}
cost 为按价格表估算的 USD(本地 ollama=0)。价格表可用 backend/data/llm_prices.json 覆盖:
  {"substring": [input_per_1M, output_per_1M], ...}  按子串匹配 model 名。
summary() 给 /api/llm/usage 端点出 今日/7日 按模型聚合。全程 best-effort, 绝不影响主调用。
"""
from __future__ import annotations

import json
import time
import threading
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parent.parent / "data"
_USAGE = _DATA / "llm_usage.jsonl"
_PRICES = _DATA / "llm_prices.json"
_lock = threading.Lock()

# 默认价格表 (USD / 1M tokens, [input, output]); 子串匹配, 从上到下首中即用
_DEFAULT_PRICES: list[tuple[str, float, float]] = [
    ("ollama", 0.0, 0.0), ("local", 0.0, 0.0),
    ("opus", 15.0, 75.0),
    ("sonnet", 3.0, 15.0),
    ("haiku", 1.0, 5.0),
    ("deepseek", 0.27, 1.10),
    ("gpt-5", 1.25, 10.0), ("mini", 0.15, 0.60), ("nano", 0.05, 0.40),
    ("gemini", 0.30, 2.50), ("flash", 0.15, 0.60),
    ("qwen", 0.40, 1.20), ("glm", 0.30, 1.10), ("kimi", 0.40, 1.60),
]


def _price_for(model: str) -> tuple[float, float]:
    m = (model or "").lower()
    try:
        if _PRICES.is_file():
            custom = json.loads(_PRICES.read_text(encoding="utf-8"))
            for sub, pair in custom.items():
                if sub.lower() in m and isinstance(pair, list) and len(pair) == 2:
                    return float(pair[0]), float(pair[1])
    except Exception:
        pass
    for sub, pi, po in _DEFAULT_PRICES:
        if sub in m:
            return pi, po
    return 1.0, 3.0  # 未知模型保守默认


def record(*, model: str, ptok: int = 0, ctok: int = 0,
           latency_ms: int = 0, caller: str = "") -> None:
    """追加一条用量记录。任何异常都吞掉, 绝不影响主调用。"""
    try:
        pi, po = _price_for(model)
        cost = round((ptok * pi + ctok * po) / 1_000_000, 6)
        line = json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "model": model, "caller": caller[:60],
            "ptok": int(ptok or 0), "ctok": int(ctok or 0),
            "latency_ms": int(latency_ms or 0), "cost": cost,
        }, ensure_ascii=False)
        _DATA.mkdir(parents=True, exist_ok=True)
        with _lock, _USAGE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def record_from_litellm(resp: Any, *, model: str, latency_ms: int = 0, caller: str = "") -> None:
    """从 litellm 响应对象提取 usage 再记账(取不到就记 0 token, 至少留调用次数)。"""
    ptok = ctok = 0
    try:
        u = getattr(resp, "usage", None) or (resp.get("usage") if isinstance(resp, dict) else None)
        if u:
            ptok = int(getattr(u, "prompt_tokens", 0) or (u.get("prompt_tokens") if isinstance(u, dict) else 0) or 0)
            ctok = int(getattr(u, "completion_tokens", 0) or (u.get("completion_tokens") if isinstance(u, dict) else 0) or 0)
    except Exception:
        pass
    record(model=model, ptok=ptok, ctok=ctok, latency_ms=latency_ms, caller=caller)


def summary(days: int = 7) -> dict[str, Any]:
    """聚合最近 N 天: 总成本/调用数 + 按天、按模型分桶。"""
    out: dict[str, Any] = {"days": days, "total_cost": 0.0, "total_calls": 0,
                           "by_day": {}, "by_model": {}}
    if not _USAGE.is_file():
        return out
    cutoff = time.time() - days * 86400
    try:
        with _USAGE.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    ts = time.mktime(time.strptime(r.get("ts", ""), "%Y-%m-%dT%H:%M:%S"))
                except Exception:
                    continue
                if ts < cutoff:
                    continue
                day = str(r.get("ts", ""))[:10]
                cost = float(r.get("cost", 0) or 0)
                out["total_cost"] = round(out["total_cost"] + cost, 4)
                out["total_calls"] += 1
                d = out["by_day"].setdefault(day, {"calls": 0, "cost": 0.0, "ptok": 0, "ctok": 0})
                d["calls"] += 1
                d["cost"] = round(d["cost"] + cost, 4)
                d["ptok"] += int(r.get("ptok", 0) or 0)
                d["ctok"] += int(r.get("ctok", 0) or 0)
                m = out["by_model"].setdefault(str(r.get("model", "?")), {"calls": 0, "cost": 0.0})
                m["calls"] += 1
                m["cost"] = round(m["cost"] + cost, 4)
    except Exception:
        pass
    return out
