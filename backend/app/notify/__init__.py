"""notify — 外部通知渠道 (企业微信 webhook 等). 给开发模式的人工环节强提醒用."""
from .wecom import notify, notify_markdown, is_configured

__all__ = ["notify", "notify_markdown", "is_configured"]
