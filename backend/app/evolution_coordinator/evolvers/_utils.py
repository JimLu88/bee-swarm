"""evolvers 共享工具: 读决策 / 读人设 / 廉价 LLM 调用 / 写 jsonl 报告."""
from __future__ import annotations
import os
import json
import time
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("bee.evolvers")

BACKEND_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
DATA_ROOT.mkdir(parents=True, exist_ok=True)

CHEAP_MODEL = os.environ.get("BEE_EVOLVER_MODEL", "deepseek/deepseek-chat")


def evolver_log_path(evolver_name: str) -> Path:
    return DATA_ROOT / f"{evolver_name}.jsonl"


def append_log(evolver_name: str, payload: dict[str, Any]) -> None:
    p = evolver_log_path(evolver_name)
    payload = {"ts": int(time.time()), **payload}
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_recent_decisions(limit: int = 30) -> list[dict[str, Any]]:
    """读最近 N 条 decision_memory JSONL (跨所有 mode)."""
    out: list[dict[str, Any]] = []
    decision_dir = BACKEND_ROOT / "data" / "decision_memory"
    if not decision_dir.is_dir():
        return out
    files = sorted(decision_dir.glob("*.jsonl"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files[:8]:
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
            for ln in reversed(lines):
                if not ln.strip():
                    continue
                try:
                    out.append(json.loads(ln))
                    if len(out) >= limit:
                        return out
                except Exception:
                    continue
        except Exception:
            continue
    return out


def list_teams() -> list[tuple[str, dict[str, Any]]]:
    """读所有 team.yaml → [(mode_id, team_dict), ...]."""
    import yaml
    out: list[tuple[str, dict[str, Any]]] = []
    teams_dir = BACKEND_ROOT / "scenarios" / "teams"
    if not teams_dir.is_dir():
        return out
    for f in teams_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            out.append((f.stem, data))
        except Exception:
            continue
    return out


async def ask_cheap_llm(prompt: str) -> str:
    """便宜模型一发, 失败抛."""
    from ...llm.litellm_client import litellm_client
    resp = await litellm_client.complete(model=CHEAP_MODEL, prompt=prompt)
    return (resp.text or "").strip()


def parse_json_loose(text: str) -> dict[str, Any] | None:
    t = (text or "").strip()
    if not t:
        return None
    if t.startswith("```"):
        try:
            t = t.split("```")[1].lstrip("json").strip()
        except Exception:
            pass
    try:
        return json.loads(t)
    except Exception:
        pass
    start = t.find("{")
    end = t.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(t[start: end + 1])
        except Exception:
            return None
    return None
