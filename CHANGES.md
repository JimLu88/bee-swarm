# H-SEMAS 变更日志

> 每次部署后追加一行: 日期 / 内容 / 回滚点(commit 或备份)。流程#8。

## 2026-06-20 — 全面审视第二批 + 弹窗根除
- **弹窗根除**: supervisor 自愈循环(每60s误判 hands/input→重启→闪命令行窗口)是元凶; 已杀进程、删 Startup 的 `.bat`+`.vbs` 静默启动器、清注册表 Run 键, 并把 `supervisor.py` 自愈改为**默认关闭**(SUP_AUTOHEAL 默认0)。用户明确不要看门狗/自启。
- **action_lane 收敛**(执行#1#5): MAX_ITERS 3→env(默6) + SAFE 工具失败重试一次 + 连续两轮相同动作=卡死提前停。
- **工具频率限制**(执行#3): `tool_registry.execute_tool` 滑动窗口(SAFE 30/分, SENSITIVE 6/分, env 可调)。
- **进化日志持久化**(修 bug): `coordinator.DB_PATH` 挪到挂载卷 backend/data(原在镜像内每次 rebuild 清零)。
- **stats CLI 修正**(代码#3): 先读 meta.dim 再开库, 不再永远误报 vector:false。
- **dev_bandit 冷启动**(进化#3): 样本<10 时固定用 fix_loop 默认变体, 不被噪声乱推荐。
- **agent_hands 白名单**(执行#9): 加 powershell/pwsh/cmd/dotnet/uv(PC 代码手脚, 待 8002 重启生效)。
- **_scratch 约定**(流程#9): D:\AI\_scratch 放临时文件, 不碰 C 盘。
- **系统现状图**(整体#2#5#14): `docs/系统现状与职责图.md`。
- **SSH 端口变更**: 群晖 SSH 从 22 → **2222**(scp/ssh 都要 `-P/-p 2222`); deploy.ps1 默认端口待更新。
- 部署: action_lane/tool_registry/coordinator/pipeline + dev_bandit 已 scp+rebuild 上 NAS。回滚点 GitHub `ed83e93`。

## 2026-06-11 (晚) — 全面审视第一批
- **LLM 用量记账**: `llm/usage_tracker.py`(新) + litellm_client 挂钩 + `GET /api/llm/usage`。每次调用记 model/tokens/估价到 `data/llm_usage.jsonl`。
- **进化器改每周跑**: 默认间隔 3→7 天(`schedule_config.json` 写 7, 实时生效); `/coordinator/status` 接真实运行数据(last_run/runs_30d/proposals_30d); 低产出(30天≥4跑零提案)自动降为每月1-7日跑。
- **书库 scenario 前置过滤**: hybrid_search 先 SQL 缩小 rowid 集再 KNN/FTS(百万级→万级), 老版 sqlite-vec 自动回退全量。
- **书库引用可见**: DecisionSummary 加 `books_refs`; CEO 综合与 answer_lane 命中的真书在 ResultPanel「📚 引用书目」折叠区展示。
- **answer_lane 接书库**: 问答车道先查 1735 本真书(免费权威)再联网, 真书用《书名》标注。
- **lane 分类留痕**: 每次分流记 requested vs resolved 到 `data/lane_audit.jsonl`, 供复盘错分率。
- **CEO 置信度**: 通用 CEO 输出末尾固定「置信度 X/10 + 三个关键前提」, 证据薄弱必须 ≤5 并标注。
- **store 缓存可失效**: `invalidate_store_cache()`(换库/重灌后调用)。
- **mobi/azw3 抢救**: Calibre 批量转换 212/220 本成功 → 增量重灌中。
- **deploy.ps1**(新): PC 端一键部署(校验→scp→rebuild→healthz)。
- 回滚点: GitHub commit `ed83e93`(本批之前) / 本批部署文件在 NAS `/tmp` 有副本。

## 2026-06-10/11 — dev_mode 轮数改造 + 灌书
- dev_mode: 成功率收敛(reward≥0.85/停滞/8轮上限)/配额暂停续跑+自动探针/STOP 真杀(agent-hands `/cancel`)/真机门/卡死检测。GitHub `ed83e93`。
- 灌书: 1735 本 / 135万 chunk / 9.36GB books.sqlite(GPU+fitz), NAS TEI(bge-small-zh, 512d)自托管嵌入, 查询端 `.env` 已切 TEI(原 SiliconFlow 配置留 `#SF_OLD`)。
- agent-hands: subprocess.run→Popen + `/task/{id}/cancel` 真杀 + quota_hit 标记。**必须以普通用户运行**(管理员进程里 claude CLI 403)。
