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
    "pubmed": "rest",  # 用户填的是 NCBI E-utilities REST, 非 MCP → 走 REST 适配器
    "osm": "rest",      # OpenStreetMap: Nominatim 地理编码 + OSRM 路线, 免 key 免卡
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
    """开一个 MCP 会话, 完成 initialize 握手, 返回 (client, url, headers). 调用方负责 aclose.

    关键: 有状态服务(如 Context7)会在 initialize 响应头里下发 `Mcp-Session-Id`,
    后续 tools/list、tools/call 必须带上, 否则 400 "No valid session ID provided".
    """
    url, headers = _endpoint_and_headers(rt)
    client = httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True)
    try:
        # 手动发 initialize 以便读响应头里的 session id.
        init_body = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "h-semas", "version": "13"},
            },
        }
        resp = await client.post(url, json=init_body, headers=headers)
        if resp.status_code >= 400:
            raise McpError(f"initialize HTTP {resp.status_code}: {resp.text[:200]}")
        obj = _parse_rpc_response(resp)
        if isinstance(obj, dict) and obj.get("error"):
            err = obj["error"]
            raise McpError(f"initialize RPC error: {err.get('message', err)}")
        # 捕获会话 id (大小写不敏感), 注入后续请求头.
        sid_hdr = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
        if sid_hdr:
            headers["Mcp-Session-Id"] = sid_hdr
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
    if _AUTH_STYLE.get(sid) == "stdio":
        from . import mcp_stdio
        return await mcp_stdio.list_tools(rt)
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
    if _AUTH_STYLE.get(server_id) == "stdio":
        from . import mcp_stdio
        return await mcp_stdio.call_tool(rt, tool_name, args)
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
    if server_id == "pubmed":
        return [{
            "name": "search_pubmed",
            "description": "检索 PubMed 权威医学文献. 参数 query=英文检索词(如 'metformin diabetes elderly'). 返回最相关的几篇标题/期刊/年份.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "英文检索词"}},
                "required": ["query"],
            },
        }]
    if server_id == "osm":
        return [
            {
                "name": "geocode_search",
                "description": "查海外地点/POI 的坐标与地址 (OpenStreetMap). 参数 query=地点名(如 'Tokyo Tower' / '東京駅').",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "地点名称"}},
                    "required": ["query"],
                },
            },
            {
                "name": "get_route",
                "description": "算两地之间的驾车路线距离与时长 (OpenStreetMap/OSRM). 参数 from=起点名, to=终点名.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string", "description": "起点地名"},
                        "to": {"type": "string", "description": "终点地名"},
                    },
                    "required": ["from", "to"],
                },
            },
        ]
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
    if server_id == "pubmed":
        q = str((args or {}).get("query") or (args or {}).get("term") or "").strip()
        if not q:
            raise McpError("pubmed: 缺少 query 参数")
        base = (rt.get("url") or "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/").strip().rstrip("/")
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            r1 = await client.get(f"{base}/esearch.fcgi",
                                  params={"db": "pubmed", "term": q, "retmax": 5, "retmode": "json"})
            if r1.status_code >= 400:
                raise McpError(f"PubMed esearch HTTP {r1.status_code}: {r1.text[:160]}")
            ids = (((r1.json() or {}).get("esearchresult") or {}).get("idlist")) or []
            if not ids:
                return f"PubMed 未检索到与「{q}」相关的文献"
            r2 = await client.get(f"{base}/esummary.fcgi",
                                  params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"})
            if r2.status_code >= 400:
                raise McpError(f"PubMed esummary HTTP {r2.status_code}: {r2.text[:160]}")
            res = (r2.json() or {}).get("result") or {}
        lines = [f"PubMed「{q}」相关文献:"]
        for pid in ids:
            it = res.get(pid) or {}
            title = it.get("title", "").strip().rstrip(".")
            journal = it.get("fulljournalname") or it.get("source") or ""
            year = (it.get("pubdate") or "")[:4]
            lines.append(f"- {title} ({journal}, {year}) PMID:{pid}")
        return "\n".join(lines)
    if server_id == "osm":
        return await _osm_call(tool_name, args, rt)
    raise McpError(f"未知 REST 服务: {server_id}")


# OpenStreetMap: Nominatim (地理编码) + OSRM (路线). 公共端点免 key, 但要求 User-Agent + 低频.
_OSM_UA = "h-semas/13 (personal travel advisor)"
_OSRM_BASE = "https://router.project-osrm.org"


async def _osm_geocode(client: httpx.AsyncClient, base: str, query: str) -> dict[str, Any] | None:
    r = await client.get(
        f"{base.rstrip('/')}/search",
        params={"q": query, "format": "json", "limit": 1, "addressdetails": 1},
        headers={"User-Agent": _OSM_UA},
    )
    if r.status_code >= 400:
        raise McpError(f"Nominatim HTTP {r.status_code}: {r.text[:120]}")
    arr = r.json()
    return arr[0] if isinstance(arr, list) and arr else None


async def _osm_call(tool_name: str, args: dict[str, Any], rt: dict[str, Any]) -> str:
    base = (rt.get("url") or "https://nominatim.openstreetmap.org").strip()
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        if tool_name == "geocode_search":
            q = str((args or {}).get("query") or "").strip()
            if not q:
                raise McpError("osm: 缺少 query")
            hit = await _osm_geocode(client, base, q)
            if not hit:
                return f"OpenStreetMap 未找到「{q}」"
            return (f"{q} → {hit.get('display_name', '')} "
                    f"(类型: {hit.get('type', '?')}, 坐标: {hit.get('lat')},{hit.get('lon')})")
        if tool_name == "get_route":
            a = str((args or {}).get("from") or "").strip()
            b = str((args or {}).get("to") or "").strip()
            if not a or not b:
                raise McpError("osm: 缺少 from/to")
            pa = await _osm_geocode(client, base, a)
            pb = await _osm_geocode(client, base, b)
            if not pa or not pb:
                return f"路线查询失败: {'起点' if not pa else '终点'}定位不到"
            coords = f"{pa['lon']},{pa['lat']};{pb['lon']},{pb['lat']}"
            r = await client.get(f"{_OSRM_BASE}/route/v1/driving/{coords}",
                                 params={"overview": "false"})
            if r.status_code >= 400:
                raise McpError(f"OSRM HTTP {r.status_code}: {r.text[:120]}")
            routes = (r.json() or {}).get("routes") or []
            if not routes:
                return f"{a} → {b}: 未找到驾车路线"
            dist_km = round(routes[0].get("distance", 0) / 1000, 1)
            dur_min = round(routes[0].get("duration", 0) / 60)
            return f"{a} → {b}: 驾车约 {dist_km} 公里, 约 {dur_min} 分钟"
        raise McpError(f"osm: 未知工具 {tool_name}")


# ---------- 配置页"测试连通"用 ----------
async def probe(server_id: str) -> dict[str, Any]:
    """测试某服务能否连通 + 拉到工具. 配置页"测试"按钮调用."""
    rt = mcp_tools.server_runtime(server_id)
    out: dict[str, Any] = {"id": server_id, "transport": rt.get("transport"), "ok": False}
    if rt.get("needs_key") and not rt.get("key"):
        out["error"] = "未填 Key"
        return out
    if rt.get("transport") == "http" and not rt.get("url"):
        out["error"] = "未填 URL"
        return out
    try:
        # stdio 首次会拉起 node 子进程, 给宽一点 (30s); http 走 25s.
        _timeout = 30.0 if rt.get("transport") == "stdio" else 25.0
        tools = await asyncio.wait_for(list_tools(server_id, force=True), timeout=_timeout)
        out["ok"] = True
        out["tool_count"] = len(tools)
        out["sample"] = [t.get("name") for t in tools[:8]]
    except asyncio.TimeoutError:
        out["error"] = "连接超时 (25s)"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return out
