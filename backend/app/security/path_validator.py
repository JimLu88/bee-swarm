"""v3-G 安全隔离区 v2: 三级路径管控 (黑/灰/白)."""
from __future__ import annotations
from pathlib import Path
import os


# 默认黑名单 (强烈推荐用户初装时弹窗扩充)
BLACKLIST_DEFAULT = [
    r"C:\Users\*\Documents\私密",
    r"D:\个人财务",
    r"C:\Windows\System32",
    "%APPDATA%\\Microsoft\\Credentials",
]
GRAYLIST_DEFAULT = [r"C:\Windows"]  # 只读
WHITELIST_DEFAULT = [r"D:\AI\workspace"]


def is_allowed(path: str, mode: str = "read") -> bool:
    """mode: read|write"""
    p = Path(os.path.expandvars(path)).resolve()
    # blacklist always blocks
    for b in BLACKLIST_DEFAULT:
        if str(p).lower().startswith(os.path.expandvars(b).lower().rstrip("*\\")):
            return False
    if mode == "write":
        # write only allowed in whitelist
        return any(str(p).lower().startswith(os.path.expandvars(w).lower()) for w in WHITELIST_DEFAULT)
    # read: gray + white allowed
    return True


def audit(path: str, action: str, allowed: bool, reason: str = "") -> None:
    """记入审计日志(scaffold: print to stderr)."""
    import sys
    print(f"[path_validator] action={action} path={path} allowed={allowed} reason={reason}", file=sys.stderr)