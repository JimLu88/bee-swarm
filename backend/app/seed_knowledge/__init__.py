"""seed_knowledge — 手写知识库语料 + 部署时自动灌库 (零 LLM)。

- corpus.py: 人工撰写的知识条 (gift_selection + 15 产业后台场景), 单一真相源。
- loader.py: 后端启动时自动把语料幂等灌进 bee-memory (按 persona_id 绑定), 用户无需敲任何命令。
"""
