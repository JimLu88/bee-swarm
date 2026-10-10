"""cookies_api — NAS 蜂群后端侧的"爬虫 Cookie 管理"代理 (/api/cookies/**)。

前端设置面板的 Cookie 区只跟 NAS 说话; NAS 转发给跑在 PC 的媒体爬虫 (8009, BEE_MEDIA_URL)。
Cookie 文件 (cookies/<platform>.txt) 的唯一数据源在 PC —— 群晖面板和 PC 自带页改的是同一份。
PC 离线 → 返回 {online:false}, 前端显示"未连接", 不报错崩。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from .tools.seven_clients import bee_clients, ToolCallError

router = APIRouter(prefix="/api/cookies", tags=["cookies"])


def _offline(detail: str = "") -> dict[str, Any]:
    return {"online": False,
            "error": detail or "PC 媒体爬虫未连接 (检查 BEE_MEDIA_URL / 媒体爬虫 8009 是否启动)"}


@router.get("/list")
def cookies_list() -> dict[str, Any]:
    try:
        return {"online": True, **bee_clients.media_get("/mc/cookies", timeout=8)}
    except ToolCallError as e:
        return _offline(str(e))


@router.get("/get/{platform}")
def cookie_get(platform: str) -> dict[str, Any]:
    try:
        return {"online": True, **bee_clients.media_get(f"/mc/cookie/{platform}", timeout=8)}
    except ToolCallError as e:
        return _offline(str(e))


@router.post("/set")
def cookie_set(body: dict = Body(default={})) -> dict[str, Any]:
    if not str(body.get("platform") or "").strip():
        raise HTTPException(status_code=400, detail="missing platform")
    try:
        return {"online": True, **bee_clients.media_post("/mc/cookie", body, timeout=10)}
    except ToolCallError as e:
        return _offline(str(e))
