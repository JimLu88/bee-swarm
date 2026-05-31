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


import re as _re


def _task_ngrams(task: str, lengths: tuple[int, ...] = (2, 3, 4)) -> set[str]:
    """把任务切成 2-4 字 n-gram 关键词集 (中文无需分词库的轻量相关性匹配).
    去掉空白与标点; 限长防止 gram 爆炸."""
    t = _re.sub(r"[\s,，。.;；:：!！?？、()（）\[\]【】\"'`]+", "", task or "")[:200]
    grams: set[str] = set()
    for k in lengths:
        for i in range(len(t) - k + 1):
            grams.add(t[i:i + k])
    return grams


def _relevance(grams: set[str], text: str) -> int:
    """书的 (标题+正文) 命中多少个任务 n-gram → 相关性分. grams 空则恒 0 (回退重要度)."""
    if not grams or not text:
        return 0
    hit = 0
    for g in grams:
        if g in text:
            hit += 1
    return hit


def _per_layer_k(layer: str) -> int:
    """层级分配 (单次召回每层取几条). book 给最多 (人设读的几十本书是主力知识源),
    activation 打分会从该 persona 全部书里选最相关/最重要的几本进 prompt."""
    alloc = {"book": 6, "case": 3, "pitfall": 3, "standard": 3}
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

    # v8: 相关性匹配. 把整句任务切成 n-gram, 按"和这本书内容的重叠度"重排,
    # 让冷门但相关的书也能被精准调出 (而非只看重要度). query 空 → grams 空 → 回退重要度.
    grams = _task_ngrams(query)

    all_items: list[dict[str, Any]] = []
    for layer in layers:
        try:
            # 服务端按 persona_id 过滤 (领域硬隔离) + activation 排序; 这里多取一些(该人设的书<=80,
            # 取 60 基本是全量), 拿回来后用相关性在客户端重排, 避免相关书被 activation 预截断.
            resp = _get(
                f"/memory/recall"
                f"?kind=knowledge_{layer}&k=60"
                f"&strategy={strategy}&persona_id={quote(persona_id)}"
            )
            items = resp.get("items") or []
        except Exception:
            items = []
        cand: list[dict[str, Any]] = []
        for it in items:
            meta_str = it.get("meta") or "{}"
            try:
                meta = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
            except Exception:
                meta = {}
            if str(meta.get("persona_id")) != persona_id:
                continue  # 双保险: 服务端已过滤, 这里再校验一次
            it["_layer"] = layer
            it["_meta_parsed"] = meta
            it["_relevance"] = _relevance(
                grams, str(it.get("content") or "") + str(meta.get("title") or "")
            )
            cand.append(it)
        # 本层内: 先相关性, 再重要度, 再频率; 取该层配额
        cand.sort(
            key=lambda x: (int(x.get("_relevance") or 0),
                           int(x.get("importance") or 0),
                           int(x.get("recall_count") or 0)),
            reverse=True,
        )
        all_items.extend(cand[:_per_layer_k(layer)])
    # 跨层汇总同样: 相关性优先, 其次重要度
    all_items.sort(
        key=lambda x: (int(x.get("_relevance") or 0),
                       int(x.get("importance") or 0),
                       int(x.get("recall_count") or 0)),
        reverse=True,
    )
    return all_items[:k]
