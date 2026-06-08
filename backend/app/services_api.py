"""services_api — NAS 蜂群后端侧的"服务运行状态 + 一键启停"代理 (/api/services/**)。

前端"服务管理"面板只跟 NAS 说话, 分两块:

  群晖蜂群 (swarm): NAS 上的 Docker 容器 (backend 自身 / 爬虫 / 记忆 / 向量库)。
    只读状态 (HTTP 探活), 不提供启停 —— 停掉 backend 会把用户正在看的网页弄断。

  PC 手脚爬虫 (pc): 跑在 PC 桌面的七剑客 worker + 媒体爬虫。
    NAS 把请求转发给 PC 管家 (8410, BEE_SUPERVISOR_URL), 实现网页一键启停。
    PC 管家离线 → 返回 {online:false}, 前端显示"未连接", 不报错崩。
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, Body

from .tools.seven_clients import bee_clients, ToolCallError

router = APIRouter(prefix="/api/services", tags=["services"])


# ---- 群晖蜂群容器: HTTP 探活 (backend 走 host 网络, 同主机 127.0.0.1 可达各容器发布端口) ----
def _probe(url: str, timeout: float = 4.0) -> bool:
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.get(url)
        return r.status_code < 500
    except Exception:
        return False


def _swarm_status() -> list[dict[str, Any]]:
    scraper = bee_clients.scraper_url.rstrip("/")
    memory = bee_clients.memory_url.rstrip("/")
    qdrant = os.environ.get("BEE_QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")
    return [
        {"key": "backend", "name": "蜂群大脑 (决策/前端)", "port": 8100, "running": True,
         "note": "你正在用的就是它"},
        {"key": "scraper", "name": "爬虫 (站内搜索/熔断)", "port": 8003,
         "running": _probe(f"{scraper}/healthz")},
        {"key": "memory", "name": "记忆 (经验检索)", "port": 8004,
         "running": _probe(f"{memory}/healthz")},
        {"key": "qdrant", "name": "向量库 (Qdrant)", "port": 6333,
         "running": _probe(f"{qdrant}/")},
    ]


def _pc_offline(detail: str = "") -> dict[str, Any]:
    return {"online": False,
            "error": detail or "PC 管家未连接 (检查 BEE_SUPERVISOR_URL / PC 管家 8410 是否启动)"}


# ---- 路由 ----
@router.get("/status")
def status() -> dict[str, Any]:
    """群晖侧容器状态 (只读) + PC 侧服务状态 (经管家)。"""
    swarm = _swarm_status()
    try:
        pc = bee_clients.sup_get("/sup/status", timeout=8)
        pc_block: dict[str, Any] = {"online": True, "services": pc.get("services", [])}
    except ToolCallError as e:
        pc_block = _pc_offline(str(e))
    return {"swarm": swarm, "pc": pc_block}


@router.post("/pc/start")
def pc_start(body: dict = Body(default={})) -> dict[str, Any]:
    """启动 PC 手脚/爬虫服务 (body 可带 {keys:[...]}, 缺省全部)。管家启动后会 sleep 等就绪。"""
    try:
        r = bee_clients.sup_post("/sup/start", body or {}, timeout=40)
        return {"online": True, **r}
    except ToolCallError as e:
        return _pc_offline(str(e))


@router.post("/pc/stop")
def pc_stop(body: dict = Body(default={})) -> dict[str, Any]:
    try:
        r = bee_clients.sup_post("/sup/stop", body or {}, timeout=30)
        return {"online": True, **r}
    except ToolCallError as e:
        return _pc_offline(str(e))


@router.post("/pc/restart")
def pc_restart(body: dict = Body(default={})) -> dict[str, Any]:
    try:
        r = bee_clients.sup_post("/sup/restart", body or {}, timeout=45)
        return {"online": True, **r}
    except ToolCallError as e:
        return _pc_offline(str(e))


# ---- 键鼠总闸 (紧急 kill-switch): 网页一键停掉 PC 上所有真实点击/输入 ----
@router.get("/input/master")
def input_master_status() -> dict[str, Any]:
    """读 PC 键鼠总闸状态 (经管家路由到 8008)。离线返回 {online:false}。"""
    try:
        r = bee_clients.input_master_get()
        return {"online": True, **r}
    except ToolCallError as e:
        return _pc_offline(str(e))


@router.post("/input/master")
def input_master_set(body: dict = Body(default={})) -> dict[str, Any]:
    """切 PC 键鼠总闸; body {enabled:bool}。off=拦下所有真实点击/输入。"""
    enabled = bool(body.get("enabled", True))
    try:
        r = bee_clients.input_master_set(enabled)
        return {"online": True, **r}
    except ToolCallError as e:
        return _pc_offline(str(e))
