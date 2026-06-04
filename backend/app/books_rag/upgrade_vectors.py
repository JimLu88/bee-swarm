# -*- coding: utf-8 -*-
"""一键把书库升级成「语义向量版」。

流程:自检嵌入器(必须是 API 通义/DashScope)→ 真实嵌入自检 →
重灌 2610 书目卡片(带向量)→ 灌 MedRAG 医学教科书(带向量)。

用法(容器内):
    python -m app.books_rag.upgrade_vectors            # MedRAG 默认灌 8000 片段
    python -m app.books_rag.upgrade_vectors 0          # MedRAG 全量(~12 万,慢)
    python -m app.books_rag.upgrade_vectors 4000       # 自定义片段上限

前置:.env 配 BOOKS_EMBED_API_KEY(通义),并已 `docker compose up -d backend`
让环境变量进容器。无 key 时本脚本直接报错退出(不会静默降级)。
"""
from __future__ import annotations

import json
import sys

from .embed import get_embedder
from .pipeline import ingest_cards


def main() -> None:
    med_chunks = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

    e = get_embedder()
    name = getattr(e, "name", None)
    dim = getattr(e, "dim", None)
    print(f"[1/4] 嵌入器: {name} | 维度: {dim}")
    if not e or not str(name or "").startswith("api:"):
        print("✗ 未检测到 API 嵌入器(通义)。请确认:")
        print("   1) .env 里 BOOKS_EMBED_API_KEY=<你的DashScope key> 已写好")
        print("   2) 已执行 `docker compose up -d backend` 让变量进容器")
        print("   当前会是关键词(FTS5)模式 —— 能用但没有语义向量,故中止升级。")
        sys.exit(2)

    # 真实嵌入自检(顺带验证 key 有效 + 批处理路径)
    v = e.encode(["心力衰竭的一线用药与禁忌", "糖尿病饮食管理要点"])
    print(f"[2/4] 嵌入自检 OK,返回 {len(v)} 条,每条维度 {len(v[0])}")

    # 重灌 2610 卡片为带向量版(force=True 覆盖旧的纯关键词卡片)
    r1 = ingest_cards(force=True)
    print("[3/4] 书目卡片重灌(带向量):", json.dumps(r1, ensure_ascii=False))

    # 灌 MedRAG 医学教科书(合法开放数据集)
    try:
        from .fetch_opendata import fetch_medrag
        r2 = fetch_medrag(med_chunks, True)
        print("[4/4] MedRAG:", json.dumps(r2, ensure_ascii=False))
    except Exception as ex:  # noqa: BLE001  MedRAG 失败不影响卡片升级
        print("[4/4] MedRAG 跳过(可稍后单独重跑):", repr(ex))

    print("✓ 升级完成。决策检索现在走「语义向量 + 关键词」混合(RRF)。")


if __name__ == "__main__":
    main()
