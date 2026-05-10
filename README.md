# H-SEMAS

Phase 1 goal: get an end-to-end runnable skeleton working:

- FastAPI backend
- **`/api/decision/start` → LangGraph** 主图（`triage` → `fanout` → `finalize`），与原先事件序（`dispatcher_ready` / `fanout_started` / `dept_done` / `decision_done`）一致；LiteLLM 路由仍由各科室 `_run_dept` 内完成
- WebSocket streaming events
- Simulated fan-out departments producing:
  - `confidence_score`
  - `dissent_intensity`
  - `debate_log_id`
- Mode switch (`mode_id`) with isolated persistence per mode

Next phases will replace more of the simulated parts with:

- Deeper LangGraph（按部门 Send / 检查点恢复等）
- Broader LiteLLM provider routing + fallbacks
- Qdrant RAG
- DSPy gene rewriting + shadow testing

## Verify (tests + frontend build)

From repo root:

- **Windows**: `npm run verify` or `.\scripts\verify.ps1`
- **Unix / macOS**: `npm run verify:unix` or `sh scripts/verify.sh` (requires `python` on PATH for `backend/tests`)

Runs backend `unittest`, then `frontend` **`npm run lint`** and **`npm run build`** (same order as CI).

**CI**: `.github/workflows/verify.yml` runs the same checks on Ubuntu (push / PR). **`workflow_dispatch`** allows manual runs in the Actions tab.

**Dependabot**: `.github/dependabot.yml` opens weekly PRs for `frontend/` npm, `backend/` pip, and GitHub Actions.

**Frontend**: use **Node 20+** (see `frontend/.nvmrc`). `package.json` **`overrides.postcss`** pins a patched PostCSS transitively pulled by Next until upstream bumps it (keeps `npm audit` clean without `audit fix --force`).

## Run (local dev)

### Backend

```bash
py -3.11 -m pip install -r backend/requirements.txt
py -3.11 -m uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Optional: copy `frontend/.env.example` to `frontend/.env.local` and set `NEXT_PUBLIC_BACKEND_URL` if the API is not on `http://127.0.0.1:8000` (REST + WebSocket derive from this URL).

Open `http://localhost:3000`.

### One-command (Windows PowerShell)

```powershell
.\scripts\dev.ps1
```

## Qdrant (Phase 2)

If you want `RAG_BACKEND=qdrant`, you must run Qdrant locally.

- If you have Docker: run `docker compose up -d qdrant` from this folder
- If you don't: use `RAG_BACKEND=local` (SQLite FTS, no Docker) or keep `RAG_BACKEND=simulated`

## Data isolation (important)

All state is namespaced by `mode_id` to prevent cross-domain “self-evolution pollution”:

- Decision history: `backend/data/<mode_id>/decisions.jsonl`
- Active genes: `backend/data/<mode_id>/genes/active/*.json`
- Shadow genes: `backend/data/<mode_id>/genes/shadow/<dept>/*.json`
- Shadow scores: `backend/data/<mode_id>/shadow_scores/<dept>/<shadow_version>.jsonl`

## Phase 3 (partial): outward search + execution bundle + optional CLI sandbox

- **Vision layer**: `benchmark` and `xlab` departments call Tavily (fallback Exa) when `BENCHMARK_WEB_SEARCH=true` and a search API key is set. Configure `TAVILY_API_KEY` / `EXA_API_KEY` in `.env` (see `.env.example`).
- **Decision output**: each run attaches `execution.qa_sandbox` (deterministic checks) and `execution.executor` (human-readable checklist). `execution.executor.suggested_cli_probe` mirrors allow-list settings with a **safe argv template** (e.g. `pytest --version`) — hints only, never auto-run. Persisted with decision summaries / WebSocket `decision_done`.
- **Optional subprocess sandbox** (`POST /api/sandbox/exec`): **disabled by default**. Enable only on trusted machines:
  - `HSEMAS_SANDBOX_EXEC_ENABLED=true`
  - `HSEMAS_EXEC_ALLOWLIST=python,pytest,ruff` — comma-separated **basename stems** (`.exe` stripped on Windows). Entries matching an internal deny-list (shells, `curl`, `npm`, `pip`, …) are rejected even if listed.
  - Working directory stays under `backend/` (`HSEMAS_EXEC_CWD` optional, relative to backend root).
  - Uses `asyncio.create_subprocess_exec` only — **never** `shell=True`.

`/api/status` reports `search` (API keys) and `sandbox_exec` (enabled / allowlist count / cwd).

### Decision history API

- `GET /api/memory/{mode_id}?limit=50&compact=1` — list recent decisions; **`compact=1`** drops `dept_reports` bodies, slims `heatmap` / `execution`, and **truncates** long `task` / `ceo_decision` (see `task_truncated` / `ceo_decision_truncated` flags).
- `GET /api/memory/{mode_id}/decision/{decision_id}` — **full** persisted summary (same shape as WebSocket `decision_done`), used by the UI after picking a compact history row.

**Tests** (from `backend/`): `python -m unittest discover -s tests -v` — includes Memory API integration (`tests/test_memory_api.py`, writes then deletes `backend/data/__test_memory_api__/`)
