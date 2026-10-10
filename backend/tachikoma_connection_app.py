"""Minimal swarm identity; deliberately does not import the H-SEMAS app."""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

BACKEND_ROOT = Path(__file__).resolve().parent
SAFE_PATHS = {"/api/health", "/tachikoma/v1/contract"}
app = FastAPI(title="H-SEMAS Tachikoma Connection", docs_url=None, redoc_url=None)


@app.middleware("http")
async def connection_guard(request: Request, call_next):
    if request.method == "GET" and request.url.path in SAFE_PATHS:
        return await call_next(request)
    return JSONResponse(status_code=403, content={
        "code": "PRODUCTION_EXECUTION_DISABLED", "service": "ai-swarm", "mode": "connection_only",
    })


def identity_payload() -> dict:
    return {
        "status": "ok", "service": "ai-swarm", "version": "dev",
        "contract_version": "v1", "ready": True, "dependencies_ready": False,
        "mode": "connection_only", "production_execution_enabled": False,
        "business_entrypoint_present": (BACKEND_ROOT / "app" / "main.py").is_file(),
        "scheduler_started": False,
        "dependency_reason": "decision engine, model providers and scheduler are intentionally not started",
    }


@app.get("/api/health")
def health() -> dict:
    return identity_payload()


@app.get("/tachikoma/v1/contract")
def contract() -> dict:
    return {
        "schema_version": "tachikoma-connection/v1", "software_id": "ai-swarm",
        "service": "ai-swarm", "production_execution_enabled": False,
        "upgrade_execution_enabled": False,
        "business_actions": [{
            "chain_id": "software-delivery-chain", "step": "coordinate",
            "method": "POST", "path": "/api/tools/call", "risk": "reversible_write",
            "approval": "project_review", "idempotency": "required",
            "status": "target_port_reserved_project_change_required", "execution_enabled": False,
        }],
    }
