# -*- coding: utf-8 -*-
"""#4 现成开放数据集 → 灌进向量库(合法、零版权风险)。

MedRAG Textbooks(AdarshDS/textbooks,18 本权威医学教科书的切块片段,合法开放),
打到医学相关场景上(家庭医生/慢病/体检/睡眠/营养/心理)。

实现:**不依赖 `datasets` 库**(它跟新版 numpy/pandas 冲突, 会把 pip 拖进回退地狱)。
改为直接拉 HuggingFace 的 parquet 文件, 用 pandas(+pyarrow)读取。

诚实须知:
- 数据集是**英文**。要让中文提问也召回, 嵌入器建议用多语 bge-m3(BOOKS_EMBED_MODEL=BAAI/bge-m3)。
- 片段多(~12万), 默认限量, 防止把群晖 CPU 跑爆。
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import List

from .embed import get_embedder
from .pipeline import _db_path
from .store import BookStore

MED_SCENARIOS = "family_doctor, chronic_disease, health_checkup, sleep_health, nutrition_fitness, mental_wellness"
_REPO = "AdarshDS/textbooks"
_UA = {"User-Agent": "h-semas-books/2.0"}
# 国内 NAS 直连 huggingface.co 会 OSError 99 → 用 HF_ENDPOINT 走镜像(如 https://hf-mirror.com)
_HF = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")


def _parquet_urls(repo: str) -> List[str]:
    """从 HF parquet API 取该数据集的 parquet 文件 URL 列表(不需 datasets 库)。"""
    api = f"{_HF}/api/datasets/{repo}/parquet"
    req = urllib.request.Request(api, headers=_UA)
    data = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
    # data 形如 {"default": {"train": ["url1","url2",...]}}
    urls: List[str] = []
    if isinstance(data, dict):
        for _cfg, splits in data.items():
            if isinstance(splits, dict):
                for _sp, lst in splits.items():
                    if isinstance(lst, list):
                        urls.extend([u for u in lst if isinstance(u, str)])
    elif isinstance(data, list):
        urls = [u for u in data if isinstance(u, str)]
    # API 返回的下载 URL 仍指向官方域名 → 重写到镜像,否则 read_parquet 又连不上
    if _HF != "https://huggingface.co":
        urls = [u.replace("https://huggingface.co", _HF) for u in urls]
    return urls


def fetch_medrag(limit_chunks: int = 8000, embed_vectors: bool = True) -> dict:
    """拉 MedRAG textbooks 片段灌进向量库(打医学场景标签)。

    limit_chunks: 最多灌多少片段(默认 8000;设 0 = 全量~12万)。
    embed_vectors: True=算向量(慢但跨语种好);False=只进 FTS5 关键词(快、省)。
    """
    try:
        import pandas as pd  # pandas 已装;读 parquet 需 pyarrow
    except Exception:
        return {"ok": False, "error": "需要 pandas+pyarrow: 容器内 pip install pyarrow"}

    try:
        urls = _parquet_urls(_REPO)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"取 parquet 列表失败: {e!r}"}
    if not urls:
        return {"ok": False, "error": "未找到该数据集的 parquet 文件"}

    emb = get_embedder() if embed_vectors else None
    dim = emb.dim if emb else None
    store = BookStore(_db_path(), dim)
    if dim:
        store.set_meta("dim", str(dim))

    n_books = n_chunks = total = 0

    def _flush(title, chunks: List[str]) -> None:
        nonlocal n_books, n_chunks
        if not chunks:
            return
        vecs = emb.encode(chunks) if emb else None
        store.add_book("medrag::" + str(title), str(title), "MedRAG", MED_SCENARIOS,
                       "opendata", "medrag", len(chunks), chunks, vecs, commit=False)
        store.commit()
        n_books += 1
        n_chunks += len(chunks)

    for url in urls:
        if limit_chunks and total >= limit_chunks:
            break
        try:
            df = pd.read_parquet(url)
        except Exception:
            continue
        cur_title, buf = None, []
        for _, row in df.iterrows():
            if limit_chunks and total >= limit_chunks:
                break
            title = str(row.get("title") or "MedRAG")
            content = str(row.get("content") or row.get("contents") or "").strip()
            if not content:
                continue
            if cur_title is None:
                cur_title = title
            if title != cur_title:
                _flush(cur_title, buf)
                buf, cur_title = [], title
            buf.append(content)
            total += 1
        _flush(cur_title, buf)

    st = store.stats()
    store.close()
    return {"ok": True, "dataset": "MedRAG/AdarshDS-textbooks", "scenarios": MED_SCENARIOS,
            "parquet_files": len(urls), "books": n_books, "chunks": n_chunks,
            "vectors": bool(emb), **st}
