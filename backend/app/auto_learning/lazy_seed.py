"""后台场景懒加载灌书 — 未手写书库的场景, 配置部门时用 DeepSeek 按 30/50/80 灌专业书库.

前台 13 场景已手写灌满 (family_doctor 等), 后台 45 场景留空.
当用户对某个后台场景"召集顾问团"(生成 team) 时, 后台异步触发本模块:
  - 对每个 persona 按角色定额 (staff 30 / head 50 / ceo 80) 生成专业书
  - 调 DeepSeek (BEE_LAZYSEED_MODEL, 默认走用户配的主模型, 保证联通能触发)
  - 分批生成 (每次 ~12 本), 去重 (对比 bee-memory 已有书名 + 本轮已生成), 写进 bee-memory
  - 状态写 lazy_seed_status 表, 前端 /api/learning/lazy-seed/status 可观测

不阻塞 HTTP: maybe_lazy_seed 用 asyncio.create_task 丢后台, 立即返回.
防重复: 同 mode 正在跑 / 已 seeded 直接跳过.
可恢复: 中途失败/触顶, 下次再触发会跳过已灌的 (靠书名去重), 续灌剩下的.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote

from . import inbox

BEE_MEMORY_URL = os.environ.get("BEE_MEMORY_URL", "http://127.0.0.1:8004")
BEE_BEARER = os.environ.get("BEE_BEARER_TOKEN", "dev-token-change-me")

# 前台已手写灌书的 13 场景 — 这些永远跳过懒加载
FRONT_STAGE_SEEDED = {
    "family_doctor", "nutrition_fitness", "legal_consulting", "stock_trading",
    "startup_advisory", "program_management", "child_education", "tax_insurance",
    "learning_planning", "travel_planning", "dining_recommendation",
    "purchase_decision", "generic_consulting",
}

# 角色定额 (与手写灌书 ROLE_TARGETS 一致)
ROLE_TARGETS = {"ceo": 80, "head": 50, "staff": 30}

_BATCH = 12                 # 单次 LLM 生成几本
_MAX_LLM_CALLS_PER_RUN = 60  # 单次 run 全场景 LLM 调用上限 (防跑飞; 触顶记 partial 可续)
_MIN_BOOKS_TO_CONSIDER_SEEDED = 10  # persona 已有这么多书就当它灌过了, 跳过


# ---------- 状态表 ----------
def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(inbox.DB_PATH))
    c.execute(
        """CREATE TABLE IF NOT EXISTS lazy_seed_status (
            mode_id TEXT PRIMARY KEY,
            status TEXT,
            started_ts INTEGER,
            done_ts INTEGER,
            personas_total INTEGER,
            personas_done INTEGER,
            books_written INTEGER,
            note TEXT
        )"""
    )
    c.row_factory = sqlite3.Row
    return c


def _set_status(mode_id: str, **fields: Any) -> None:
    try:
        with _conn() as c:
            row = c.execute("SELECT mode_id FROM lazy_seed_status WHERE mode_id=?",
                            (mode_id,)).fetchone()
            if row is None:
                c.execute(
                    "INSERT INTO lazy_seed_status "
                    "(mode_id,status,started_ts,done_ts,personas_total,personas_done,books_written,note) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (mode_id, fields.get("status", "pending"), fields.get("started_ts", 0),
                     fields.get("done_ts", 0), fields.get("personas_total", 0),
                     fields.get("personas_done", 0), fields.get("books_written", 0),
                     str(fields.get("note", ""))[:500]),
                )
            else:
                sets, vals = [], []
                for k, v in fields.items():
                    sets.append(f"{k}=?")
                    vals.append(str(v)[:500] if k == "note" else v)
                vals.append(mode_id)
                c.execute(f"UPDATE lazy_seed_status SET {', '.join(sets)} WHERE mode_id=?", vals)
    except Exception:
        pass


def get_status(mode_id: str) -> dict[str, Any]:
    try:
        with _conn() as c:
            row = c.execute("SELECT * FROM lazy_seed_status WHERE mode_id=?", (mode_id,)).fetchone()
            if row:
                return dict(row)
    except Exception:
        pass
    if mode_id in FRONT_STAGE_SEEDED:
        return {"mode_id": mode_id, "status": "front_stage_seeded", "note": "前台手写书库"}
    return {"mode_id": mode_id, "status": "not_seeded"}


# ---------- bee-memory 交互 ----------
def _existing_titles(persona_id: str) -> set[str]:
    """拉该 persona 已有 book 书名 (去重用). 失败返回空集 (宁可重复也别漏灌)."""
    try:
        req = urllib.request.Request(
            f"{BEE_MEMORY_URL}/memory/recall"
            f"?kind=knowledge_book&k=300&strategy=recent&persona_id={quote(persona_id)}",
            headers={"Authorization": f"Bearer {BEE_BEARER}"},
        )
        with urllib.request.urlopen(req, timeout=8.0) as r:
            data = json.loads(r.read())
    except Exception:
        return set()
    titles: set[str] = set()
    for it in data.get("items") or []:
        meta_str = it.get("meta") or "{}"
        try:
            meta = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
        except Exception:
            meta = {}
        if str(meta.get("persona_id")) != persona_id:
            continue
        t = str(meta.get("title") or "").strip()
        if t:
            titles.add(t)
    return titles


# ---------- LLM 生成 ----------
def _parse_json_loose(text: str) -> dict[str, Any] | None:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
        t = t.strip()
    try:
        return json.loads(t)
    except Exception:
        s, e = t.find("{"), t.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(t[s:e + 1])
            except Exception:
                return None
    return None


def _resolve_model() -> tuple[str, list[str]]:
    """默认走用户配的主模型 (保证联通), env BEE_LAZYSEED_MODEL 可改成便宜 deepseek."""
    env = os.environ.get("BEE_LAZYSEED_MODEL", "").strip()
    if env:
        fb_env = os.environ.get("BEE_LAZYSEED_FALLBACK", "").strip()
        return env, ([fb_env] if fb_env else [])
    try:
        from ..persona.team_generator import _resolve_ceo_model, _smart_fallback_for
        m = _resolve_ceo_model()
        return m, (_smart_fallback_for(m) or [])
    except Exception:
        return "deepseek/deepseek-chat", ["ollama/deepseek-r1:8b"]


def _role_brief(role: str) -> str:
    if role == "ceo":
        return ("CEO 总顾问: 除本场景核心专业书, 还要 决策科学/战略/管理/组织领导/"
                "沟通协调/思维模型/真实案例复盘 等更广更系统的书 (共 80 本视野)")
    if role == "head":
        return ("部门主管: 在本专业核心书之上, 增加更深入、更系统化、含管理/方法论/"
                "沟通协调的书 (共 50 本)")
    return "普通职员/主治: 扎实的本专业核心专业书 (共 30 本)"


async def _gen_batch(model: str, fb: list[str], *, mode_label: str, dept_label: str,
                     sub_specialty: str, role: str, n: int, exclude: list[str]) -> list[dict[str, Any]]:
    try:
        from ..llm.litellm_client import litellm_client
    except Exception:
        return []
    exclude_txt = "、".join(exclude[-60:]) if exclude else "(无)"
    prompt = f"""你是 H-SEMAS 知识策展员, 为一位专家准备其领域核心书库。

场景: {mode_label}
部门: {dept_label}
专家角色: {_role_brief(role)}
专业子方向: {sub_specialty or dept_label}

任务: 列 {n} 本该领域**真实存在的经典教科书/工具书/专著** (作者要真实), 每本写 250-450 字的
**可操作知识精华** (关键概念/方法论/判断套路/公式), 不是简介。

已经有了的书不要重复 (避开这些书名): {exclude_txt}

只输出 strict JSON:
{{
  "books": [
    {{"title": "<书名>", "author": "<真实作者>", "core_concepts": "<250-450字精华>"}}
  ]
}}
只输出 JSON。
"""
    try:
        resp = await litellm_client.complete(
            model=model, fallbacks=fb or None, prompt=prompt,
            system="Output ONLY valid JSON. Use REAL books and REAL authors.",
        )
    except Exception:
        return []
    data = _parse_json_loose(resp.text)
    if not data:
        return []
    return list(data.get("books") or [])


async def _seed_persona(model: str, fb: list[str], *, mode_id: str, mode_label: str,
                        dept_id: str, dept_label: str, persona_id: str,
                        sub_specialty: str, role: str, calls_left: list[int]) -> int:
    """给一个 persona 灌到定额. calls_left 是可变单元素列表 (全局 LLM 调用预算)."""
    target = ROLE_TARGETS.get(role, 30)
    have = await asyncio.to_thread(_existing_titles, persona_id)
    if len(have) >= max(_MIN_BOOKS_TO_CONSIDER_SEEDED, target - 5):
        return 0  # 基本灌过了
    try:
        from ..persona.knowledge_store import add_knowledge
    except Exception:
        return 0

    seen = set(have)
    written = 0
    while len(seen) < target and calls_left[0] > 0:
        calls_left[0] -= 1
        need = min(_BATCH, target - len(seen))
        books = await _gen_batch(
            model, fb, mode_label=mode_label, dept_label=dept_label,
            sub_specialty=sub_specialty, role=role, n=need, exclude=list(seen),
        )
        if not books:
            break  # 这批失败, 放弃该 persona (下次触发可续)
        new_this_batch = 0
        for b in books:
            title = str(b.get("title") or "").strip()
            content = str(b.get("core_concepts") or "").strip()
            if not title or len(content) < 30 or title in seen:
                continue
            res = await asyncio.to_thread(
                add_knowledge,
                layer="book", mode_id=mode_id, persona_id=persona_id, dept_id=dept_id,
                title=title, content=content,
                extra_meta={"author": b.get("author", ""), "lazy_seeded": True, "role": role},
            )
            if "error" not in res:
                seen.add(title)
                written += 1
                new_this_batch += 1
        if new_this_batch == 0:
            break  # 整批都是重复/无效, 停 (防死循环)
    return written


def _iter_personas(team: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    ceo = team.get("ceo") or {}
    if ceo.get("persona_id"):
        out.append({"persona_id": str(ceo["persona_id"]), "role": "ceo",
                    "dept_id": "__ceo__", "dept_label": "总顾问",
                    "sub_specialty": str(ceo.get("title") or "会诊总指挥")})
    for d in team.get("departments") or []:
        dept_id = str(d.get("dept_id") or "")
        dept_label = str(d.get("label") or dept_id)
        head = d.get("head") or {}
        if head.get("persona_id"):
            out.append({"persona_id": str(head["persona_id"]), "role": "head",
                        "dept_id": dept_id, "dept_label": dept_label,
                        "sub_specialty": str(head.get("sub_specialty") or dept_label)})
        for s in d.get("staff") or []:
            if s.get("persona_id"):
                out.append({"persona_id": str(s["persona_id"]), "role": "staff",
                            "dept_id": dept_id, "dept_label": dept_label,
                            "sub_specialty": str(s.get("sub_specialty") or dept_label)})
    return out


# 防同一 mode 并发重复跑
_RUNNING: set[str] = set()


async def run_lazy_seed(mode_id: str, team: dict[str, Any] | None = None) -> dict[str, Any]:
    """实际灌书 (async). team 为空则从 team_store 读."""
    from ..modes import get_mode
    if mode_id in _RUNNING:
        return {"mode_id": mode_id, "status": "already_running"}
    if team is None:
        try:
            from ..persona.team_store import load_team
            team = load_team(mode_id) or {}
        except Exception:
            team = {}
    personas = _iter_personas(team)
    if not personas:
        _set_status(mode_id, status="no_team", note="team 无 persona")
        return {"mode_id": mode_id, "status": "no_team"}

    try:
        mode_label = get_mode(mode_id).label
    except Exception:
        mode_label = mode_id

    _RUNNING.add(mode_id)
    model, fb = _resolve_model()
    _set_status(mode_id, status="running", started_ts=int(time.time()), done_ts=0,
                personas_total=len(personas), personas_done=0, books_written=0,
                note=f"model={model}")
    total_written = 0
    done = 0
    calls_left = [_MAX_LLM_CALLS_PER_RUN]
    try:
        for p in personas:
            n = await _seed_persona(
                model, fb, mode_id=mode_id, mode_label=mode_label,
                dept_id=p["dept_id"], dept_label=p["dept_label"],
                persona_id=p["persona_id"], sub_specialty=p["sub_specialty"],
                role=p["role"], calls_left=calls_left,
            )
            total_written += n
            done += 1
            _set_status(mode_id, personas_done=done, books_written=total_written)
            if calls_left[0] <= 0:
                _set_status(mode_id, status="partial", done_ts=int(time.time()),
                            note=f"触顶 {_MAX_LLM_CALLS_PER_RUN} 次调用, 已灌 {done}/{len(personas)} 人, 再次触发可续灌")
                return {"mode_id": mode_id, "status": "partial",
                        "personas_done": done, "books_written": total_written}
        _set_status(mode_id, status="done", done_ts=int(time.time()),
                    note=f"完成 {done} 人 {total_written} 本")
        return {"mode_id": mode_id, "status": "done", "personas_done": done,
                "books_written": total_written}
    except Exception as e:
        _set_status(mode_id, status="error", done_ts=int(time.time()), note=repr(e))
        return {"mode_id": mode_id, "status": "error", "error": repr(e)}
    finally:
        _RUNNING.discard(mode_id)


def maybe_lazy_seed(mode_id: str, team: dict[str, Any] | None = None) -> dict[str, Any]:
    """team_api.generate 灌完团队后调这个 (sync, 不阻塞). 满足条件就丢后台异步灌书.

    跳过条件: 前台已手写场景 / 正在跑 / 已 done.
    """
    if mode_id in FRONT_STAGE_SEEDED:
        return {"scheduled": False, "reason": "front_stage_seeded"}
    if mode_id in _RUNNING:
        return {"scheduled": False, "reason": "already_running"}
    st = get_status(mode_id)
    if st.get("status") == "done":
        return {"scheduled": False, "reason": "already_done"}
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(run_lazy_seed(mode_id, team))
        _set_status(mode_id, status="scheduled", started_ts=int(time.time()))
        return {"scheduled": True, "mode_id": mode_id}
    except RuntimeError:
        # 没有运行中的 loop (非 async 上下文): 起线程跑
        import threading
        threading.Thread(
            target=lambda: asyncio.run(run_lazy_seed(mode_id, team)),
            daemon=True,
        ).start()
        _set_status(mode_id, status="scheduled", started_ts=int(time.time()))
        return {"scheduled": True, "mode_id": mode_id, "via": "thread"}
