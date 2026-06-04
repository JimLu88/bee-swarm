# -*- coding: utf-8 -*-
"""合法书源自动下载器 —— 只从公有领域/开放获取源抓真书到 books_dropzone。

明确边界:**不碰 Z-Library 等盗版站**。这里只抓合法免费源:
- Project Gutenberg(经 Gutendex JSON API):英文公版经典覆盖好。
- (可扩展)Standard Ebooks / archive.org 公版 / OpenStax —— 留接口位。

诚实说明:本书库以现代中文/专业书为主,公版免费源**命中率有限**(主要覆盖英文公版经典、
部分古籍英译)。能合法下的自动下,下不到的在报告里列出, 由用户自行从正当渠道获取。
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List, Optional

from ..seed_knowledge import booklib_check as blc

_UA = {"User-Agent": "h-semas-books/1.0 (legal public-domain fetcher)"}
_TIMEOUT = 30


def _http_json(url: str) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _download(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            data = r.read()
        if not data:
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def _gutendex_find(title: str) -> Optional[tuple]:
    """在 Gutenberg 找 title;返回 (下载url, 后缀) 或 None。"""
    q = urllib.parse.quote(title)
    data = _http_json(f"https://gutendex.com/books?search={q}")
    if not data or not data.get("results"):
        return None
    fmts = data["results"][0].get("formats", {})
    for mime, suf in (("application/epub+zip", "epub"),
                      ("text/plain; charset=utf-8", "txt"),
                      ("text/plain", "txt")):
        if mime in fmts and not fmts[mime].endswith(".zip"):
            return fmts[mime], suf
    return None


def fetch_legal(limit: int = 30, dropzone: Optional[str] = None,
                sleep_sec: float = 1.0) -> dict:
    """对书单标题逐个查公版源, 能下的下到 books_dropzone。

    limit: 本次最多尝试多少本(防止一次跑太久 / 礼貌限速)。
    """
    dz = Path(dropzone) if dropzone else blc.DEFAULT_DROPZONE
    dz.mkdir(parents=True, exist_ok=True)
    required = blc.load_required()
    # 已在文件夹里的(标准化名)→ 跳过
    have = {stem for _p, stem in blc.scan_dropzone(dz)}

    titles = [ent["title"] for ent in required.values()]
    downloaded: List[str] = []
    checked = 0
    for title in sorted(titles):
        if checked >= limit:
            break
        nt = blc._norm(title)
        if nt in have or any(nt in h or h in nt for h in have):
            continue
        checked += 1
        hit = _gutendex_find(title)
        time.sleep(sleep_sec)  # 礼貌限速,别把人家 API 打挂
        if not hit:
            continue
        url, suf = hit
        safe = "".join(c for c in title if c not in '\\/:*?"<>|')[:80]
        if _download(url, dz / f"{safe}.{suf}"):
            downloaded.append(title)
    return {"source": "project-gutenberg(公版)", "checked": checked,
            "downloaded": downloaded, "n_downloaded": len(downloaded),
            "note": "仅公版免费源;现代中文/专业书命中率有限,未下到的请自行从正当渠道获取。"}
