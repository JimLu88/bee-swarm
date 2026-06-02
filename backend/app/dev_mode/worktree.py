"""worktree — 在 PC 仓库上建/删 git worktree (经 bee-agent-hands 的 /exec 白名单跑 git).

每个并行 task 一个独立 worktree + 分支, 互不踩。完成后 PR 闸门批准 → 合并 → 删 worktree。
所有 git 命令走 seven_clients.agent_exec(白名单含 git), 在 PC 上真执行。
bee_clients 是同步 httpx, 这里用 asyncio.to_thread 包一层, 不阻塞事件循环。
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from ..tools.seven_clients import bee_clients


def _wt_path(repo_root: str, task_id: str) -> str:
    # 放在仓库内的 .dev_worktrees/<task_id> (git worktree 允许), 方便清理.
    return os.path.join(repo_root, ".dev_worktrees", task_id)


def _branch(task_id: str) -> str:
    return f"dev/{task_id}"


async def _git(repo_root: str, args: list[str], *, timeout: int = 60) -> dict[str, Any]:
    return await asyncio.to_thread(bee_clients.agent_exec, ["git", *args], workdir=repo_root, timeout=timeout)


async def create(repo_root: str, task_id: str) -> dict[str, Any]:
    """git worktree add .dev_worktrees/<id> -b dev/<id>. 返回 {ok, path, branch, error?}。"""
    path = _wt_path(repo_root, task_id)
    branch = _branch(task_id)
    res = await _git(repo_root, ["worktree", "add", path, "-b", branch])
    if res.get("ok"):
        return {"ok": True, "path": path, "branch": branch}
    # 分支可能已存在 → 复用(去掉 -b)
    res2 = await _git(repo_root, ["worktree", "add", path, branch])
    if res2.get("ok"):
        return {"ok": True, "path": path, "branch": branch, "reused": True}
    return {"ok": False, "path": path, "branch": branch,
            "error": (res2.get("stderr") or res2.get("error") or res.get("stderr") or "worktree add 失败")[:400]}


async def diff_summary(repo_root: str, task_id: str) -> dict[str, Any]:
    """该 worktree 相对基线的改动概要(给评审/PR 看)。"""
    path = _wt_path(repo_root, task_id)
    stat = await asyncio.to_thread(bee_clients.agent_exec, ["git", "diff", "--stat", "HEAD"], workdir=path, timeout=30)
    names = await asyncio.to_thread(bee_clients.agent_exec, ["git", "diff", "--name-only", "HEAD"], workdir=path, timeout=30)
    files = [ln.strip() for ln in (names.get("stdout") or "").splitlines() if ln.strip()]
    return {"files_changed": files, "stat": (stat.get("stdout") or "")[:4000]}


async def commit(repo_root: str, task_id: str, message: str) -> dict[str, Any]:
    """在 worktree 里 add + commit(便于后续合并)。"""
    path = _wt_path(repo_root, task_id)
    await asyncio.to_thread(bee_clients.agent_exec, ["git", "add", "-A"], workdir=path, timeout=30)
    return await asyncio.to_thread(
        bee_clients.agent_exec, ["git", "commit", "-m", message or f"dev {task_id}"], workdir=path, timeout=30)


async def remove(repo_root: str, task_id: str) -> dict[str, Any]:
    """合并/丢弃后清理 worktree。"""
    path = _wt_path(repo_root, task_id)
    return await _git(repo_root, ["worktree", "remove", "--force", path])
