# -*- coding: utf-8 -*-
"""#4 现成开放数据集 → 灌进向量库(合法、零版权风险)。

MedRAG Textbooks(AdarshDS/textbooks,18 本权威医学教科书切块片段,合法开放),
打到医学相关场景(家庭医生/慢病/体检/睡眠/营养/心理)。

国内可用方案:用 `huggingface_hub` 直接下载仓库里的 chunk/*.jsonl 原始文件
(它原生识别环境变量 HF_ENDPOINT → 走镜像 https://hf-mirror.com 的 resolve/ 路径,
镜像站对 resolve 文件是真代理的;而之前用的自动 parquet 接口镜像站不代理,故失败)。

数据集结构(每行一个 JSON):
  id       片段唯一 id
  title    该片段所属教科书名
  content  片段正文(≤1000 字符)
  contents title + content 拼接(BM25 用)

诚实须知:数据是**英文**。要让中文提问也召回,嵌入器建议多语模型(我们用通义
text-embedding-v3,本身多语)。片段总量 ~12.6 万,默认限量防止把群晖 CPU/额度跑爆。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from .embed import get_embedder
from .pipeline import _db_path
from .store import BookStore

MED_SCENARIOS = "family_doctor, chronic_disease, health_checkup, sleep_health, nutrition_fitness, mental_wellness"
_REPO = "AdarshDS/textbooks"

# 18 本教科书的 chunk 文件(按体积从小到大排,limit_chunks 截断时优先覆盖更多不同的书,
# 且避免为取少量片段而下载 52MB 的 Harrison)。文件名含原仓库的拼写(Obstentrics/Psichiatry),
# 必须与仓库完全一致。
_CHUNK_FILES: List[str] = [
    "chunk/Pathoma_Husain.jsonl",
    "chunk/First_Aid_Step1.jsonl",
    "chunk/First_Aid_Step2.jsonl",
    "chunk/Biochemistry_Lippincott.jsonl",
    "chunk/Anatomy_Gray.jsonl",
    "chunk/Pediatrics_Nelson.jsonl",
    "chunk/Psichiatry_DSM-5.jsonl",
    "chunk/Physiology_Levy.jsonl",
    "chunk/Histology_Ross.jsonl",
    "chunk/Immunology_Janeway.jsonl",
    "chunk/Pathology_Robbins.jsonl",
    "chunk/Cell_Biology_Alberts.jsonl",
    "chunk/Pharmacology_Katzung.jsonl",
    "chunk/Gynecology_Novak.jsonl",
    "chunk/Obstentrics_Williams.jsonl",
    "chunk/Neurology_Adams.jsonl",
    "chunk/Surgery_Schwartz.jsonl",
    "chunk/InternalMed_Harrison.jsonl",
]


def _download(fname: str) -> str:
    """用 huggingface_hub 下载单个 chunk 文件,返回本地路径。
    huggingface_hub 原生读 HF_ENDPOINT 环境变量 → 国内自动走 hf-mirror.com。"""
    from huggingface_hub import hf_hub_download
    return hf_hub_download(repo_id=_REPO, filename=fname, repo_type="dataset")


def fetch_medrag(limit_chunks: int = 8000, embed_vectors: bool = True) -> dict:
    """拉 MedRAG textbooks 片段灌进向量库(打医学场景标签)。

    limit_chunks: 最多灌多少片段(默认 8000;设 0 = 全量 ~12.6 万,慢)。
    embed_vectors: True=算向量(慢但跨语种好);False=只进 FTS5 关键词(快、省)。
    """
    emb = get_embedder() if embed_vectors else None
    dim = emb.dim if emb else None
    store = BookStore(_db_path(), dim)
    if dim:
        store.set_meta("dim", str(dim))

    n_books = n_chunks = total = 0
    errors: List[str] = []

    for fname in _CHUNK_FILES:
        if limit_chunks and total >= limit_chunks:
            break
        try:
            local = _download(fname)
        except Exception as e:  # noqa: BLE001  单本下载失败不挂整批,但要记录(不静默)
            errors.append(f"{fname}: {e!r}")
            continue

        title = Path(fname).stem  # 兜底书名;若行内有 title 字段则用之
        chunks: List[str] = []
        try:
            with open(local, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if limit_chunks and total >= limit_chunks:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    content = (obj.get("content") or obj.get("contents") or "").strip()
                    if not content:
                        continue
                    if obj.get("title"):
                        title = str(obj["title"])
                    chunks.append(content)
                    total += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"read {fname}: {e!r}")
            continue

        if not chunks:
            continue
        vecs = emb.encode(chunks) if emb else None
        store.add_book("medrag::" + fname, title, "MedRAG", MED_SCENARIOS,
                       "opendata", "medrag", len(chunks), chunks, vecs, commit=False)
        store.commit()
        n_books += 1
        n_chunks += len(chunks)

    st = store.stats()
    store.close()
    ok = n_chunks > 0
    return {
        "ok": ok,
        "dataset": "MedRAG/AdarshDS-textbooks",
        "scenarios": MED_SCENARIOS,
        "hf_endpoint": os.environ.get("HF_ENDPOINT", "https://huggingface.co"),
        "medrag_books": n_books,        # 本次真正灌入的 MedRAG 书数
        "medrag_chunks": n_chunks,      # 本次真正灌入的 MedRAG 片段数
        "total_books": st["books"],     # 全库总数(含卡片)
        "total_chunks": st["chunks"],
        "vector": st["vector"],
        "dim": st["dim"],
        "errors": errors[:5],           # 失败原因(最多列 5 条,不静默吞掉)
    }
