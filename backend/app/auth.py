"""轻量登录鉴权 (单用户密码 + HMAC 签名 Token, 无需数据库).

设计:
- 设了密码 → 全站 /api/** 需登录; 没设密码 → 鉴权关闭 (向后兼容, 现状不变).
- 密码来源: 环境变量 HSEMAS_APP_PASSWORD (优先) 或 设置面板 app_password (落盘 hub_settings, 同步进 env).
- Token = f"{exp}.{hmac_hex}"; 密钥由密码派生 → 改密码后旧 Token 全部失效.
- 配合 HTTPS 反向代理使用 (公网暴露时务必走 https).

只用标准库 (hmac/hashlib/time), 不引入新依赖.

调用方: backend/app/main.py (鉴权中间件 + /api/auth/login + /api/auth/status + WS decision_stream).
本模块不读写任何数据文件; 密码持久化由 hub_settings.json 脱敏机制负责 (字段 app_password).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

# Token 默认有效期 (天). 30 天 = 一次登录基本一个月不用再输.
_TOKEN_TTL_DAYS = 30
_KEY_PREFIX = b"hsemas-auth-v1|"


def _current_password() -> str:
    """当前生效的登录密码 (空 = 未设 = 鉴权关闭)."""
    pw = os.environ.get("HSEMAS_APP_PASSWORD", "").strip()
    if pw:
        return pw
    # 兜底: .env 启动时载入的 settings (GUI 改密码会同步写 env, 上面已覆盖).
    try:
        from .settings import settings  # 延迟导入避免环依赖

        return (getattr(settings, "app_password", "") or "").strip()
    except Exception:
        return ""


def auth_enabled() -> bool:
    """是否启用登录 (设了密码才启用)."""
    return bool(_current_password())


def _derive_key(password: str) -> bytes:
    return hashlib.sha256(_KEY_PREFIX + password.encode("utf-8")).digest()


def _sign(exp: int, password: str) -> str:
    return hmac.new(_derive_key(password), str(exp).encode("ascii"), hashlib.sha256).hexdigest()


def make_token(ttl_days: int = _TOKEN_TTL_DAYS) -> str:
    """签发一个登录 Token (调用方需先确认密码正确)."""
    password = _current_password()
    if not password:
        return ""
    exp = int(time.time()) + ttl_days * 86_400
    return f"{exp}.{_sign(exp, password)}"


def verify_token(token: str) -> bool:
    """校验 Token 是否有效 (签名正确且未过期)."""
    if not token or "." not in token:
        return False
    password = _current_password()
    if not password:
        # 鉴权关闭时, 任何 Token 都算通过 (路由层本就放行).
        return True
    exp_str, _, sig = token.partition(".")
    try:
        exp = int(exp_str)
    except ValueError:
        return False
    if exp < int(time.time()):
        return False
    expected = _sign(exp, password)
    return hmac.compare_digest(expected, sig)


def verify_password(password: str) -> bool:
    """登录时校验用户输入的密码 (常数时间比较)."""
    current = _current_password()
    if not current:
        return False
    return hmac.compare_digest(current, (password or ""))


# ============ 防暴力破解: 连续失败 → 按来源 IP 锁定一段时间 (内存级, 重启清零) ============
_LOCK_THRESHOLD = 5          # 连续失败几次后开始锁定
_LOCK_BASE_SEC = 30          # 首次锁定秒数
_LOCK_MAX_SEC = 900          # 锁定上限 (15 分钟)
_attempts: dict[str, dict] = {}  # ip -> {"fails": int, "until": float}


def login_locked(ip: str) -> float:
    """返回该 IP 当前剩余锁定秒数 (0 = 未锁)."""
    rec = _attempts.get(ip)
    if not rec:
        return 0.0
    remain = rec.get("until", 0.0) - time.time()
    return remain if remain > 0 else 0.0


def record_login_failure(ip: str) -> None:
    """记一次失败; 超过阈值后按指数退避锁定 (30s→60s→120s…封顶15分钟)."""
    rec = _attempts.setdefault(ip, {"fails": 0, "until": 0.0})
    rec["fails"] = int(rec.get("fails", 0)) + 1
    if rec["fails"] >= _LOCK_THRESHOLD:
        over = rec["fails"] - _LOCK_THRESHOLD
        cooldown = min(_LOCK_BASE_SEC * (2 ** over), _LOCK_MAX_SEC)
        rec["until"] = time.time() + cooldown


def record_login_success(ip: str) -> None:
    """登录成功 → 清空该 IP 的失败记录."""
    _attempts.pop(ip, None)
