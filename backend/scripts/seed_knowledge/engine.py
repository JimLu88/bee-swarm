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
ROLE_CEO = "ceo"              # 场景总决策者 (跨部门综合)
ALL_ROLES = (ROLE_HEAD, ROLE_HELPER, ROLE_ATTENDING, ROLE_REVIEWER)

# v8 书量分层 (用户定): 普通 30 / 主管 50 (专科+管理增量) / CEO 80 (理论+案例+沟通管理).
ROLE_TARGETS = {
    ROLE_HELPER: 30, ROLE_ATTENDING: 30, ROLE_REVIEWER: 30,
    ROLE_HEAD: 50, ROLE_CEO: 80,
}
# 主管 50 本里, 专科书最多取这么多, 其余从「主管增量池」(管理/系统化)补足.
HEAD_SPECIALTY_CAP = 32


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


def _dedup_by_title(books: list[Book]) -> list[Book]:
    seen: set[str] = set()
    out: list[Book] = []
    for b in books:
        if b.title not in seen:
            seen.add(b.title)
            out.append(b)
    return out


def select_books_for_role(
    lib: SpecialtyLibrary | None,
    role: str,
    target: int | None = None,
    *,
    head_plus_pool: list[Book] | None = None,
    ceo_pool: list[Book] | None = None,
    all_specialty: list[Book] | None = None,
) -> list[Book]:
    """按角色选书 (v9 配比: 80% 专业 + 20% 管理/决策):
      staff → target(默认30) 本本专科书 (按 roles 偏好+重要度).
      head → 50 本 = 40 专业(本科为主, 不足用跨科补) + 10 管理/系统化(head_plus_pool).
      ceo  → 80 本 = 64 跨部门专业(all_specialty) + 16 决策/管理(ceo_pool).
    用户定: 主管/CEO 也必须 80% 是本场景专业知识, 只有 20% 是管理决策, 否则不懂行.
    """
    tgt = target if target is not None else ROLE_TARGETS.get(role, 30)
    spec_n = int(round(tgt * 0.8))   # 80% 专业
    pool_n = tgt - spec_n            # 20% 管理/决策

    if role == ROLE_CEO:
        # CEO 主体是跨部门专业书(广), 只夹 20% 决策管理池
        spec = _dedup_by_title(sorted(all_specialty or [], key=lambda b: -b.importance))
        picked = spec[:spec_n]
        chosen = {b.title for b in picked}
        pool = [b for b in sorted(ceo_pool or [], key=lambda b: -b.importance) if b.title not in chosen]
        return (picked + pool[:pool_n])[:tgt]

    if role == ROLE_HEAD:
        own = sorted((lib.books if lib else []), key=lambda b: -b.importance)
        picked = own[:spec_n]
        chosen = {b.title for b in picked}
        # 本科专业书不足 80% → 用跨部门专业补 (仍算专业, 不用管理凑数)
        if len(picked) < spec_n and all_specialty:
            for b in sorted(all_specialty, key=lambda b: -b.importance):
                if b.title not in chosen:
                    picked.append(b); chosen.add(b.title)
                    if len(picked) >= spec_n:
                        break
        plus = [b for b in sorted(head_plus_pool or [], key=lambda b: -b.importance) if b.title not in chosen]
        return (picked + plus[:pool_n])[:tgt]

    # staff: 偏好匹配本角色 roles 的书, 再用其余补足 (全专业)
    books = lib.books if lib else []
    primary = sorted([b for b in books if role in b.roles], key=lambda b: -b.importance)
    rest = sorted([b for b in books if role not in b.roles], key=lambda b: -b.importance)
    return (primary + rest)[:tgt]


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
        # 用服务端 persona_id 过滤 (不是 content LIKE query — 那个匹配书正文恒空, 是已知 bug).
        resp = _get(f"/memory/recall?kind=knowledge_book&k=500&strategy=static&persona_id={quote(persona_id)}")
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
    ceo = data.get("ceo") or {}
    if ceo.get("persona_id"):
        out.append({"persona_id": str(ceo["persona_id"]), "dept_id": "ceo",
                    "role": ROLE_CEO, "title": str(ceo.get("title") or "")})
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
    target_per_persona: int | None = None,
    head_plus_pool: list[Book] | None = None,
    ceo_pool: list[Book] | None = None,
    skip_existing: bool = True,
    verbose: bool = True,
) -> dict[str, Any]:
    """给一个场景的所有 persona 灌书 (v8 分层 30/50/80).

    libraries: {dept_id: SpecialtyLibrary} 各专科书库.
    head_plus_pool: 主管增量池 (管理/系统化), head 在专科书之上补到 50.
    ceo_pool: CEO 池 (理论/案例/沟通管理), CEO 取 80.
    target_per_persona=None → 按 ROLE_TARGETS 自动 (30/50/80); 给数字则覆盖.
    """
    personas = list_personas(mode_id)
    # v9: 跨部门专业书并集 (CEO 取 64 本广度, head 本科不足时补) — 保证主管/CEO 80% 专业
    all_specialty = _dedup_by_title([b for lb in libraries.values() for b in lb.books])
    stats = {"mode_id": mode_id, "personas": len(personas), "stored": 0,
             "skipped": 0, "no_lib": 0, "failed": 0}
    for p in personas:
        role = p["role"]
        lib = libraries.get(p["dept_id"])
        # CEO 不依赖专科库, 用 ceo_pool; staff/head 需要专科库
        if role != ROLE_CEO and not lib:
            stats["no_lib"] += 1
            if verbose:
                print(f"  [no_lib] {p['persona_id']} (dept={p['dept_id']})")
            continue
        if role == ROLE_CEO and not ceo_pool:
            stats["no_lib"] += 1
            if verbose:
                print(f"  [no_ceo_pool] {p['persona_id']}")
            continue
        books = select_books_for_role(
            lib, role, target_per_persona,
            head_plus_pool=head_plus_pool, ceo_pool=ceo_pool,
            all_specialty=all_specialty,
        )
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
