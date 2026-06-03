"""BeeServiceClient — 七剑客统一 HTTP 客户端 (同步 httpx).

所有服务都走 Bearer 鉴权 (token 来自 BEE_BEARER_TOKEN 环境变量, 默认 dev-token-change-me).
默认 base URL 走 127.0.0.1; 可通过 BEE_{SCRAPER,HANDS,LIGHT,VISION,LEDGER,MEMORY}_URL 覆盖.
"""
from __future__ import annotations
import os
import logging
from typing import Any

import httpx

logger = logging.getLogger("bee.tools.seven_clients")

DEFAULT_TIMEOUT = float(os.environ.get("BEE_TOOL_TIMEOUT", "30"))


class ToolCallError(RuntimeError):
    """七剑客调用失败的统一异常 — 上层用 .service / .status / .body 取信息."""
    def __init__(self, service: str, status: int, body: str):
        self.service = service
        self.status = status
        self.body = body[:600]
        super().__init__(f"[{service}] HTTP {status}: {self.body}")


def _bearer() -> str:
    return os.environ.get("BEE_BEARER_TOKEN", "dev-token-change-me")


def _search_keys() -> dict[str, str]:
    """v9: 把 UI 里存的搜索 key (hub_settings.json → llm_rag_settings) 随请求带给爬虫,
    让用户在前端填一次即生效, 无需在爬虫容器单独配 env/.env。缺失则空 (爬虫退回自身 env)。"""
    out: dict[str, str] = {}
    try:
        from ..settings_llm_rag import llm_rag_settings as _s
        for field in ("tavily_api_key", "exa_api_key"):
            v = getattr(_s, field, None)
            if isinstance(v, str) and v.strip():
                out[field] = v.strip()
    except Exception:
        pass
    return out


class BeeServiceClient:
    """七剑客 HTTP client. 进程级单例 = bee_clients."""

    def __init__(self) -> None:
        self.scraper_url = os.environ.get("BEE_SCRAPER_URL", "http://127.0.0.1:8003")
        self.hands_url = os.environ.get("BEE_HANDS_URL", "http://127.0.0.1:8002")
        self.light_url = os.environ.get("BEE_LIGHT_URL", "http://127.0.0.1:8007")
        self.vision_url = os.environ.get("BEE_VISION_URL", "http://127.0.0.1:8006")
        self.input_url = os.environ.get("BEE_INPUT_URL", "http://127.0.0.1:8008")
        self.ledger_url = os.environ.get("BEE_LEDGER_URL", "http://127.0.0.1:8001")
        self.memory_url = os.environ.get("BEE_MEMORY_URL", "http://127.0.0.1:8004")
        self.timeout = DEFAULT_TIMEOUT

    def _post(self, service: str, base: str, path: str,
              json_body: dict[str, Any] | None = None,
              timeout: float | None = None) -> dict[str, Any]:
        url = f"{base.rstrip('/')}{path}"
        headers = {"Authorization": f"Bearer {_bearer()}"}
        try:
            with httpx.Client(timeout=timeout or self.timeout) as c:
                r = c.post(url, json=json_body or {}, headers=headers)
        except httpx.HTTPError as e:
            raise ToolCallError(service, 0, f"network: {e!r}") from e
        if r.status_code >= 400:
            raise ToolCallError(service, r.status_code, r.text)
        try:
            return r.json()
        except Exception:
            return {"raw": r.text[:2000]}

    def _get(self, service: str, base: str, path: str,
             params: dict[str, Any] | None = None,
             timeout: float | None = None) -> dict[str, Any]:
        url = f"{base.rstrip('/')}{path}"
        headers = {"Authorization": f"Bearer {_bearer()}"}
        try:
            with httpx.Client(timeout=timeout or self.timeout) as c:
                r = c.get(url, params=params or {}, headers=headers)
        except httpx.HTTPError as e:
            raise ToolCallError(service, 0, f"network: {e!r}") from e
        if r.status_code >= 400:
            raise ToolCallError(service, r.status_code, r.text)
        try:
            return r.json()
        except Exception:
            return {"raw": r.text[:2000]}

    # scraper (8003)
    def scrape(self, site: str, keyword: str = "", limit: int = 20) -> dict[str, Any]:
        return self._post("scraper", self.scraper_url, "/scraper/task",
                          {"site": site, "keyword": keyword, "limit": limit, **_search_keys()})

    def web_search(self, query: str,
                   providers: list[str] | None = None) -> dict[str, Any]:
        return self._post("scraper", self.scraper_url, "/scraper/search/query",
                          {"query": query, "providers": providers or [], **_search_keys()})

    # vision (8006)
    def ocr(self, image_b64: str, engine: str = "rapidocr") -> dict[str, Any]:
        return self._post("vision", self.vision_url, "/vision/ocr",
                          {"image_b64": image_b64, "engine": engine}, timeout=120)

    def screenshot(self, monitor: int = 1,
                   bbox: list[int] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"monitor": monitor}
        if bbox:
            body["bbox"] = bbox
        return self._post("vision", self.vision_url, "/vision/screenshot", body)

    def describe(self, image_b64: str, question: str = "描述图片",
                 model: str = "") -> dict[str, Any]:
        return self._post("vision", self.vision_url, "/vision/describe",
                          {"image_b64": image_b64, "question": question,
                           "model": model}, timeout=120)

    # light-exec (8007)
    def office(self, ability: str, spec: dict[str, Any]) -> dict[str, Any]:
        return self._post("light_exec", self.light_url, "/light_exec/run",
                          {"ability": ability, "spec": spec}, timeout=120)

    # agent-hands (8002)
    def agent_task(self, task: str, *, workdir: str = "",
                   yolo_mode: bool = False, model: str = "") -> dict[str, Any]:
        return self._post("agent_hands", self.hands_url, "/agent_hands/task",
                          {"task": task, "workdir": workdir,
                           "yolo_mode": yolo_mode, "model": model})

    def agent_status(self, task_id: str) -> dict[str, Any]:
        return self._get("agent_hands", self.hands_url,
                         f"/agent_hands/task/{task_id}")

    def agent_approve(self, task_id: str) -> dict[str, Any]:
        return self._post("agent_hands", self.hands_url,
                          f"/agent_hands/hitl/{task_id}/approve")

    def agent_exec(self, command: list[str], *, workdir: str = "", timeout: int = 180) -> dict[str, Any]:
        """白名单命令直执行 (跑测试 / git worktree): 开发模式用. claude shell 被拦时走这个."""
        return self._post("agent_hands", self.hands_url, "/agent_hands/exec",
                          {"command": command, "workdir": workdir, "timeout": timeout},
                          timeout=float(timeout) + 15)

    # input — 键鼠 (8008): 人类测试员模拟点击/移动/输入 (win32)
    def input_click(self, x: int, y: int, *, button: str = "left", double: bool = False) -> dict[str, Any]:
        return self._post("input", self.input_url, "/input/click",
                          {"x": int(x), "y": int(y), "button": button, "double": bool(double)})

    def input_move(self, x: int, y: int) -> dict[str, Any]:
        return self._post("input", self.input_url, "/input/move", {"x": int(x), "y": int(y)})

    def input_type(self, text: str) -> dict[str, Any]:
        return self._post("input", self.input_url, "/input/type", {"text": str(text)})

    # ledger (8001)
    def ledger_status(self) -> dict[str, Any]:
        return self._get("ledger", self.ledger_url, "/ledger/status")

    # memory (8004)
    def memory_recall(self, persona_id: str, query: str,
                      k: int = 8) -> dict[str, Any]:
        return self._post("memory", self.memory_url, "/memory/recall",
                          {"persona_id": persona_id, "query": query, "k": k})

    def healthcheck(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        targets = {
            "scraper": self.scraper_url, "hands": self.hands_url,
            "light": self.light_url, "vision": self.vision_url,
            "ledger": self.ledger_url, "memory": self.memory_url,
        }
        for name, base in targets.items():
            try:
                with httpx.Client(timeout=5) as c:
                    r = c.get(f"{base.rstrip('/')}/healthz")
                out[name] = {"ok": r.status_code == 200, "status": r.status_code}
            except Exception as e:
                out[name] = {"ok": False, "status": 0, "error": repr(e)[:200]}
        return out


bee_clients = BeeServiceClient()
