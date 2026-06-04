# -*- coding: utf-8 -*-
"""书库到位检查器 (booklib_check) —— 纯标准库, 无第三方依赖。

用途:扫描"投书文件夹", 对照 booklists/*.md 里所有书单的所需书目,
给出每本书的状态, 并把谁还没到位、谁多余了列清楚。

状态:
  ✅ 已到位已灌   —— 文件在 + 已被程序灌进知识库 (booklists/.ingested.json 记录)
  📥 已到位未灌   —— 文件在, 但还没进知识库
  ❌ 缺失          —— 书单里要, 投书文件夹里还没有
  ❓ 多余文件      —— 文件夹里有, 但不匹配任何书单条目

运行:
    python -m app.seed_knowledge.booklib_check
    python -m app.seed_knowledge.booklib_check --dropzone "D:\\我的书库"

报告写到 booklists/_inventory_report.md, 同时打印摘要。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOOKLISTS_DIR = HERE / "booklists"
REPO_ROOT = HERE.parents[2]  # .../h-semas
DEFAULT_DROPZONE = REPO_ROOT / "books_dropzone"
INGESTED_STATE = BOOKLISTS_DIR / ".ingested.json"
REPORT_PATH = BOOKLISTS_DIR / "_inventory_report.md"

BOOK_EXTS = {".pdf", ".epub", ".mobi", ".azw3", ".txt", ".docx", ".doc"}
_PAREN = re.compile(r"[（(【\[].*?[）)】\]]")
_NONWORD = re.compile(r"[\s　_\-—·、,，。.:：;；!！?？'\"“”‘’/\\|()（）]+")


def _norm(s: str) -> str:
    """标准化书名/文件名, 便于模糊匹配。"""
    s = (s or "").strip()
    s = _PAREN.sub("", s)          # 去括号内版本/副标题
    s = _NONWORD.sub("", s)        # 去空白与标点
    return s.lower()


def _iter_md_tables(md_text: str):
    """逐个 markdown 表格产出 (headers, rows) ; rows 为 list[list[str]]。"""
    headers = None
    rows = []
    for line in md_text.splitlines():
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):  # 分隔行 |---|---|
                continue
            if headers is None:
                headers = cells
            else:
                rows.append(cells)
        else:
            if headers is not None:
                yield headers, rows
            headers, rows = None, []
    if headers is not None:
        yield headers, rows


def load_required() -> dict:
    """从 booklists/*.md 收集所需书目, 按标准化书名去重。
    返回 {norm_title: {"title":.., "author":.., "douban":.., "scenarios":set}}"""
    required: dict[str, dict] = {}
    if not BOOKLISTS_DIR.is_dir():
        return required
    for md in sorted(BOOKLISTS_DIR.glob("*.md")):
        if md.name.startswith("_inventory"):
            continue
        scenario = md.stem
        text = md.read_text(encoding="utf-8")
        for headers, rows in _iter_md_tables(text):
            if "书名" not in headers:
                continue
            ti = headers.index("书名")
            ai = headers.index("作者") if "作者" in headers else (
                headers.index("作者/版本") if "作者/版本" in headers else None)
            di = headers.index("豆瓣") if "豆瓣" in headers else None
            for r in rows:
                if ti >= len(r):
                    continue
                title = r[ti].strip()
                if not title or title in ("书名",):
                    continue
                key = _norm(title)
                if len(key) < 2:
                    continue
                ent = required.setdefault(key, {
                    "title": title, "author": "", "douban": "", "scenarios": set()})
                ent["scenarios"].add(scenario)
                if ai is not None and ai < len(r) and not ent["author"]:
                    ent["author"] = r[ai].strip()
                if di is not None and di < len(r) and not ent["douban"]:
                    ent["douban"] = r[di].strip()
    return required


def load_ingested() -> set:
    """读取已灌入知识库的书 (标准化书名集合)。文件不存在 → 空集。"""
    if not INGESTED_STATE.is_file():
        return set()
    try:
        data = json.loads(INGESTED_STATE.read_text(encoding="utf-8"))
    except Exception:
        return set()
    items = data.get("ingested", data) if isinstance(data, dict) else data
    out = set()
    for it in (items or []):
        if isinstance(it, str):
            out.add(_norm(it))
        elif isinstance(it, dict) and it.get("title"):
            out.add(_norm(it["title"]))
    return out


def scan_dropzone(dropzone: Path) -> list:
    """返回投书文件夹下所有书文件 [(path, norm_stem)]。"""
    files = []
    if not dropzone.is_dir():
        return files
    for p in dropzone.rglob("*"):
        if p.is_file() and p.suffix.lower() in BOOK_EXTS:
            files.append((p, _norm(p.stem)))
    return files


def match(required: dict, files: list) -> tuple:
    """把文件匹配到所需书目。返回 (present:set(norm_title), file_for, extra_files:list)。"""
    present = set()
    file_for = {}          # norm_title -> 文件名
    used_files = set()
    for key in required:
        for path, stem in files:
            if not stem:
                continue
            if key in stem or stem in key:   # 双向子串模糊匹配
                present.add(key)
                file_for[key] = path.name
                used_files.add(path)
                break
    extra = [p.name for p, _ in files if p not in used_files]
    return present, file_for, extra


def summary(dropzone: str | None = None) -> dict:
    """结构化统计(供后端端点/前端书库面板用)。"""
    dz = Path(dropzone) if dropzone else DEFAULT_DROPZONE
    dz.mkdir(parents=True, exist_ok=True)
    required = load_required()
    ingested = load_ingested()
    files = scan_dropzone(dz)
    present, _file_for, extra = match(required, files)
    done = in_place = 0
    missing: list[str] = []
    for key, ent in required.items():
        if key in present and key in ingested:
            done += 1
        elif key in present:
            in_place += 1
        else:
            missing.append(ent["title"])
    return {"total": len(required), "done": done, "in_place": in_place,
            "missing": len(missing), "extra": len(extra),
            "dropzone": str(dz), "files_in_dropzone": len(files)}


def export_lists() -> dict:
    """把全部书单导出为 CSV(书名/作者/豆瓣/Goodreads/类/归属) + 纯书名 TXT。"""
    import csv as _csv
    import io as _io
    books: dict[str, dict] = {}
    for md in sorted(BOOKLISTS_DIR.glob("*.md")):
        if md.name.startswith(("_inventory", "_导出")):
            continue
        sc = md.stem
        for headers, rows in _iter_md_tables(md.read_text(encoding="utf-8")):
            if "书名" not in headers:
                continue
            ti = headers.index("书名")
            ai = headers.index("作者") if "作者" in headers else None
            di = headers.index("豆瓣") if "豆瓣" in headers else None
            gi = headers.index("Goodreads") if "Goodreads" in headers else None
            ci = next((headers.index(h) for h in headers if h.startswith("类")), None)
            for r in rows:
                if ti >= len(r) or not r[ti].strip() or r[ti].strip() == "书名":
                    continue
                k = _norm(r[ti])
                if len(k) < 2:
                    continue
                e = books.setdefault(k, {"title": r[ti].strip(), "author": "",
                                         "douban": "", "gr": "", "cls": "", "scenes": set()})
                e["scenes"].add(sc)
                for idx, fld in ((ai, "author"), (di, "douban"), (gi, "gr"), (ci, "cls")):
                    if idx is not None and idx < len(r) and not e[fld]:
                        e[fld] = r[idx].strip()
    csv_p = BOOKLISTS_DIR / "_导出_全部书单.csv"
    txt_p = BOOKLISTS_DIR / "_导出_书名清单.txt"
    with _io.open(csv_p, "w", encoding="utf-8-sig", newline="") as fp:
        w = _csv.writer(fp)
        w.writerow(["书名", "作者", "豆瓣", "Goodreads", "类", "归属场景"])
        for e in sorted(books.values(), key=lambda x: x["title"]):
            w.writerow([e["title"], e["author"], e["douban"], e["gr"], e["cls"],
                        ";".join(sorted(e["scenes"]))])
    txt_p.write_text("\n".join(sorted(e["title"] for e in books.values())), encoding="utf-8")
    return {"unique": len(books), "csv": str(csv_p), "txt": str(txt_p)}


def main():
    ap = argparse.ArgumentParser(description="书库到位检查器")
    ap.add_argument("--dropzone", default=str(DEFAULT_DROPZONE),
                    help="投书文件夹路径 (默认 <repo>/books_dropzone)")
    args = ap.parse_args()
    dropzone = Path(args.dropzone)
    dropzone.mkdir(parents=True, exist_ok=True)

    required = load_required()
    ingested = load_ingested()
    files = scan_dropzone(dropzone)
    present, file_for, extra = match(required, files)

    done, in_place_raw, missing = [], [], []
    for key, ent in sorted(required.items(), key=lambda kv: kv[1]["title"]):
        row = (ent["title"], ent["author"], ent["douban"],
               ", ".join(sorted(ent["scenarios"])), file_for.get(key, ""))
        if key in present and key in ingested:
            done.append(row)
        elif key in present:
            in_place_raw.append(row)
        else:
            missing.append(row)

    total = len(required)
    lines = []
    lines.append("# 📚 书库到位检查报告\n")
    lines.append(f"- 书单所需总数:**{total}** 本")
    lines.append(f"- ✅ 已到位已灌(被程序使用):**{len(done)}**")
    lines.append(f"- 📥 已到位未灌:**{len(in_place_raw)}**")
    lines.append(f"- ❌ 缺失:**{len(missing)}**")
    lines.append(f"- ❓ 多余文件:**{len(extra)}**")
    lines.append(f"- 投书文件夹:`{dropzone}`\n")

    def tbl(title, rows):
        lines.append(f"\n## {title}({len(rows)})\n")
        if not rows:
            lines.append("(无)\n"); return
        lines.append("| 书名 | 作者 | 豆瓣 | 归属 | 文件 |")
        lines.append("|------|------|------|------|------|")
        for t, a, d, sc, f in rows:
            lines.append(f"| {t} | {a} | {d} | {sc} | {f} |")

    tbl("❌ 缺失(还没放进文件夹)", missing)
    tbl("📥 已到位未灌(可触发灌库)", in_place_raw)
    tbl("✅ 已到位已灌(被程序使用)", done)
    if extra:
        lines.append(f"\n## ❓ 多余文件(不在任何书单,{len(extra)})\n")
        for f in sorted(extra):
            lines.append(f"- {f}")

    report = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")

    print(f"[booklib] 所需 {total} | 已灌 {len(done)} | 已到位未灌 "
          f"{len(in_place_raw)} | 缺失 {len(missing)} | 多余 {len(extra)}")
    print(f"[booklib] 报告已写入: {REPORT_PATH}")


if __name__ == "__main__":
    main()
