"""mcp_client — v13 #1 第②步: MCP 真实调用引擎.

把第①步注册表(mcp_tools)里"已启用且配好 Key/URL"的服务, 变成能真正发请求的工具:
- 真 MCP 服务 (alpha_vantage / firecrawl / github / context7 / pubmed):
  走 MCP Streamable-HTTP JSON-RPC (initialize → tools/list → tools/call).
- 非 MCP 的 REST (weather=OpenWeather): 用户填的是原生 REST URL, 走专用适配器.

每家 MCP 的鉴权方式不同, 用 `_endpoint_and_headers()` 按 server_id 归一:
- bearer    : Authorization: Bearer <key>            (github / context7 / pipedream)
- query:apikey: <url>?apikey=<key>                    (alpha_vantage)
- path      : <url>/<key>/v2/mcp                       (firecrawl, key 在路径里)
- none      : 不鉴权                                   (pubmed)
- rest      : 不是 MCP, 走 REST 适配器                 (weather)

对外:
- probe(server_id)        测试连通 (配置页"测试"按钮用), 返回 {ok, tool_count, sample, error}
- list_tools(server_id)   列该服务的工具 (带 TTL 缓存)
- call_tool(server_id,name,args)  调用并返回文本结果
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from . import mcp_tools

# tools/list 结果缓存 (server_id -> (expire_ts, tools)). 减少决策时的 initialize+list 往返.
_TOOLS_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_TOOLS_TTL_SEC = 1800  # 30 分钟

_HTTP_TIMEOUT = 20.0
_PROTOCOL_VERSION = "2025-06-18"


class McpError(Exception):
    pass


# ---------- 每家服务的鉴权/端点归一 ----------
# server_id -> auth 风格. 不在表里的真 MCP 默认按 bearer 试 (有 key 才加头).
_AUTH_STYLE: dict[str, str] = {
    "alpha_vantage": "query:apikey",
    "weather": "rest",
    "firecrawl": "path",
    "github": "bearer",
    "context7": "bearer",
    "pubmed": "none",
    "google_maps": "stdio",
    "airbnb": "stdio",
    "pipedream": "bearer",
}


def _endpoint_and_headers(rt: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """根据预置 server_id 的鉴权风格, 返回真正要打的 (url, headers)."""
    sid = rt.get("id", "")
    url = (rt.get("url") or "").rstrip("/")
    key = rt.get("key") or ""
    style = _AUTH_STYLE.get(sid, "bearer")
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if not url:
        raise McpError(f"{sid}: 未配置 URL")
    if style == "query:apikey":
        if key:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}apikey={key}"
    elif style == "path":
        # firecrawl: key 在路径里. 用户只填了 https://mcp.firecrawl.dev → 补成 /<key>/v2/mcp
        if key and key not in url:
            url = f"{url}/{key}/v2/mcp"
    elif style == "bearer":
        if key:
            headers["Authorization"] = f"Bearer {key}"
    elif style == "none":
        pass
    return url, headers


# ---------- MCP Streamable-HTTP JSON-RPC ----------
def _parse_rpc_response(resp: httpx.Response) -> dict[str, Any]:
    """MCP 流式 HTTP 可能回 application/json 或 text/event-stream(SSE). 都解析出 JSON-RPC 对象."""
    ctype = resp.headers.get("content-type", "")
    body = resp.text
    if "text/event-stream" in ctype:
        # SSE: 多行 data: {json}. 取最后一个带 result/error 的.
        chosen: dict[str, Any] | None = None
        for line in body.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                obj = json.loads(payload)
            except Exception:
                continue
            if isinstance(obj, dict) and ("result" in obj or "error" in obj):
                chosen = obj
        if chosen is None:
            raise McpError(f"SSE 无有效 JSON-RPC 响应: {body[:200]}")
        return chosen
    # 普通 JSON
    try:
        return json.loads(body)
    except Exception as e:
        raise McpError(f"响应非 JSON ({resp.status_code}): {body[:200]}") from e


async def _rpc(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    method: str,
    params: dict[str, Any] | None = None,
    *,
    rpc_id: int = 1,
    notify: bool = False,
) -> dict[str, Any] | None:
    body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if not notify:
        body["id"] = rpc_id
    if params is not None:
        body["params"] = params
    resp = await client.post(url, json=body, headers=headers)
    if notify:
        return None
    if resp.status_code >= 400:
        raise McpError(f"{method} HTTP {resp.status_code}: {resp.text[:200]}")
    obj = _parse_rpc_response(resp)
    if isinstance(obj, dict) and obj.get("error"):
        err = obj["error"]
        raise McpError(f"{method} RPC error: {err.get('message', err)}")
    return obj


async def _mcp_session(rt: dict[str, Any]):
    """开一个 MCP 会话, 完成 initialize 握手, 返回 (client, url, headers). 调用方负责 aclose."""
    url, headers = _endpoint_and_headers(rt)
    client = httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True)
    try:
        await _rpc(
            client, url, headers, "initialize",
            {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "h-semas", "version": "13"},
            },
        )
        # 发 initialized 通知 (协议要求); 无状态服务忽略亦可.
        try:
            await _rpc(client, url, headers, "notifications/initialized", {}, notify=True)
        except Exception:
            pass
        return client, url, headers
    except Exception:
        await client.aclose()
        raise


async def _list_tools_live(rt: dict[str, Any]) -> list[dict[str, Any]]:
    sid = rt.get("id", "")
    if _AUTH_STYLE.get(sid) == "rest":
        return _rest_tools(sid)
    client, url, headers = await _mcp_session(rt)
    try:
        obj = await _rpc(client, url, headers, "tools/list", {}, rpc_id=2)
        tools = (((obj or {}).get("result") or {}).get("tools")) or []
        out: list[dict[str, Any]] = []
        for t in tools:
            if not isinstance(t, dict):
                continue
            out.append({
                "name": t.get("name", ""),
                "description": (t.get("description") or "")[:300],
                "input_schema": t.get("inputSchema") or t.get("input_schema") or {},
            })
        return out
    finally:
        await client.aclose()


async def list_tools(server_id: str, *, force: bool = False) -> list[dict[str, Any]]:
    now = time.monotonic()
    if not force:
        hit = _TOOLS_CACHE.get(server_id)
        if hit and hit[0] > now:
            return hit[1]
    rt = mcp_tools.server_runtime(server_id)
    tools = await _list_tools_live(rt)
    _TOOLS_CACHE[server_id] = (now + _TOOLS_TTL_SEC, tools)
    return tools


def _content_to_text(result: Any) -> str:
    """MCP tools/call 的 result.content 是块数组, 抽出文本."""
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for blk in content:
                if isinstance(blk, dict):
                    if blk.get("text"):
                        parts.append(str(blk["text"]))
            if parts:
                return "\n".join(parts)
        if result.get("structuredContent") is not None:
            return json.dumps(result["structuredContent"], ensure_ascii=False)[:4000]
    return json.dumps(result, ensure_ascii=False)[:4000]


async def call_tool(server_id: str, tool_name: str, args: dict[str, Any]) -> str:
    rt = mcp_tools.server_runtime(server_id)
    if _AUTH_STYLE.get(server_id) == "rest":
        return await _rest_call(server_id, tool_name, args, rt)
    client, url, headers = await _mcp_session(rt)
    try:
        obj = await _rpc(
            client, url, headers, "tools/call",
            {"name": tool_name, "arguments": args or {}}, rpc_id=3,
        )
        return _content_to_text((obj or {}).get("result"))
    finally:
        await client.aclose()


# ---------- REST 适配器 (weather=OpenWeather, 用户填的是原生 REST) ----------
def _rest_tools(server_id: str) -> list[dict[str, Any]]:
    if server_id == "weather":
        return [{
            "name": "get_weather",
            "description": "查询某城市当前天气 (温度/天气/湿度/风). 参数 location=城市名(英文或拼音, 如 Shanghai/Beijing).",
            "input_schema": {
                "type": "object",
                "properties": {"location": {"type": "string", "description": "城市名"}},
                "required": ["location"],
            },
        }]
    return []


async def _rest_call(server_id: str, tool_name: str, args: dict[str, Any], rt: dict[str, Any]) -> str:
    if server_id == "weather":
        loc = str((args or {}).get("location") or (args or {}).get("q") or "").strip()
        if not loc:
            raise McpError("weather: 缺少 location 参数")
        url = (rt.get("url") or "").strip()
        key = rt.get("key") or ""
        if not url or not key:
            raise McpError("weather: 未配置 URL/Key")
        params = {"q": loc, "appid": key, "units": "metric", "lang": "zh_cn"}
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.get(url, params=params)
            if r.status_code >= 400:
                raise McpError(f"OpenWeather HTTP {r.status_code}: {r.text[:160]}")
            d = r.json()
        try:
            w = (d.get("weather") or [{}])[0].get("description", "")
            main = d.get("main") or {}
            wind = (d.get("wind") or {}).get("speed")
            name = d.get("name", loc)
            return (f"{name} 当前天气: {w}, 气温 {main.get('temp')}°C "
                    f"(体感 {main.get('feels_like')}°C), 湿度 {main.get('humidity')}%, 风速 {wind} m/s")
        except Exception:
            return json.dumps(d, ensure_ascii=False)[:1500]
    raise McpError(f"未知 REST 服务: {server_id}")


# ---------- 配置页"测试连通"用 ----------
async def probe(server_id: str) -> dict[str, Any]:
    """测试某服务能否连通 + 拉到工具. 配置页"测试"按钮调用."""
    rt = mcp_tools.server_runtime(server_id)
    out: dict[str, Any] = {"id": server_id, "transport": rt.get("transport"), "ok": False}
    if rt.get("transport") == "stdio":
        out["error"] = "stdio 类型需在容器内起子进程, 暂不支持线上测试"
        return out
    if rt.get("needs_key") and not rt.get("key"):
        out["error"] = "未填 Key"
        return out
    if rt.get("transport") == "http" and not rt.get("url"):
        out["error"] = "未填 URL"
        return out
    try:
        tools = await asyncio.wait_for(list_tools(server_id, force=True), timeout=25.0)
        out["ok"] = True
        out["tool_count"] = len(tools)
        out["sample"] = [t.get("name") for t in tools[:8]]
    except asyncio.TimeoutError:
        out["error"] = "连接超时 (25s)"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return out
