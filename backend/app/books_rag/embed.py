# -*- coding: utf-8 -*-
"""可插拔嵌入器。优先级:OpenAI兼容API > 本地 bge(sentence-transformers) > 测试用确定性 > 无。

环境变量:
- BOOKS_EMBED_API_KEY / BOOKS_EMBED_API_BASE / BOOKS_EMBED_MODEL  → 走 OpenAI 兼容 /embeddings(如通义/DashScope)
- 否则若装了 sentence-transformers → 本地 bge(BOOKS_EMBED_MODEL 默认 BAAI/bge-small-zh-v1.5,dim 512)
- 否则 BOOKS_EMBED_FAKE=1 → 确定性哈希嵌入(仅测试/兜底,无语义)
- 否则 None → 调用方走 FTS5 纯关键词模式
"""
from __future__ import annotations

import hashlib
import math
import os
import struct
from typing import List, Optional, Protocol


class Embedder(Protocol):
    name: str
    dim: int
    def encode(self, texts: List[str]) -> List[List[float]]: ...


def _l2norm(v: List[float]) -> List[float]:
    s = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / s for x in v]


class STEmbedder:
    """本地 sentence-transformers bge。CPU 可跑,数据不出机器。"""
    def __init__(self, model: str):
        from sentence_transformers import SentenceTransformer  # 延迟导入
        self._m = SentenceTransformer(model)
        self.name = f"st:{model}"
        self.dim = int(self._m.get_sentence_embedding_dimension())

    def encode(self, texts: List[str]) -> List[List[float]]:
        vecs = self._m.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return [list(map(float, v)) for v in vecs]


class APIEmbedder:
    """OpenAI 兼容 /embeddings(通义 text-embedding-v3 等)。便宜、批量。"""
    def __init__(self, base: str, key: str, model: str, dim: int):
        self._base = base.rstrip("/")
        self._key = key
        self.name = f"api:{model}"
        self.dim = dim
        self._model = model

    def encode(self, texts: List[str]) -> List[List[float]]:
        import json
        import urllib.request
        body = json.dumps({"model": self._model, "input": texts}).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base}/embeddings", data=body,
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [_l2norm([float(x) for x in d["embedding"]]) for d in data["data"]]


class DeterministicEmbedder:
    """确定性哈希嵌入(无语义)—— 仅用于本地测试 sqlite-vec 链路 / 极端兜底。"""
    def __init__(self, dim: int = 64):
        self.name = "deterministic-test"
        self.dim = dim

    def encode(self, texts: List[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for t in texts:
            v = [0.0] * self.dim
            toks = [t[i:i + 2] for i in range(0, len(t), 1)] or [t]
            for tok in toks:
                h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
                v[h % self.dim] += 1.0
            out.append(_l2norm(v))
        return out


_CACHED: list = []  # 单例缓存: 模型只加载一次, 常驻复用 (避免每次检索重载, 关键性能点)


def get_embedder() -> Optional[Embedder]:
    """按优先级返回嵌入器(单例缓存)。返回 None 表示无可用嵌入器(走 FTS5 纯关键词)。"""
    if _CACHED:
        return _CACHED[0]
    emb = _build_embedder()
    _CACHED.append(emb)  # 含 None 也缓存, 避免反复尝试加载失败的模型
    return emb


def _build_embedder() -> Optional[Embedder]:
    key = os.environ.get("BOOKS_EMBED_API_KEY", "").strip()
    if key:
        base = os.environ.get("BOOKS_EMBED_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        model = os.environ.get("BOOKS_EMBED_MODEL", "text-embedding-v3")
        dim = int(os.environ.get("BOOKS_EMBED_DIM", "1024"))
        return APIEmbedder(base, key, model, dim)
    try:
        import sentence_transformers  # noqa: F401
        model = os.environ.get("BOOKS_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
        return STEmbedder(model)
    except Exception:
        pass
    if os.environ.get("BOOKS_EMBED_FAKE") == "1":
        return DeterministicEmbedder(int(os.environ.get("BOOKS_EMBED_DIM", "64")))
    return None


def serialize_f32(vec: List[float]) -> bytes:
    """打包成 sqlite-vec 需要的 float32 字节串。"""
    return struct.pack(f"{len(vec)}f", *vec)
