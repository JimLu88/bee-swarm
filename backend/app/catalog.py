"""部门名清单 — v6-A 改成从 modes.MODES 动态列举.

历史: 原本从 get_args(DeptName Literal) 取。改 str 后 Literal 不存在了, 改这里。
"""
from __future__ import annotations


def list_dept_names() -> list[str]:
    """所有已注册 mode 用过的 dept 名 (去重 + 保序). 给 yaml 编辑器/校验用."""
    from .modes import MODES, list_modes

    seen: set[str] = set()
    out: list[str] = []
    for m in MODES.values():
        for d in m.departments:
            if d not in seen:
                seen.add(d)
                out.append(d)
    # extra_mode_loader 的 mode 也加进来 (它们可能定义新 dept)
    try:
        for m in list_modes():
            for d in m.departments:
                if d not in seen:
                    seen.add(d)
                    out.append(d)
    except Exception:
        pass
    return out
