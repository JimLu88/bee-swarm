"""constraints — 开发模式的"约束库"(CLAUDE.md 稳定 + learnings.md 自长 + rules 晋升).

存在 NAS 侧(每个 repo 一份), 每次让 claude 写码时注入成 constraint_text;
避免去 PC 上读写文件的复杂度, 同时实现"约束随项目自进化"。
- CLAUDE.md : 稳定核心(很少改, 用户/p19 精炼)
- learnings.md : 每次踩坑追加(append-only, 原始)
- rules.md : 从 learnings 批量(≤5)晋升的精炼规则(经 pending_changes 审批后写入)

存 backend/data/software_dev/constraints/<repo_key>/{CLAUDE.md,learnings.md,rules.md}
repo_key = repo_root 的短 hash(避免路径里的非法字符)。
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

MAX_PROMOTE = 5            # 单次最多晋升几条 learnings → rules (层级保持浅)
_INJECT_LEARNINGS_TAIL = 12  # 注入提示时带最近几条 learnings


def _base() -> Path:
    p = Path(__file__).resolve().parent.parent / "data" / "software_dev" / "constraints"
    p.mkdir(parents=True, exist_ok=True)
    return p


def repo_key(repo_root: str) -> str:
    h = hashlib.sha1((repo_root or "").encode("utf-8")).hexdigest()[:10]
    safe = "".join(c for c in (repo_root or "") if c.isalnum())[-16:] or "repo"
    return f"{safe}_{h}"


def _dir(repo_root: str) -> Path:
    d = _base() / repo_key(repo_root)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8") if p.is_file() else ""
    except Exception:
        return ""


def append_learning(repo_root: str, text: str) -> None:
    """踩坑/失败教训追加到 learnings.md (带时间戳)。"""
    text = (text or "").strip()
    if not text:
        return
    p = _dir(repo_root) / "learnings.md"
    line = f"- [{time.strftime('%Y-%m-%d %H:%M')}] {text}\n"
    try:
        with p.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def build_constraint_text(repo_root: str) -> str:
    """拼成注入给 claude 的约束: CLAUDE.md(稳定) + rules.md(已晋升) + 最近 learnings。"""
    d = _dir(repo_root)
    parts: list[str] = []
    claude_md = _read(d / "CLAUDE.md").strip()
    if claude_md:
        parts.append(f"# 项目约束 (CLAUDE.md)\n{claude_md}")
    rules = _read(d / "rules.md").strip()
    if rules:
        parts.append(f"# 已沉淀规则 (rules)\n{rules}")
    learn = [ln for ln in _read(d / "learnings.md").splitlines() if ln.strip()]
    if learn:
        parts.append("# 最近踩过的坑 (learnings, 避免重犯)\n" + "\n".join(learn[-_INJECT_LEARNINGS_TAIL:]))
    return "\n\n".join(parts)


def unpromoted_learnings(repo_root: str, limit: int = MAX_PROMOTE) -> list[str]:
    """取还没进 rules.md 的 learnings(简单去重: 内容不在 rules 文本里), 最多 limit 条。"""
    d = _dir(repo_root)
    rules = _read(d / "rules.md")
    out: list[str] = []
    for ln in _read(d / "learnings.md").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        body = ln.split("] ", 1)[-1].strip()  # 去时间戳前缀
        if body and body not in rules:
            out.append(body)
    # 去重保序
    seen, uniq = set(), []
    for b in out:
        if b not in seen:
            seen.add(b); uniq.append(b)
    return uniq[-max(1, limit):] if uniq else []


def apply_rule_promotion(repo_root: str, rules: list[str]) -> int:
    """把若干 learnings 晋升写入 rules.md(pending_changes 审批通过后调用)。返回写入条数。"""
    rules = [str(r).strip() for r in (rules or []) if str(r).strip()][:MAX_PROMOTE]
    if not rules:
        return 0
    p = _dir(repo_root) / "rules.md"
    existing = _read(p)
    added = 0
    try:
        with p.open("a", encoding="utf-8") as f:
            for r in rules:
                if r not in existing:
                    f.write(f"- {r}\n")
                    added += 1
    except Exception:
        return 0
    return added


def apply_rule_promotion_by_key(repo_key_str: str, rules: list[str]) -> int:
    """按 repo_key 晋升(p19 提案 / pending_changes 审批通过后调用)。"""
    rules = [str(r).strip() for r in (rules or []) if str(r).strip()][:MAX_PROMOTE]
    if not rules:
        return 0
    d = _base() / repo_key_str
    d.mkdir(parents=True, exist_ok=True)
    p = d / "rules.md"
    existing = _read(p)
    added = 0
    try:
        with p.open("a", encoding="utf-8") as f:
            for r in rules:
                if r not in existing:
                    f.write(f"- {r}\n")
                    added += 1
    except Exception:
        return 0
    return added


def list_repos() -> list[str]:
    """已有约束库的 repo_key 列表(给 p19 遍历)。"""
    try:
        return [d.name for d in _base().iterdir() if d.is_dir()]
    except Exception:
        return []


def learnings_for_key(repo_key_str: str, limit: int = MAX_PROMOTE) -> tuple[str, list[str]]:
    """给 p19 用: 按 repo_key 读未晋升 learnings。返回 (repo_key, 未晋升列表)。"""
    d = _base() / repo_key_str
    rules = _read(d / "rules.md")
    out: list[str] = []
    for ln in _read(d / "learnings.md").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        body = ln.split("] ", 1)[-1].strip()
        if body and body not in rules and body not in out:
            out.append(body)
    return repo_key_str, out[-max(1, limit):] if out else []
