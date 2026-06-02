"""dev_mode — H-SEMAS 开发模式: 群晖大脑指挥 PC 上的 Claude Code 写程序.

子模块:
- records       dev-run 记录读写 + 奖励计算 + 成功次数(进化触发用)
- dev_bandit    编码 SOP 变体的 Thompson 采样选择 + 奖励回写
- prompt_optimizer  轻量提示词优化器(复用 gene_evolve 模式, 可换 DSPy)
- planner       意图→优化 SPEC→拆 DevTask
- executor      并行执行(每 task 一个 worktree, 调 claude)
- worktree      PC 上 git worktree 增删
- verify        三路验证(跑测试 / LLM 评审 / 人类测试员)
- human_tester  人类测试员(bee-vision 看 + bee-input 点)
- constraints   CLAUDE.md / learnings.md / rules 生成与晋升
- session       dev-loop 状态机主入口 run_dev_session
"""
