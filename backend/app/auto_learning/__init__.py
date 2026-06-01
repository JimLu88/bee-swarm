"""v9 自学习闭环 — 联网新知自动入库 + 每天 20:00 CEO 梳理 + 后台场景懒加载.

三块:
  inbox.py     决策时把联网搜索命中写进"知识收件箱" (pending)
  digest.py    每天 20:00 CEO 模型读收件箱 → 去重/提炼 → 写进 bee-memory (layer=trend, source=web)
  lazy_seed.py 未手写灌书的后台场景, 配置部门时用 DeepSeek 按 30/50/80 分层灌专业书库
  api.py       /api/learning/** 状态查询 + 手动触发 (确保联通能触发)
"""
