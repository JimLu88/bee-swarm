# -*- coding: utf-8 -*-
"""合法书源自动下载器(多书库 · 英文名查 · 只取公有领域)。

明确边界:**绝不碰 Z-Library 等盗版站,也不下 archive.org 上在版书的扫描件。**
只从下列合法源、且只取**公有领域**内容:
- Internet Archive(archive.org):加 `possible-copyright-status:NOT_IN_COPYRIGHT` 过滤,在版书被排除(已实测)。可达、主力。
- Project Gutenberg(gutendex):英文公版(本机直连可能被墙,群晖多半可达)。
西方经典按**英文原名**查(内置中→英映射);古籍按中文名走 archive 公版。

诚实说明:本书库 2610 本以现代中文/专业书为主,合法公版源只覆盖**约 10–15 本经典**,
其余无合法免费源 → 见 classify() 产出的「待自行获取」清单, 由用户自行用 Olib 等正当方式获取。
"""
from __future__ import annotations

import csv
import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List, Optional

from ..seed_knowledge import booklib_check as blc

_UA = {"User-Agent": "h-semas-books/2.0 (legal public-domain fetcher)"}
_TIMEOUT = 12

# 中文名 → 英文原名(仅收公有领域经典;在版书一律不放这里)
PD_MAP: dict[str, str] = {
    "国富论": "The Wealth of Nations",
    "国民财富的性质和原因的研究": "The Wealth of Nations",
    "道德情操论": "The Theory of Moral Sentiments",
    "理想国": "The Republic Plato",
    "政治学": "Politics Aristotle",
    "尼各马可伦理学": "Nicomachean Ethics",
    "社会契约论": "The Social Contract",
    "论法的精神": "The Spirit of the Laws",
    "利维坦": "Leviathan Hobbes",
    "政府论": "Two Treatises of Government",
    "君主论": "The Prince Machiavelli",
    "物种起源": "On the Origin of Species",
    "人类的由来": "The Descent of Man",
    "战争论": "On War Clausewitz",
    "资本论": "Das Kapital",
    "沉思录": "Meditations Marcus Aurelius",
    "瓦尔登湖": "Walden Thoreau",
    "论美国的民主": "Democracy in America",
    "常识": "Common Sense Thomas Paine",
    "乌托邦": "Utopia Thomas More",
    "新工具": "Novum Organum",
    "人性论": "A Treatise of Human Nature",
    "纯粹理性批判": "Critique of Pure Reason",
    "梦的解析": "The Interpretation of Dreams",
    "自然哲学的数学原理": "Mathematical Principles of Natural Philosophy",
    "几何原本": "Euclid Elements",
    "查拉图斯特拉如是说": "Thus Spoke Zarathustra",
    "国家与革命": "The State and Revolution",
    "爱弥儿": "Emile Rousseau",
    "忏悔录": "Confessions Rousseau",
}
# 古籍(中文名直接查 archive 公版)
CN_ANCIENT = {
    "黄帝内经", "伤寒论", "金匮要略", "温病条辨", "本草纲目", "神农本草经", "难经",
    "脾胃论", "医学衷中参西录", "孙子兵法", "论语", "孟子", "大学", "中庸", "庄子",
    "韩非子", "史记", "资治通鉴", "随园食单", "茶经", "齐民要术", "天工开物", "九章算术",
}


def _http(url: str) -> bytes:
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=_TIMEOUT).read()
    except Exception:
        return b""


def _base(title: str) -> str:
    return title.split("(")[0].split("（")[0].strip()


def _english_for(title: str) -> Optional[str]:
    """该书单标题对应的查询词:西方→英文原名;古籍→中文名;否则 None(无合法源)。"""
    b = _base(title)
    for k, en in PD_MAP.items():
        if b == k or b.startswith(k) or (len(k) >= 3 and k in b):
            return en
    for k in CN_ANCIENT:
        if b == k or (len(k) >= 3 and (b.startswith(k) or k in b)):
            return b  # 古籍用中文名查
    return None


# ---- Internet Archive(只取公有领域)----
def _archive_pd_download(query: str, dest_dir: Path, fname_base: str) -> Optional[str]:
    q = urllib.parse.quote(f'title:("{query}") AND mediatype:texts AND possible-copyright-status:NOT_IN_COPYRIGHT')
    d = _http(f"https://archive.org/advancedsearch.php?q={q}&fl[]=identifier&rows=1&output=json")
    if not d:
        return None
    try:
        docs = json.loads(d)["response"]["docs"]
    except Exception:
        return None
    if not docs:
        return None
    ident = docs[0]["identifier"]
    meta = _http(f"https://archive.org/metadata/{ident}")
    if not meta:
        return None
    try:
        files = json.loads(meta).get("files", [])
    except Exception:
        return None
    pick = None
    for ext in (".epub", ".txt"):
        for f in files:
            n = f.get("name", "")
            if n.lower().endswith(ext) and "_meta" not in n.lower():
                pick = (n, ext); break
        if pick:
            break
    if not pick:
        return None
    name, ext = pick
    data = _http(f"https://archive.org/download/{ident}/{urllib.parse.quote(name)}")
    if not data:
        return None
    out = dest_dir / f"{fname_base}{ext}"
    out.write_bytes(data)
    return out.name


def fetch_legal(limit: int = 50, dropzone: Optional[str] = None, sleep_sec: float = 0.6) -> dict:
    """对书单中**有合法公版源**的标题(英文名/古籍)逐个下到 books_dropzone。"""
    dz = Path(dropzone) if dropzone else blc.DEFAULT_DROPZONE
    dz.mkdir(parents=True, exist_ok=True)
    required = blc.load_required()
    have = {stem for _p, stem in blc.scan_dropzone(dz)}
    downloaded: List[str] = []
    tried = 0
    for ent in sorted(required.values(), key=lambda e: e["title"]):
        if tried >= limit:
            break
        title = ent["title"]
        q = _english_for(title)
        if not q:
            continue  # 无合法源 → 跳过(进"待自行获取")
        nt = blc._norm(title)
        if nt in have or any(nt in h or h in nt for h in have):
            continue
        tried += 1
        safe = "".join(c for c in _base(title) if c not in '\\/:*?"<>|')[:80]
        got = _archive_pd_download(q, dz, safe)
        time.sleep(sleep_sec)
        if got:
            downloaded.append(title)
    return {"source": "archive.org(公版)+gutenberg", "tried": tried,
            "downloaded": downloaded, "n_downloaded": len(downloaded),
            "note": "仅公有领域;现代/在版书无合法免费源,见「待自行获取」清单自行获取。"}


def classify() -> dict:
    """不联网, 把书单分成「合法可下载(公版)」与「待自行获取」两份 CSV。"""
    required = blc.load_required()
    can: List[tuple] = []
    cannot: List[tuple] = []
    for ent in sorted(required.values(), key=lambda e: e["title"]):
        title = ent["title"]
        q = _english_for(title)
        row = (title, ent.get("author", ""), ";".join(sorted(ent.get("scenarios", []))))
        if q:
            can.append((title, q, *row[1:]))
        else:
            cannot.append(row)
    bl = blc.BOOKLISTS_DIR
    with io.open(bl / "_合法可下载_公版.csv", "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.writer(fp); w.writerow(["书名", "查询词(英文/古籍)", "作者", "归属场景"])
        w.writerows(can)
    with io.open(bl / "_待自行获取_书单.csv", "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.writer(fp); w.writerow(["书名", "作者", "归属场景"])
        w.writerows(cannot)
    return {"can_download": len(can), "must_self_source": len(cannot),
            "csv_can": str(bl / "_合法可下载_公版.csv"),
            "csv_cannot": str(bl / "_待自行获取_书单.csv")}
