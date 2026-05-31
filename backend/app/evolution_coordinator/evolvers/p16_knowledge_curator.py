"""v6-C 知识策展员 — 每周给每个 persona 充实知识库.

每周一 03:00 (建议) 跑:
  1. 扫所有 team.yaml, 找已生成的 persona
  2. 对每个 head, 让 Opus 列书单 (5 本经典)
  3. 调 Opus 浓缩 books / pitfalls / standards → 入 bee-memory
  4. (未来) 失败决策从 evolution_log 提 → 入 pitfalls
  5. (未来) 成功决策从 decisions 提 → 入 cases

存表:
  knowledge_curator_log:
    id PK, ts INT, mode_id, persona_id, layer, action, count, note
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "evolution_history.sqlite"
TEAMS_DIR = Path(__file__).resolve().parents[3] / "scenarios" / "teams"

# 单次 run 限流, 防止一次烧太多 token
MAX_PERSONAS_PER_RUN = 4
MAX_BOOKS_PER_PERSONA = 5
MAX_PITFALLS_PER_PERSONA = 5
MAX_STANDARDS_PER_PERSONA = 5


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_curator_log (
            id TEXT PRIMARY KEY, ts INTEGER, mode_id TEXT, persona_id TEXT,
            layer TEXT, action TEXT, count INTEGER, note TEXT
        )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kc_mode ON knowledge_curator_log(mode_id, ts)")
    c.row_factory = sqlite3.Row
    return c


def _log(mode_id: str, persona_id: str, layer: str, action: str, count: int, note: str = "") -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO knowledge_curator_log VALUES (?,?,?,?,?,?,?,?)",
            (f"kc-{uuid.uuid4().hex[:10]}", int(time.time()), mode_id, persona_id,
             layer, action, count, note[:500]),
        )


def _list_all_personas() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not TEAMS_DIR.exists():
        return out
    for f in sorted(TEAMS_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        mode_id = str(data.get("mode_id") or f.stem)
        for d in data.get("departments") or []:
            head = d.get("head") or {}
            if head.get("persona_id"):
                out.append({
                    "mode_id": mode_id, "dept_id": str(d.get("dept_id")),
                    "persona_id": head["persona_id"], "name": head.get("name", ""),
                    "sub_specialty": head.get("sub_specialty", ""), "role": "head",
                })
    return out


def _parse_json_loose(text: str) -> dict[str, Any] | None:
    """LLM 偶尔加 ```json 围栏, 试着剥掉."""
    t = text.strip()
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
                return json.loads(t[s: e + 1])
            except Exception:
                return None
    return None


async def _ask_opus(prompt: str, system: str = "Output ONLY valid JSON.") -> dict[str, Any] | None:
    """v6 修脱节 #3: 默认 DeepSeek 省钱 (单次 ¥0.5-1, 而非 Opus ¥3-5).
    BEE_CURATOR_MODEL env 可改回 Opus."""
    import os
    model = os.environ.get("BEE_CURATOR_MODEL", "deepseek/deepseek-chat")
    fb = os.environ.get("BEE_CURATOR_FALLBACK", "anthropic/claude-sonnet-4-6,ollama/deepseek-r1:8b").split(",")
    try:
        from ...llm.litellm_client import litellm_client
    except Exception:
        return None
    try:
        resp = await litellm_client.complete(
            model=model,
            fallbacks=fb,
            prompt=prompt,
            system=system,
        )
    except Exception:
        return None
    return _parse_json_loose(resp.text)


async def _curate_books(p: dict[str, Any]) -> int:
    data = await _ask_opus(f"""你是 H-SEMAS 知识策展员, 为这位专家准备其领域的核心知识库。

专家信息:
- 场景: {p['mode_id']}
- 部门: {p['dept_id']}
- 名字: {p['name']}
- 专业方向: {p['sub_specialty']}

任务: 列 {MAX_BOOKS_PER_PERSONA} 本该领域的核心教科书/工具书, 对每本写 **300-500 字** 的核心要点浓缩。
浓缩应包含:
- 关键概念 / 方法论 / 公式
- 该领域专家会反复用到的判断套路
- 不是简介, 是**可操作的知识精华**

输出 strict JSON:
{{
  "books": [
    {{"title": "<书名>", "author": "<作者>", "core_concepts": "<300-500 字浓缩>"}}
  ]
}}
只输出 JSON。
""")
    if not data:
        return 0
    try:
        from ...persona.knowledge_store import add_knowledge
    except Exception:
        return 0
    n = 0
    for book in (data.get("books") or [])[:MAX_BOOKS_PER_PERSONA]:
        title = str(book.get("title") or "").strip()
        content = str(book.get("core_concepts") or "").strip()
        if not title or not content:
            continue
        result = add_knowledge(
            layer="book", mode_id=p["mode_id"], persona_id=p["persona_id"],
            dept_id=p["dept_id"], title=title, content=content,
            extra_meta={"author": book.get("author", "")},
        )
        if "error" not in result:
            n += 1
    return n


async def _curate_pitfalls(p: dict[str, Any]) -> int:
    data = await _ask_opus(f"""你是 H-SEMAS 知识策展员。

专家: {p['name']} ({p['sub_specialty']}), 场景 {p['mode_id']}, 部门 {p['dept_id']}

任务: 列 {MAX_PITFALLS_PER_PERSONA} 个**该领域专家最容易犯的错 / 思维陷阱 / 易混淆套路**。
这些不是"知识", 而是"反知识" — 让专家保持谦虚、避免过度自信。

格式: 每个含
- 错误类型 (一句话标题)
- 为什么容易错
- 正确套路 / 排雷方法

输出 strict JSON:
{{
  "pitfalls": [
    {{"title": "<>", "explanation": "<200-400 字>"}}
  ]
}}
只输出 JSON。
""")
    if not data:
        return 0
    try:
        from ...persona.knowledge_store import add_knowledge
    except Exception:
        return 0
    n = 0
    for it in (data.get("pitfalls") or [])[:MAX_PITFALLS_PER_PERSONA]:
        title = str(it.get("title") or "").strip()
        content = str(it.get("explanation") or "").strip()
        if not title or not content:
            continue
        result = add_knowledge(
            layer="pitfall", mode_id=p["mode_id"], persona_id=p["persona_id"],
            dept_id=p["dept_id"], title=title, content=content,
        )
        if "error" not in result:
            n += 1
    return n


async def _curate_standards(p: dict[str, Any]) -> int:
    """只对法律/医疗/财务/工程类领域有意义, 其它跳过."""
    relevant_modes = (
        "legal_consulting", "family_doctor", "tax_insurance",
        "program_management", "nutrition_fitness", "stock_trading",
    )
    if p["mode_id"] not in relevant_modes:
        return 0

    data = await _ask_opus(f"""你是 H-SEMAS 知识策展员。

专家: {p['name']} ({p['sub_specialty']}), {p['mode_id']} / {p['dept_id']}

任务: 列该专业领域 **真实存在的 3-5 个法规/标准/临床指南/行业规范** (条文级, 不是泛泛而谈)。

输出 strict JSON:
{{
  "standards": [
    {{"title": "<法规标准全名>", "key_clauses": "<最重要的几条关键条款节选 200-400 字>"}}
  ]
}}
只输出 JSON。
""")
    if not data:
        return 0
    try:
        from ...persona.knowledge_store import add_knowledge
    except Exception:
        return 0
    n = 0
    for it in (data.get("standards") or [])[:MAX_STANDARDS_PER_PERSONA]:
        title = str(it.get("title") or "").strip()
        content = str(it.get("key_clauses") or "").strip()
        if not title or not content:
            continue
        result = add_knowledge(
            layer="standard", mode_id=p["mode_id"], persona_id=p["persona_id"],
            dept_id=p["dept_id"], title=title, content=content,
        )
        if "error" not in result:
            n += 1
    return n


def run() -> dict[str, Any]:
    """主入口: 每周一 03:00 跑, 给最多 MAX_PERSONAS_PER_RUN 个 persona 充实知识库.

    成本控制: 每个 persona ~3 个 LLM 调用 (books + pitfalls + standards), 约 ¥3-5/persona.
    一次 run 4 个 persona = ¥12-20.
    """
    now = int(time.time())
    all_personas = _list_all_personas()
    if not all_personas:
        return {"evolver": "p16_knowledge_curator", "status": "no_teams_found", "ts": now}

    with _conn() as c:
        recent = {
            r["persona_id"]: int(r["ts"])
            for r in c.execute(
                "SELECT persona_id, MAX(ts) ts FROM knowledge_curator_log GROUP BY persona_id"
            ).fetchall()
        }
    all_personas.sort(key=lambda p: recent.get(p["persona_id"], 0))
    targets = all_personas[:MAX_PERSONAS_PER_RUN]

    results: list[dict[str, Any]] = []
    for p in targets:
        n_books = asyncio.run(_curate_books(p))
        _log(p["mode_id"], p["persona_id"], "book", "added", n_books)
        n_pitfalls = asyncio.run(_curate_pitfalls(p))
        _log(p["mode_id"], p["persona_id"], "pitfall", "added", n_pitfalls)
        n_standards = asyncio.run(_curate_standards(p))
        _log(p["mode_id"], p["persona_id"], "standard", "added", n_standards)
        results.append({
            "persona_id": p["persona_id"], "mode_id": p["mode_id"],
            "books": n_books, "pitfalls": n_pitfalls, "standards": n_standards,
        })

    return {
        "evolver": "p16_knowledge_curator",
        "status": "ok",
        "ts": now,
        "targets_processed": len(results),
        "results": results,
    }
