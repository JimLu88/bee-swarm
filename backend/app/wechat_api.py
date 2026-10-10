"""wechat_api — NAS 蜂群后端侧的"微信自动聊天"代理 (/api/wechat/**)。

前端面板只跟 NAS 说话; NAS 把请求转发给跑在 PC 桌面的 bee-wechat 服务 (8010, BEE_WECHAT_URL)。
PC 离线/没起 → 返回 {online:false} 而不是 500, 前端据此显示"未连接", 不报错崩。

唯一的"加工": 保存配置时, 自动把 LLM 网关 (base_url + key) 注入推给 PC,
让用户在前端已填过的网关凭证直接复用, 无需在 PC 再配一遍 key。
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from .tools.seven_clients import bee_clients, ToolCallError

router = APIRouter(prefix="/api/wechat", tags=["wechat"])


def _llm_creds() -> dict[str, str]:
    """解析当前生效的 LLM 网关 (供 PC 微信服务用同一套便宜模型)。
    优先 env (启动时 hub_settings 已注入 OPENAI_API_*), 再退 settings 对象。"""
    base = (os.environ.get("OPENAI_API_BASE") or os.environ.get("OPENAI_BASE_URL") or "").strip()
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    try:
        from .settings_llm_rag import LlmRagSettings
        s = LlmRagSettings()
        base = base or (s.litellm_base_url or "").strip()
        key = key or (s.openai_api_key or "").strip()
    except Exception:
        pass
    out: dict[str, str] = {}
    if base:
        out["llm_base_url"] = base
    if key:
        out["llm_api_key"] = key
    return out


def _offline(detail: str = "") -> dict[str, Any]:
    return {"online": False, "error": detail or "PC 微信服务未连接 (检查 BEE_WECHAT_URL / 微信助手是否启动)"}


@router.get("/config")
def get_config() -> dict:
    try:
        r = bee_clients.wechat_get("/wechat/config")
        return {"online": True, **r}
    except ToolCallError as e:
        return _offline(str(e))


@router.post("/config")
def set_config(patch: dict = Body(default={})) -> dict:
    body = dict(patch or {})
    body.update(_llm_creds())   # 注入网关凭证 (前端不必重复填 key)
    try:
        r = bee_clients.wechat_post("/wechat/config", body)
        return {"online": True, **r}
    except ToolCallError as e:
        return _offline(str(e))


@router.get("/status")
def get_status() -> dict:
    try:
        r = bee_clients.wechat_get("/wechat/status")
        return {"online": True, **r}
    except ToolCallError as e:
        return _offline(str(e))


@router.post("/start")
def start() -> dict:
    try:
        # 启动前先把网关凭证推过去, 保证 auto 模式能生成回复
        try:
            bee_clients.wechat_post("/wechat/config", _llm_creds())
        except ToolCallError:
            pass
        return {"online": True, **bee_clients.wechat_post("/wechat/start")}
    except ToolCallError as e:
        return _offline(str(e))


@router.post("/stop")
def stop() -> dict:
    try:
        return {"online": True, **bee_clients.wechat_post("/wechat/stop")}
    except ToolCallError as e:
        return _offline(str(e))


@router.get("/sessions")
def sessions() -> dict:
    try:
        return {"online": True, **bee_clients.wechat_get("/wechat/sessions", timeout=20)}
    except ToolCallError as e:
        return _offline(str(e))


@router.get("/pending")
def pending() -> dict:
    try:
        return {"online": True, **bee_clients.wechat_get("/wechat/pending")}
    except ToolCallError as e:
        return _offline(str(e))


@router.post("/pending/approve")
def pending_approve(body: dict = Body(default={})) -> dict:
    if not str(body.get("id") or "").strip():
        raise HTTPException(400, "missing id")
    try:
        return {"online": True, **bee_clients.wechat_post("/wechat/pending/approve", body)}
    except ToolCallError as e:
        return _offline(str(e))


@router.post("/pending/reject")
def pending_reject(body: dict = Body(default={})) -> dict:
    if not str(body.get("id") or "").strip():
        raise HTTPException(400, "missing id")
    try:
        return {"online": True, **bee_clients.wechat_post("/wechat/pending/reject", body)}
    except ToolCallError as e:
        return _offline(str(e))


@router.post("/chat/resume")
def chat_resume(body: dict = Body(default={})) -> dict:
    if not str(body.get("chat") or "").strip():
        raise HTTPException(400, "missing chat")
    try:
        return {"online": True, **bee_clients.wechat_post("/wechat/chat/resume", body)}
    except ToolCallError as e:
        return _offline(str(e))


@router.post("/chat/pause")
def chat_pause(body: dict = Body(default={})) -> dict:
    if not str(body.get("chat") or "").strip():
        raise HTTPException(400, "missing chat")
    try:
        return {"online": True, **bee_clients.wechat_post("/wechat/chat/pause", body)}
    except ToolCallError as e:
        return _offline(str(e))
