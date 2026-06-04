# -*- coding: utf-8 -*-
"""书库 RAG 管线:扫投书文件夹 → 解析(整本)→ 切块 → 嵌入 → 入库 → 回写 .ingested.json;并提供检索。

CLI:
    python -m app.books_rag.pipeline ingest            # 灌投书文件夹里所有书(幂等)
    python -m app.books_rag.pipeline ingest --force    # 强制重灌
    python -m app.books_rag.pipeline search "胸痛 鉴别诊断" --scenario family_doctor
    python -m app.books_rag.pipeline stats

嵌入器:见 embed.get_embedder()(本地 bge / API / 无→FTS5)。整本不截断。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

from ..seed_knowledge import booklib_check as blc
from .embed import get_embedder
from .store import BookStore

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t　]+")
_MIN_BOOK_CHARS = 200


def _db_path() -> Path:
    try:
        from ..runtime_paths import backend_data_dir
        base = backend_data_dir()
    except Exception:
        base = Path(__file__).resolve().parents[2] / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base / "books.sqlite"


# ---------- 解析(整本,不截断) ----------
def extract_text(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    try:
        if ext in ("txt", "md", "log"):
            return path.read_text(encoding="utf-8", errors="replace")
        if ext == "pdf":
            from pypdf import PdfReader
            rdr = PdfReader(str(path))
            return "\n".join((p.extract_text() or "") for p in rdr.pages)
        if ext == "docx":
            from docx import Document
            doc = Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        if ext == "epub":
            return _extract_epub(path)
    except Exception:  # noqa: BLE001  坏文件不挂整批
        return ""
    return ""


def _extract_epub(path: Path) -> str:
    import zipfile
    out: List[str] = []
    with zipfile.ZipFile(str(path)) as z:
        names = [n for n in z.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))]
        for n in names:
            try:
                html = z.read(n).decode("utf-8", errors="replace")
            except Exception:
                continue
            out.append(_TAG.sub(" ", html))
    return "\n".join(out)


# ---------- 切块 ----------
def chunk_text(text: str, size: int = 600, overlap: int = 80) -> List[str]:
    text = _WS.sub(" ", (text or "").replace("\r", "\n"))
    paras = [p.strip() for p in re.split(r"\n{2,}|\n", text) if p.strip()]
    chunks: List[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 1 <= size:
            buf = f"{buf}\n{p}" if buf else p
        else:
            if buf:
                chunks.append(buf)
            if len(p) <= size:
                buf = p
            else:  # 超长段落硬切
                for i in range(0, len(p), size - overlap):
                    chunks.append(p[i:i + size])
                buf = ""
    if buf:
        chunks.append(buf)
    # 加重叠:相邻块头接上一块的尾
    if overlap > 0 and len(chunks) > 1:
        merged = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-overlap:]
            merged.append(prev_tail + chunks[i])
        chunks = merged
    return [c for c in chunks if c.strip()]


# ---------- 书目匹配(复用 booklib_check) ----------
def _match_required(norm_stem: str, required: dict) -> Optional[str]:
    """文件名标准化串 → 命中的书单 key(canonical title)。"""
    for key in required:
        if key and (key in norm_stem or norm_stem in key):
            return key
    return None


# ---------- 灌库 ----------
def ingest(dropzone: Optional[str] = None, force: bool = False) -> dict:
    dz = Path(dropzone) if dropzone else blc.DEFAULT_DROPZONE
    dz.mkdir(parents=True, exist_ok=True)
    emb = get_embedder()
    dim = emb.dim if emb else None
    store = BookStore(_db_path(), dim)
    store.set_meta("embed", emb.name if emb else "none(fts5-only)")
    if dim:
        store.set_meta("dim", str(dim))

    required = blc.load_required()
    files = blc.scan_dropzone(dz)
    ingested_titles: set[str] = set()
    n_new = n_skip = n_fail = 0
    for path, norm_stem in files:
        size = path.stat().st_size
        key = _match_required(norm_stem, required) or norm_stem
        title = required[key]["title"] if key in required else path.stem
        author = required[key].get("author", "") if key in required else ""
        scenario = ", ".join(sorted(required[key]["scenarios"])) if key in required else ""
        if not force and store.has_book(key, size):
            n_skip += 1
            if key in required:
                ingested_titles.add(required[key]["title"])
            continue
        text = extract_text(path)
        if len(text) < _MIN_BOOK_CHARS:
            n_fail += 1  # 扫描型PDF/空文件:解析不出文字
            continue
        chunks = chunk_text(text)
        vecs = emb.encode(chunks) if emb else None
        store.add_book(key, title, author, scenario, "", path.name, size, chunks, vecs)
        n_new += 1
        if key in required:
            ingested_titles.add(required[key]["title"])

    _write_ingested(store, ingested_titles)
    st = store.stats()
    store.close()
    return {"new": n_new, "skipped": n_skip, "parse_failed": n_fail, **st,
            "embedder": emb.name if emb else "none(FTS5-only)"}


def _write_ingested(store: BookStore, titles: set[str]) -> None:
    """回写 .ingested.json(并入已有),让 booklib_check 显示"已被程序使用"。"""
    p = blc.INGESTED_STATE
    existing: set[str] = set()
    if p.is_file():
        try:
            old = json.loads(p.read_text(encoding="utf-8"))
            existing = set(old.get("ingested", []) if isinstance(old, dict) else old)
        except Exception:
            existing = set()
    all_titles = sorted(existing | titles)
    books = [dict(r) for r in store.db.execute(
        "SELECT title, file, scenario, n_chunks FROM books ORDER BY title")]
    p.write_text(json.dumps(
        {"ingested": all_titles, "updated_by": "books_rag", "books": books},
        ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- 检索 ----------
def retrieve(query: str, scenario: Optional[str] = None, k: int = 5) -> List[dict]:
    emb = get_embedder()
    # 用建库时的 dim 打开(读 meta),保证 vec 扩展正确加载
    probe = BookStore(_db_path(), None)
    stored_dim = probe.db.execute("SELECT v FROM meta WHERE k='dim'").fetchone()
    probe.close()
    dim = int(stored_dim["v"]) if stored_dim else None
    store = BookStore(_db_path(), dim)
    q_emb = None
    if emb and dim and emb.dim == dim:
        q_emb = emb.encode([query])[0]
    res = store.hybrid_search(query, q_emb, k=k, scenario=scenario)
    store.close()
    return res


def ingest_cards(force: bool = False) -> dict:
    """#3-lite 书目卡片层:把书单 2610 本做成"卡片"灌进向量库(零成本/无盗版)。
    每张卡 = 《书名》作者+场景定位,让系统在没真书前就"知道每个场景有哪些权威书"。
    真书灌入后两者并存、互不覆盖(卡片 book_key 带 card:: 前缀)。"""
    emb = get_embedder()
    dim = emb.dim if emb else None
    store = BookStore(_db_path(), dim)
    store.set_meta("embed", emb.name if emb else "none(fts5-only)")
    if dim:
        store.set_meta("dim", str(dim))
    required = blc.load_required()
    contents: List[str] = []
    metas: List[tuple] = []
    for ent in required.values():
        title = ent["title"]
        author = ent.get("author", "")
        sc = ", ".join(sorted(ent.get("scenarios", [])))
        db = ent.get("douban", "")
        key = "card::" + blc._norm(title)
        if not force and store.has_book(key, 1):
            continue
        c = f"《{title}》 作者:{author}。{sc} 场景的权威推荐专业书。" + (f"豆瓣评分 {db}。" if db and db != "—" else "")
        contents.append(c)
        metas.append((key, title, author, sc))
    if not contents:
        st = store.stats(); store.close()
        return {"new_cards": 0, **st}
    vecs = emb.encode(contents) if emb else None
    for i, (key, title, author, sc) in enumerate(metas):
        store.add_book(key, title, author, sc, "card", "booklist-card", 1,
                       [contents[i]], [vecs[i]] if vecs else None, commit=False)
    store.commit()  # 批量末尾一次提交(2610卡片只 commit 1 次,群晖上快得多)
    st = store.stats(); store.close()
    return {"new_cards": len(metas), **st}


def retrieve_context(query: str, scenario: Optional[str] = None, k: int = 3,
                     max_chars: int = 1200) -> str:
    """给决策流用:检索命中书摘 → 拼成可注入 prompt 的文本块。
    库不存在或无命中 → 返回空串(绝不影响决策)。"""
    try:
        if not _db_path().exists():
            return ""
        hits = retrieve(query, scenario=scenario, k=k)
    except Exception:
        return ""
    if not hits:
        return ""
    lines = ["[书库检索 — 来自已灌入的真实书籍, 请优先据此作答, 并在结论中标注引用的书名]"]
    used = 0
    for h in hits:
        seg = " ".join((h.get("content") or "").split())[:400]
        piece = f"《{h.get('title')}》: {seg}"
        if used + len(piece) > max_chars:
            break
        lines.append(piece)
        used += len(piece)
    return "\n".join(lines)


# ---------- CLI ----------
def main():
    import argparse
    ap = argparse.ArgumentParser(description="书库 RAG 管线")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("ingest"); pi.add_argument("--dropzone"); pi.add_argument("--force", action="store_true")
    ps = sub.add_parser("search"); ps.add_argument("query"); ps.add_argument("--scenario"); ps.add_argument("-k", type=int, default=5)
    sub.add_parser("stats")
    a = ap.parse_args()
    if a.cmd == "ingest":
        print(json.dumps(ingest(a.dropzone, a.force), ensure_ascii=False, indent=2))
    elif a.cmd == "search":
        for r in retrieve(a.query, a.scenario, a.k):
            print(f"[{r['score']}] 《{r['title']}》{r['scenario']}\n  {r['content'][:120]}...\n")
    elif a.cmd == "stats":
        s = BookStore(_db_path(), None); print(json.dumps(s.stats(), ensure_ascii=False)); s.close()


if __name__ == "__main__":
    main()
