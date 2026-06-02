"""mcp_stdio — v13 #1 第②步补充: stdio 类 MCP 服务的子进程传输.

Airbnb / Google Maps 这类 MCP 服务不是 HTTP 端点, 而是要在本机起一个 node 子进程,
用 stdin/stdout 跑 JSON-RPC (MCP stdio transport: 每条消息一行 JSON, 换行分隔)。

性能纪律 (防卡):
- 仅在旅行类场景白名单内才会被 mcp_orchestrator 取用; 平时根本不启动.
- 子进程包在镜像里预装好 (Dockerfile npm -g), 运行时不联网下载.
- 单次操作硬超时 _OP_TIMEOUT 秒; 超时/出错立即 terminate→kill, 不留僵尸进程.
- 每次操作 spawn→用完即杀, 无常驻进程; NAS 空闲零负担.

对外: list_tools(rt) / call_tool(rt, name, args). rt = mcp_tools.server_runtime(id).
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

_OP_TIMEOUT = 12.0          # 单次 stdio 操作硬超时 (秒)
_PROTOCOL_VERSION = "2025-06-18"


class StdioError(Exception):
    pass


# server_id -> 启动命令 + 需要注入的环境变量 (key 从 runtime 拿).
# 包已在 backend/Dockerfile 里 npm -g 预装; npx -y 命中本地副本, 不联网.
STDIO_SERVERS: dict[str, dict[str, Any]] = {
    "airbnb": {
        "cmd": ["npx", "-y", "@openbnb/mcp-server-airbnb", "--ignore-robots-txt"],
        "env_key": None,  # 免 key
    },
    # 注: Google Maps 因需境外信用卡, 已替换为 OpenStreetMap(REST, 见 mcp_client._osm_call)
}


def is_stdio(server_id: str) -> bool:
    return server_id in STDIO_SERVERS


def _content_to_text(result: Any) -> str:
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            parts = [str(b["text"]) for b in content if isinstance(b, dict) and b.get("text")]
            if parts:
                return "\n".join(parts)
        if result.get("structuredContent") is not None:
            return json.dumps(result["structuredContent"], ensure_ascii=False)[:4000]
    return json.dumps(result, ensure_ascii=False)[:4000]


async def _spawn(rt: dict[str, Any]) -> asyncio.subprocess.Process:
    sid = rt.get("id", "")
    spec = STDIO_SERVERS.get(sid)
    if not spec:
        raise StdioError(f"{sid}: 非 stdio 服务")
    env = dict(os.environ)
    env_key = spec.get("env_key")
    if env_key:
        key = (rt.get("key") or "").strip()
        if not key:
            raise StdioError(f"{sid}: 缺少 API Key")
        env[env_key] = key
    try:
        proc = await asyncio.create_subprocess_exec(
            *spec["cmd"],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,  # 服务日志丢弃, 防 stderr 写满阻塞
            env=env,
        )
    except FileNotFoundError as e:
        raise StdioError(f"{sid}: 找不到 node/npx (容器未装 Node?) — {e}") from e
    return proc


async def _send(proc: asyncio.subprocess.Process, msg: dict[str, Any]) -> None:
    assert proc.stdin is not None
    proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
    await proc.stdin.drain()


async def _read_reply(proc: asyncio.subprocess.Process, target_id: int) -> dict[str, Any]:
    """读到 id 匹配且带 result/error 的那条; 跳过通知/日志行."""
    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            raise StdioError("子进程提前退出 (无输出)")
        s = line.decode("utf-8", errors="replace").strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue  # 非 JSON 日志行
        if isinstance(obj, dict) and obj.get("id") == target_id and ("result" in obj or "error" in obj):
            if obj.get("error"):
                raise StdioError(f"RPC error: {obj['error'].get('message', obj['error'])}")
            return obj


async def _handshake(proc: asyncio.subprocess.Process) -> None:
    await _send(proc, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": _PROTOCOL_VERSION, "capabilities": {},
                   "clientInfo": {"name": "h-semas", "version": "13"}},
    })
    await _read_reply(proc, 1)
    await _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})


async def _kill(proc: asyncio.subprocess.Process) -> None:
    """确保子进程被回收, 绝不留僵尸 (否则 NAS 越用越卡)."""
    try:
        if proc.stdin and not proc.stdin.is_closing():
            proc.stdin.close()
    except Exception:
        pass
    if proc.returncode is None:
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


async def _with_proc(rt: dict[str, Any], body):
    """spawn → 跑 body(proc) → 无论如何都 kill. 整体硬超时 _OP_TIMEOUT."""
    proc = await _spawn(rt)
    try:
        return await asyncio.wait_for(body(proc), timeout=_OP_TIMEOUT)
    finally:
        await _kill(proc)


async def list_tools(rt: dict[str, Any]) -> list[dict[str, Any]]:
    async def body(proc: asyncio.subprocess.Process) -> list[dict[str, Any]]:
        await _handshake(proc)
        await _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        obj = await _read_reply(proc, 2)
        tools = ((obj.get("result") or {}).get("tools")) or []
        out: list[dict[str, Any]] = []
        for t in tools:
            if isinstance(t, dict) and t.get("name"):
                out.append({
                    "name": t["name"],
                    "description": (t.get("description") or "")[:300],
                    "input_schema": t.get("inputSchema") or t.get("input_schema") or {},
                })
        return out
    return await _with_proc(rt, body)


async def call_tool(rt: dict[str, Any], tool_name: str, args: dict[str, Any]) -> str:
    async def body(proc: asyncio.subprocess.Process) -> str:
        await _handshake(proc)
        await _send(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": tool_name, "arguments": args or {}}})
        obj = await _read_reply(proc, 3)
        return _content_to_text(obj.get("result"))
    return await _with_proc(rt, body)
