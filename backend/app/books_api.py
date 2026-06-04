# -*- coding: utf-8 -*-
"""书库管理 HTTP 端点(挂 /api/books/**),供设置里的「📚 书库」面板调用。

- GET  /api/books/status        到位统计(总需/已灌/已到位未灌/缺失/多余)+ 向量库状态
- POST /api/books/scan          重新扫描投书文件夹, 返回统计(写 _inventory_report.md)
- POST /api/books/ingest        把投书文件夹里的书切块+嵌入入库(幂等), 回写 .ingested.json
- POST /api/books/export        导出全部书单 CSV + 纯书名 TXT(给 Olib/Calibre 用)
- POST /api/books/fetch-legal   从公版免费源自动下载(只合法源, 不碰盗版)

注意:Z-Library 等盗版站的批量下载不在本系统实现;请用导出的书单自行操作。
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body

router = APIRouter(prefix="/api/books", tags=["books"])


@router.get("/status")
def status() -> dict[str, Any]:
    from .seed_knowledge import booklib_check as blc
    out: dict[str, Any] = {"inventory": {}, "store": {}}
    try:
        out["inventory"] = blc.summary()
    except Exception as e:  # noqa: BLE001
        out["inventory"] = {"error": repr(e)}
    try:
        from .books_rag.store import BookStore
        from .books_rag.pipeline import _db_path
        if _db_path().exists():
            s = BookStore(_db_path(), None)
            out["store"] = s.stats()
            s.close()
        else:
            out["store"] = {"books": 0, "chunks": 0, "note": "尚未灌库"}
    except Exception as e:  # noqa: BLE001
        out["store"] = {"error": repr(e)}
    return out


@router.post("/scan")
async def scan() -> dict[str, Any]:
    from .seed_knowledge import booklib_check as blc
    res = await asyncio.to_thread(blc.summary)
    try:
        await asyncio.to_thread(blc.main)  # 同时写出 _inventory_report.md
    except SystemExit:
        pass
    except Exception:
        pass
    return {"ok": True, **res}


@router.post("/ingest")
async def ingest(body: dict = Body(default={})) -> dict[str, Any]:
    force = bool(body.get("force"))
    try:
        from .books_rag.pipeline import ingest as _ingest
        res = await asyncio.to_thread(_ingest, None, force)
        return {"ok": True, **res}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": repr(e)}


@router.post("/export")
async def export() -> dict[str, Any]:
    from .seed_knowledge import booklib_check as blc
    try:
        res = await asyncio.to_thread(blc.export_lists)
        return {"ok": True, **res}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": repr(e)}


@router.post("/fetch-legal")
async def fetch_legal_ep(body: dict = Body(default={})) -> dict[str, Any]:
    limit = int(body.get("limit", 30))
    try:
        from .books_rag.fetch_legal import fetch_legal
        res = await asyncio.to_thread(fetch_legal, limit, None)
        return {"ok": True, **res}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": repr(e)}


@router.post("/classify")
async def classify_ep() -> dict[str, Any]:
    """分清单:合法可下载(公版)vs 待自行获取(无合法免费源),各出一份 CSV。"""
    try:
        from .books_rag.fetch_legal import classify
        res = await asyncio.to_thread(classify)
        return {"ok": True, **res}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": repr(e)}
