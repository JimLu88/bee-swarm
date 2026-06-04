# -*- coding: utf-8 -*-
"""books_rag —— 书库 RAG 灌库与检索管线。

组件:
- embed.py   可插拔嵌入器(本地 bge / OpenAI兼容API / 测试用确定性 / 无→FTS5纯关键词)
- store.py   sqlite-vec(向量) + FTS5(关键词) 混合检索库
- pipeline.py 扫投书文件夹 → 解析 → 切块 → 嵌入 → 入库 → 回写 .ingested.json;检索 API + CLI

设计:全本地、零大模型调用(嵌入用小模型/CPU)、数据不出机器;无 bge 也能降级 FTS5 运行。
"""
