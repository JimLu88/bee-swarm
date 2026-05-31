"""灌库引擎 — 把手写书库按 persona 定制后灌进 bee-memory.

核心概念:
- Book: 一本书 (真实书名 + 作者 + 核心要点浓缩 + 角色权重标签).
- SpecialtyLibrary: 一个专科 (dept_id) 的完整书库 (通常 30-45 本).
- 选书: 每个 persona 按 role 从其专科书库里挑 ~30 本:
    head      → 全谱 (基础+核心+进阶+鉴别), 偏深
    helper    → 偏工具书/手册/检索类 (assistant)
    attending → 偏诊疗常规/操作/实战 (executor)
    reviewer  → 偏鉴别诊断/陷阱/安全/循证 (critic)
- 灌库: 调 bee-memory /store, kind=knowledge_book, meta 带 persona_id 隔离.
- 幂等: 灌前先按 (persona_id, title) 查重, 已存在则跳过.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

BEE_MEMORY_URL = os.environ.get("BEE_MEMORY_URL", "http://127.0.0.1:8004")
BEE_BEARER = os.environ.get("BEE_BEARER_TOKEN", "dev-token-change-me")
TEAMS_DIR = Path(__file__).resolve().parents[2] / "scenarios" / "teams"

ROLE_HEAD = "head"
ROLE_HELPER = "helper"        # 资深助理 (检索/工具)
ROLE_ATTENDING = "attending"  # 主治/骨干 (执行/常规)
ROLE_REVIEWER = "reviewer"    # 审核员 (鉴别/陷阱/安全)
ALL_ROLES = (ROLE_HEAD, ROLE_HELPER, ROLE_ATTENDING, ROLE_REVIEWER)


@dataclass
class Book:
    """一本真实专业书 + 核心要点浓缩 (手写, 非 LLM)."""
    title: str
    author: str
    core: str                            # 200-500 字核心要点浓缩
    layer: str = "book"                  # book / standard / pitfall
    roles: tuple[str, ...] = ALL_ROLES   # 适合哪些角色 (默认全角色)
    importance: int = 5


@dataclass
class SpecialtyLibrary:
    """一个专科 (dept_id) 的书库."""
    dept_id: str
    label: str
    books: list[Book] = field(default_factory=list)


def _role_of_staff(persona_id: str, title: str) -> str:
    pid = (persona_id or "").lower()
    t = title or ""
    if pid.endswith("_helper") or "助理" in t or "检索" in t:
        return ROLE_HELPER
    if pid.endswith("_attending") or "主治" in t or "骨干" in t:
        return ROLE_ATTENDING
    if pid.endswith("_reviewer") or "审核" in t:
        return ROLE_REVIEWER
    return ROLE_ATTENDING


def select_books_for_role(lib: SpecialtyLibrary, role: str, target: int = 30) -> list[Book]:
    """从专科书库为某角色选 target 本."""
    if role == ROLE_HEAD:
        return sorted(lib.books, key=lambda b: -b.importance)[:target]
    primary = sorted([b for b in lib.books if role in b.roles], key=lambda b: -b.importance)
    rest = sorted([b for b in lib.books if role not in b.roles], key=lambda b: -b.importance)
    return (primary + rest)[:target]


# ----------------------------------------------------------------- bee-memory IO
def _post(path: str, payload: dict[str, Any], timeout: float = 8.0) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{BEE_MEMORY_URL}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {BEE_BEARER}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _get(path: str, timeout: float = 8.0) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{BEE_MEMORY_URL}{path}",
        headers={"Authorization": f"Bearer {BEE_BEARER}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _existing_titles_for_persona(persona_id: str) -> set[str]:
    """召回该 persona 已灌的 book 标题, 幂等去重用."""
    titles: set[str] = set()
    try:
        from urllib.parse import quote
        resp = _get(f"/memory/recall?kind=knowledge_book&k=300&strategy=static&query={quote(persona_id)}")
        for it in resp.get("items") or []:
            meta = it.get("meta") or "{}"
            try:
                m = json.loads(meta) if isinstance(meta, str) else meta
            except Exception:
                m = {}
            if str(m.get("persona_id")) == persona_id and m.get("title"):
                titles.add(str(m["title"]))
    except Exception:
        pass
    return titles


def store_book(*, mode_id: str, persona_id: str, dept_id: str, book: Book) -> bool:
    meta = {
        "layer": book.layer, "mode_id": mode_id, "persona_id": persona_id,
        "dept_id": dept_id, "title": book.title, "author": book.author,
    }
    payload = {
        "kind": f"knowledge_{book.layer}",
        "content": f"《{book.title}》({book.author})\n{book.core}"[:8000],
        "mode_id": mode_id,
        "importance": int(book.importance),
        "meta": meta,
    }
    try:
        r = _post("/memory/store", payload)
        return bool(r.get("memory_id"))
    except Exception:
        return False


# ----------------------------------------------------------------- team.yaml 解析
def list_personas(mode_id: str) -> list[dict[str, str]]:
    f = TEAMS_DIR / f"{mode_id}.yaml"
    if not f.is_file():
        return []
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    out: list[dict[str, str]] = []
    for dep in data.get("departments") or []:
        dept_id = str(dep.get("dept_id") or "")
        head = dep.get("head") or {}
        if head.get("persona_id"):
            out.append({"persona_id": str(head["persona_id"]), "dept_id": dept_id,
                        "role": ROLE_HEAD, "title": str(head.get("title") or "")})
        for st in dep.get("staff") or []:
            if st.get("persona_id"):
                out.append({
                    "persona_id": str(st["persona_id"]), "dept_id": dept_id,
                    "role": _role_of_staff(str(st.get("persona_id")), str(st.get("title") or "")),
                    "title": str(st.get("title") or ""),
                })
    return out


def seed_scenario(
    *,
    mode_id: str,
    libraries: dict[str, SpecialtyLibrary],
    target_per_persona: int = 30,
    skip_existing: bool = True,
    verbose: bool = True,
) -> dict[str, Any]:
    """给一个场景的所有 persona 灌书. libraries: {dept_id: SpecialtyLibrary}."""
    personas = list_personas(mode_id)
    stats = {"mode_id": mode_id, "personas": len(personas), "stored": 0,
             "skipped": 0, "no_lib": 0, "failed": 0}
    for p in personas:
        lib = libraries.get(p["dept_id"])
        if not lib:
            stats["no_lib"] += 1
            if verbose:
                print(f"  [no_lib] {p['persona_id']} (dept={p['dept_id']})")
            continue
        books = select_books_for_role(lib, p["role"], target_per_persona)
        existing = _existing_titles_for_persona(p["persona_id"]) if skip_existing else set()
        n_ok = n_skip = n_fail = 0
        for b in books:
            if b.title in existing:
                n_skip += 1
                continue
            if store_book(mode_id=mode_id, persona_id=p["persona_id"], dept_id=p["dept_id"], book=b):
                n_ok += 1
            else:
                n_fail += 1
            time.sleep(0.01)
        stats["stored"] += n_ok
        stats["skipped"] += n_skip
        stats["failed"] += n_fail
        if verbose:
            print(f"  {p['persona_id']:44s} role={p['role']:9s} 灌{n_ok} 跳{n_skip} 败{n_fail}")
    return stats
