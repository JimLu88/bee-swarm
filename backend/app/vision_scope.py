"""Shared definition of vision-layer departments (benchmark + xlab)."""

from __future__ import annotations

VISION_DEPTS = frozenset({"benchmark", "xlab"})


def is_vision_dept(dept: str) -> bool:
    return dept in VISION_DEPTS
