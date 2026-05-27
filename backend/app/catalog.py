from __future__ import annotations

from typing import get_args

from .models import DeptName


def list_dept_names() -> list[str]:
    """All valid ``DeptName`` literals (order matches ``models.DeptName`` union)."""
    return list(get_args(DeptName))
