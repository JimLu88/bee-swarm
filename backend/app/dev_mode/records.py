"""records — 开发模式每次跑批的记录 + 奖励计算 + 成功次数统计.

存 backend/data/software_dev/dev_runs.jsonl (每行一次 task 跑批). 字段见 append_run.
奖励 reward = 0.5*测试通过 + 0.3*评审分 + 0.2*人工QA通过率, 喂给 dev_bandit 与 p17 进化器.
successful_count() 给"满 8 次才开自动进化"的闸门用.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

# 满 N 次成功跑批才允许自动进化提议 (用户定: 8)
EVOLVE_THRESHOLD = 8
# 视为"成功"的奖励下限
SUCCESS_REWARD = 0.6


def _path() -> Path:
    p = Path(__file__).resolve().parent.parent / "data" / "software_dev"
    p.mkdir(parents=True, exist_ok=True)
    return p / "dev_runs.jsonl"


def compute_reward(*, tests_passed: bool, review_score: float = 0.0,
                   human_qa: dict[str, Any] | None = None) -> float:
    """0.5*测试 + 0.3*评审 + 0.2*人工QA通过率. 缺失项按 0 计, 结果裁剪到 [0,1]."""
    qa_rate = 0.0
    if isinstance(human_qa, dict):
        passed = float(human_qa.get("passed", 0) or 0)
        failed = float(human_qa.get("failed", 0) or 0)
        total = passed + failed
        qa_rate = (passed / total) if total > 0 else 0.0
    r = 0.5 * (1.0 if tests_passed else 0.0) + 0.3 * float(review_score or 0.0) + 0.2 * qa_rate
    return max(0.0, min(1.0, round(r, 4)))


def append_run(*, dev_id: str, task_id: str, title: str = "", kind: str = "feature",
               sop_variant: str = "", tests_passed: bool = False, test_summary: str = "",
               review_score: float = 0.0, human_qa: dict[str, Any] | None = None,
               files_changed: list[str] | None = None) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "dev_id": dev_id, "task_id": task_id, "title": title, "kind": kind,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sop_variant": sop_variant,
        "tests_passed": bool(tests_passed), "test_summary": str(test_summary)[:2000],
        "review_score": float(review_score or 0.0),
        "human_qa": human_qa or {},
        "files_changed": files_changed or [],
        "user_feedback": "",
    }
    rec["reward"] = compute_reward(tests_passed=tests_passed, review_score=review_score, human_qa=human_qa)
    p = _path()
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def read_runs(limit: int = 200) -> list[dict[str, Any]]:
    p = _path()
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows[-max(1, min(limit, 1000)):]


def successful_count() -> int:
    """reward >= SUCCESS_REWARD 的跑批数 (进化闸门用)."""
    return sum(1 for r in read_runs(1000) if float(r.get("reward", 0) or 0) >= SUCCESS_REWARD)


def can_auto_evolve() -> bool:
    return successful_count() >= EVOLVE_THRESHOLD
