"""dev_state — 开发模式的全局停止信号 + 配额暂停存档 + 在途任务注册.

三件事:
1. STOP 键: 进程内 Event + dev_stop.flag 文件(持久兜底). is_stopped() 各层轮询, 命中即停.
2. 配额暂停: claude 配额用尽时把整个 dev session 进度存 dev_state/{dev_id}.json, 供恢复续跑.
3. 在途任务注册: dev_id -> {agent task_id}, STOP 时据此逐个 agent_cancel(真杀 claude 子进程).
"""
from __future__ import annotations

import json
import time
import threading
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent.parent / "data" / "software_dev"
_DIR.mkdir(parents=True, exist_ok=True)
_STOP_FLAG = _DIR / "dev_stop.flag"
_STATE_DIR = _DIR / "dev_state"
_STATE_DIR.mkdir(parents=True, exist_ok=True)

_stop_event = threading.Event()
_lock = threading.Lock()
_active_tasks: dict[str, set[str]] = {}  # dev_id -> set(agent task_id)


# ---------- STOP 信号 ----------
def request_stop() -> None:
    """前端 STOP 键 → 置全局停止信号(内存 Event + 持久 flag)。"""
    _stop_event.set()
    try:
        _STOP_FLAG.write_text(str(int(time.time())), encoding="utf-8")
    except Exception:
        pass


def clear_stop() -> None:
    """开始一次新 dev session 前清除停止信号(否则残留 flag 会永久拦)。"""
    _stop_event.clear()
    try:
        _STOP_FLAG.unlink(missing_ok=True)
    except Exception:
        pass


def is_stopped() -> bool:
    if _stop_event.is_set():
        return True
    return _STOP_FLAG.exists()


# ---------- 在途 agent 任务注册(STOP 时逐个真杀)----------
def register_task(dev_id: str, task_id: str) -> None:
    if not dev_id or not task_id:
        return
    with _lock:
        _active_tasks.setdefault(dev_id, set()).add(task_id)


def unregister_task(dev_id: str, task_id: str) -> None:
    with _lock:
        s = _active_tasks.get(dev_id)
        if s:
            s.discard(task_id)
            if not s:
                _active_tasks.pop(dev_id, None)


def active_task_ids() -> list[tuple[str, str]]:
    with _lock:
        return [(d, t) for d, ts in _active_tasks.items() for t in list(ts)]


# ---------- 配额暂停存档 ----------
def save_pause(dev_id: str, state: dict[str, Any]) -> None:
    """把 dev session 当前进度存盘(状态=paused_quota), 供恢复续跑。"""
    rec = dict(state)
    rec["dev_id"] = dev_id
    rec["status"] = "paused_quota"
    rec["paused_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    rec["paused_ts"] = int(time.time())
    try:
        (_STATE_DIR / f"{dev_id}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_pause(dev_id: str) -> dict[str, Any] | None:
    p = _STATE_DIR / f"{dev_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_paused() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in sorted(_STATE_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("status") == "paused_quota":
                out.append(d)
        except Exception:
            continue
    return out


def clear_pause(dev_id: str) -> None:
    try:
        (_STATE_DIR / f"{dev_id}.json").unlink(missing_ok=True)
    except Exception:
        pass
