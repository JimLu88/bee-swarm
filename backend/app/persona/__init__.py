"""v6-A 动态部门 + 人设池模块.

team_store: 读写 backend/scenarios/teams/<mode_id>.yaml (持久化的 AI 生成的团队)
team_generator: 调 Opus 联网调研 + 生成完整团队 (含 6 家旗舰主管 + 本地职员 + CEO)
team_api: 5 个 HTTP 端点 (generate / regen-dept / regen-persona / put-prompt / get)
model_capabilities.yaml: 全球 Tier-1 旗舰快照, fallback 给 Opus 当知识库
"""
