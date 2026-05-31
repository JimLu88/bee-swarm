"""seed_knowledge — 手写专业书库, 批量灌进 bee-memory 记忆库.

不调任何外部 API / LLM: 内容全部手写 (真实书名 + 核心要点浓缩).
按 persona 的 dept + role 定制每人 ~30 本.

只灌前台 13 个内置场景 (ModePicker.BUILTIN_MODES); 后台 50 extra 场景留懒加载.
"""
