# -*- coding: utf-8 -*-
"""自动灌库 — 后端启动时把手写语料(corpus.CORPUS)幂等灌进 bee-memory。

- 用户无需敲任何命令: git pull + 重启后端即自动补齐缺失知识。
- 逐条幂等: 状态文件记录已灌的 (mode/dept/title), 只灌新增的, 不重复(语料增补也只灌新条)。
- best-effort: bee-memory 不可达/出错绝不影响后端启动。
- 强制重灌: 环境变量 BEE_RESEED=1, 或 CLI `python -m app.seed_knowledge.loader --force`。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from .corpus import CORPUS

log = logging.getLogger("bee.seed")


def _state_path() -> Path:
    try:
        from ..runtime_paths import backend_data_dir
        base = backend_data_dir()
    except Exception:
        base = Path(__file__).resolve().parent.parent.parent / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base / ".seed_state.json"


def _load_state() -> dict:
    p = _state_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_state(state: dict) -> None:
    try:
        _state_path().write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.warning("seed state save failed: %r", e)


def seed_sync(force: bool = False) -> dict:
    """同步灌库 (add_knowledge 是同步 urllib)。返回各 mode 的灌入统计。"""
    from ..persona.knowledge_store import add_knowledge

    if os.environ.get("BEE_RESEED", "0") == "1":
        force = True
    state = _load_state()
    result: dict[str, int] = {}
    for mode_id, depts in CORPUS.items():
        done = set() if force else set(state.get(mode_id, []))
        n = 0
        for dept_id, entries in depts.items():
            persona_id = f"head_{mode_id}_{dept_id}"
            for layer, title, content in entries:
                key = f"{dept_id}::{title}"
                if key in done:
                    continue
                r = add_knowledge(
                    layer=layer, mode_id=mode_id, persona_id=persona_id,
                    dept_id=dept_id, content=f"{title}。{content}", title=title,
                    extra_meta={"seeded_by": "hand-authored-corpus"},
                )
                if isinstance(r, dict) and r.get("error"):
                    continue  # bee-memory 不可达 → 不标记, 下次重试
                done.add(key)
                n += 1
        state[mode_id] = sorted(done)
        if n:
            result[mode_id] = n
    _save_state(state)
    return result


async def auto_seed() -> dict:
    """启动时后台调用 (放线程, 不阻塞事件循环)。"""
    try:
        res = await asyncio.to_thread(seed_sync, False)
        if res:
            log.info("auto_seed inserted: %s", res)
        return res
    except Exception as e:  # noqa: BLE001
        log.warning("auto_seed failed: %r", e)
        return {"error": repr(e)}


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    print(json.dumps(seed_sync(force=force), ensure_ascii=False, indent=2))
