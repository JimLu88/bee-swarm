"""
Resolvable paths for dev vs PyInstaller onefile.

When frozen, ``backend/app`` lives in a temp extract dir — never persist user data there.
Write runtime state next to ``sys.executable`` instead.
"""

from __future__ import annotations

import sys
from pathlib import Path


def backend_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parent.parent / "data"
