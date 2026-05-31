"""v6-C 人设知识库管理 — 8 层知识 (books/trends/cases/pitfalls/standards/slang/kols/history).

所有知识条目都进 bee-memory (port 8004), kind=knowledge_<layer>, 通过 meta.persona_id
+ mode_id + dept_id 三元 filter 实现领域隔离。

8 层各自的 importance / TTL 策略:
  books      importance=5 永不衰减 (经典)
  standards  importance=5 永不衰减 (法规)
  cases      importance=4 ELO 调节
  pitfalls   importance=4 永不衰减 (反知识)
  kols       importance=3 90 天衰减
  trends     importance=2 90 天衰减 (时效信息)
  slang      importance=2 永不衰减 (术语字典)
  history    importance=动态 用户反馈调节
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Literal
from urllib.parse import quote

BEE_MEMORY_URL = os.environ.get("BEE_MEMORY_URL", "http://127.0.0.1:8004")
BEE_BEARER = os.environ.get("BEE_BEARER_TOKEN", "dev-token-change-me")

KnowledgeLayer = Literal[
    "book", "trend", "case", "pitfall", "standard", "slang", "kol", "history"
]

LAYER_DEFAULTS: dict[str, dict[str, Any]] = {
    "book":     {"importance": 5, "novelty": 0.3, "predictive_value": 0.8},
    "standard": {"importance": 5, "novelty": 0.2, "predictive_value": 0.9},
    "case":     {"importance": 4, "novelty": 0.5, "predictive_value": 0.7},
    "pitfall":  {"importance": 4, "novelty": 0.3, "predictive_value": 0.85},
    "kol":      {"importance": 3, "novelty": 0.7, "predictive_value": 0.5},
    "trend":    {"importance": 2, "novelty": 0.9, "predictive_value": 0.4},
    "slang":    {"importance": 2, "novelty": 0.1, "predictive_value": 0.3},
    "history":  {"importance": 3, "novelty": 0.6, "predictive_value": 0.6},
}


def _post(path: str, payload: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{BEE_MEMORY_URL}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {BEE_BEARER}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _get(path: str, timeout: float = 5.0) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{BEE_MEMORY_URL}{path}",
        headers={"Authorization": f"Bearer {BEE_BEARER}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def add_knowledge(
    *,
    layer: KnowledgeLayer,
    mode_id: str,
    persona_id: str,
    dept_id: str,
    content: str,
    title: str = "",
    source_url: str = "",
    importance: int | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """加一条知识进 bee-memory.

    Returns: {"id": "...", "kind": "knowledge_book", ...}
    """
    d = LAYER_DEFAULTS.get(layer, LAYER_DEFAULTS["book"])
    meta: dict[str, Any] = {
        "layer": layer,
        "mode_id": mode_id,
        "persona_id": persona_id,
        "dept_id": dept_id,
        "title": title,
        "source_url": source_url,
        **(extra_meta or {}),
    }
    payload = {
        "kind": f"knowledge_{layer}",
        "content": content[:50_000],
        "mode_id": mode_id,
        "importance": int(importance if importance is not None else d["importance"]),
        "novelty": float(d["novelty"]),
        "predictive_value": float(d["predictive_value"]),
        "meta": json.dumps(meta, ensure_ascii=False),
    }
    try:
        return _post("/memory/store", payload)
    except Exception as e:
        return {"error": str(e), "fallback": "local_only"}


def _per_layer_k(layer: str) -> int:
    """层级分配: books 2, cases 3, pitfalls 2, standards 2, 其余 1."""
    alloc = {"book": 2, "case": 3, "pitfall": 2, "standard": 2}
    return alloc.get(layer, 1)


def recall_for_persona(
    *,
    mode_id: str,
    persona_id: str,
    query: str,
    k: int = 10,
    layers: list[KnowledgeLayer] | None = None,
    strategy: str = "activation",
) -> list[dict[str, Any]]:
    """按 persona_id 拉知识. 默认拉所有层, 用 v3-D 激活打分 + 沿边扩散.

    防过载机制 (此处实现):
    - k 默认 10 (硬上限)
    - 按层级分配: books×2 + cases×3 + pitfalls×2 + standards×2 + 其余×1
    - 领域硬隔离: 客户端按 meta.persona_id 严格 filter
    """
    if layers is None:
        layers = ["book", "case", "pitfall", "standard", "history"]

    all_items: list[dict[str, Any]] = []
    for layer in layers:
        try:
            resp = _get(
                f"/memory/recall?query={quote(query)}"
                f"&kind=knowledge_{layer}&k={_per_layer_k(layer)}&strategy={strategy}"
            )
            items = resp.get("items") or []
        except Exception:
            items = []
        for it in items:
            meta_str = it.get("meta") or "{}"
            try:
                meta = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
            except Exception:
                meta = {}
            if str(meta.get("persona_id")) != persona_id:
                continue
            it["_layer"] = layer
            it["_meta_parsed"] = meta
            all_items.append(it)
    all_items.sort(
        key=lambda x: (int(x.get("importance") or 0), int(x.get("recall_count") or 0)),
        reverse=True,
    )
    return all_items[:k]
