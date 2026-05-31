"""ToolRegistry — 暴露给 LLM 的工具清单 + 调度执行 + 输出解析.

设计:
- 工具清单按白名单管理 (TOOL_REGISTRY), 每个工具有 schema + 安全等级 + handler
- LLM 在 dept JSON 输出里加 "tool_calls": [{"tool":"...", "args":{...}}]
- _run_dept 解析后调 execute_tool, 结果回灌到 raw_debate (并不二次过 LLM)
- 安全等级:
    safe=随便跑          (scrape/web_search/office:read-only/healthcheck/ocr/describe)
    sensitive=需 HITL    (screenshot/agent_task; office:email_send/desktop 由后端再拦)
    blocked=不开放给 LLM (永远不让 LLM 自动触发)
"""
from __future__ import annotations
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

from .seven_clients import bee_clients, ToolCallError

logger = logging.getLogger("bee.tools.registry")

SAFE = "safe"
SENSITIVE = "sensitive"
BLOCKED = "blocked"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_schema: dict[str, str]
    safety: str
    handler: Callable[[dict[str, Any]], dict[str, Any]]


def _h_scrape(args: dict) -> dict:
    return bee_clients.scrape(
        site=str(args.get("site", "")),
        keyword=str(args.get("keyword", "")),
        limit=int(args.get("limit", 20)),
    )


def _h_web_search(args: dict) -> dict:
    providers = args.get("providers") or None
    return bee_clients.web_search(
        query=str(args.get("query", "")),
        providers=providers if isinstance(providers, list) else None,
    )


def _h_office(args: dict) -> dict:
    return bee_clients.office(
        ability=str(args.get("ability", "")),
        spec=dict(args.get("spec") or {}),
    )


def _h_screenshot(args: dict) -> dict:
    return bee_clients.screenshot(
        monitor=int(args.get("monitor", 1)),
        bbox=args.get("bbox") if isinstance(args.get("bbox"), list) else None,
    )


def _h_ocr(args: dict) -> dict:
    return bee_clients.ocr(
        image_b64=str(args.get("image_b64", "")),
        engine=str(args.get("engine", "rapidocr")),
    )


def _h_describe(args: dict) -> dict:
    return bee_clients.describe(
        image_b64=str(args.get("image_b64", "")),
        question=str(args.get("question", "描述图片")),
        model=str(args.get("model", "")),
    )


def _h_agent_task(args: dict) -> dict:
    return bee_clients.agent_task(
        task=str(args.get("task", "")),
        workdir=str(args.get("workdir", "")),
        yolo_mode=False,
        model=str(args.get("model", "")),
    )


def _h_healthcheck(_: dict) -> dict:
    return {"services": bee_clients.healthcheck()}


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "scrape": ToolSpec(
        name="scrape",
        description="从指定站点抓数据 (hacker_news/arxiv/github_trending/huggingface/weibo_hot)",
        args_schema={"site": "站点 id", "keyword": "可选关键词", "limit": "数量 1-50"},
        safety=SAFE, handler=_h_scrape,
    ),
    "web_search": ToolSpec(
        name="web_search",
        description="多 provider Web 搜索 (tavily/brave/exa, 需对应 API Key)",
        args_schema={"query": "查询", "providers": "可选 provider 列表"},
        safety=SAFE, handler=_h_web_search,
    ),
    "office": ToolSpec(
        name="office",
        description="生成办公文件 (xlsx/docx/ppt/pdf/image_process)。email_send 等敏感能力需人工触发",
        args_schema={"ability": "能力 id", "spec": "对应 ability 的 spec 对象"},
        safety=SAFE, handler=_h_office,
    ),
    "screenshot": ToolSpec(
        name="screenshot",
        description="桌面截屏 (mss)",
        args_schema={"monitor": "显示器编号", "bbox": "可选 [x1,y1,x2,y2]"},
        safety=SENSITIVE, handler=_h_screenshot,
    ),
    "ocr": ToolSpec(
        name="ocr",
        description="OCR base64 图片 (rapidocr/paddleocr/claude-vision)",
        args_schema={"image_b64": "图片 base64", "engine": "ocr 引擎"},
        safety=SAFE, handler=_h_ocr,
    ),
    "describe": ToolSpec(
        name="describe",
        description="Claude/GPT 多模态描述图片",
        args_schema={"image_b64": "图片 base64", "question": "提问", "model": "可选模型"},
        safety=SAFE, handler=_h_describe,
    ),
    "agent_task": ToolSpec(
        name="agent_task",
        description="把任务派给 claude CLI 跑 (默认 plan 模式, 不动文件; 想真改文件需 HITL approve)",
        args_schema={"task": "任务描述", "workdir": "可选工作目录", "model": "可选模型"},
        safety=SENSITIVE, handler=_h_agent_task,
    ),
    "healthcheck": ToolSpec(
        name="healthcheck",
        description="查 6 个微服务的 /healthz",
        args_schema={},
        safety=SAFE, handler=_h_healthcheck,
    ),
}


def list_tools(include_sensitive: bool = False) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in TOOL_REGISTRY.values():
        if spec.safety == BLOCKED:
            continue
        if spec.safety == SENSITIVE and not include_sensitive:
            continue
        out.append({
            "name": spec.name,
            "description": spec.description,
            "args_schema": spec.args_schema,
            "safety": spec.safety,
        })
    return out


def execute_tool(name: str, args: dict[str, Any] | None,
                 allow_sensitive: bool = False) -> dict[str, Any]:
    spec = TOOL_REGISTRY.get(name)
    if not spec:
        return {"ok": False, "tool": name, "args": args or {},
                "error": f"unknown tool: {name}"}
    if spec.safety == BLOCKED:
        return {"ok": False, "tool": name, "args": args or {},
                "error": "tool blocked"}
    if spec.safety == SENSITIVE and not allow_sensitive:
        return {"ok": False, "tool": name, "args": args or {},
                "safety": spec.safety,
                "error": "sensitive tool requires user approval"}
    try:
        result = spec.handler(args or {})
        return {"ok": True, "tool": name, "args": args or {},
                "safety": spec.safety, "result": result}
    except ToolCallError as e:
        return {"ok": False, "tool": name, "args": args or {},
                "safety": spec.safety,
                "error": f"{e.service} HTTP {e.status}: {e.body}"}
    except Exception as e:
        logger.exception("tool %s failed", name)
        return {"ok": False, "tool": name, "args": args or {},
                "safety": spec.safety,
                "error": f"{type(e).__name__}: {e}"}


_TOOLS_JSON_RE = re.compile(
    r'"tool_calls"\s*:\s*(\[[\s\S]{2,5000}?\])', re.IGNORECASE,
)


def extract_tool_calls(llm_text: str) -> list[dict[str, Any]]:
    if not llm_text or '"tool_calls"' not in llm_text.lower():
        return []
    m = _TOOLS_JSON_RE.search(llm_text)
    if not m:
        return []
    try:
        arr = json.loads(m.group(1))
    except Exception:
        return []
    if not isinstance(arr, list):
        return []
    out: list[dict[str, Any]] = []
    for it in arr[:5]:
        if isinstance(it, dict) and isinstance(it.get("tool"), str):
            out.append({"tool": it["tool"], "args": it.get("args") or {}})
    return out
