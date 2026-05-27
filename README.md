# H-SEMAS

## Phase 1（骨架）

- FastAPI backend + **`/api/decision/start` → LangGraph**（`triage` → 按部门 **Send** 并行 → `defer` **finalize**）
- WebSocket：`dispatcher_ready` / `fanout_started` / `dept_done` / `decision_done`
- 科室产出：`confidence_score`、`dissent_intensity`、`debate_log_id`
- **`mode_id`** 隔离：`backend/data/<mode_id>/…`

## Phase 2（已闭环）

- **编排**：LangGraph 并行扇出；可选 **checkpoint** — `memory`（默认）或 **`sqlite`**（`AsyncSqliteSaver` + `aiosqlite`，见 `HSEMAS_GRAPH_CHECKPOINT_*`）
- **RAG**：`RAG_BACKEND=simulated | local | qdrant`；**local** = SQLite FTS5；**qdrant** = 向量检索 + 可选 **`RAG_HYBRID_LOCAL_FTS`** 与本地 FTS 合并；失败时回退可读占位 chunk
- **嵌入**：Qdrant 路径下 **hash 向量**（默认可复现）或 **LiteLLM 文本嵌入**（配置 `LITELLM_EMBEDDING_MODEL` + 任一 LLM 供应商 Key）
- **LLM**：`LLM_PROVIDER=simulated | litellm`，科室内 **LiteLLM** 调用 + **fallback 模型链**
- **可观测**：`DecisionSummary.rag_aggregate`、科室 `rag_retrieval_meta`；`/api/status` 报告 RAG / 嵌入 / hybrid / checkpoint，并含 **`roadmap`**（`phase2`–`phase5` 里程碑）；可选 **`GET /api/debug/graph-state/{id}`**
- **API**：`POST/GET /api/rag/ingest|search/{mode_id}`；`GET /api/memory/...` compact 含 **`rag_hint`**

## Phase 3（已闭环）

- **视野外搜**：`benchmark` / `xlab` 在 `BENCHMARK_WEB_SEARCH=true` 且配置了 **`TAVILY_API_KEY`** 或 **`EXA_API_KEY`** 时，经 `fetch_benchmark_web_chunks` 拉取网页片段，与 RAG 合并后注入提示词（`decision_engine._run_dept`）
- **执行包**：每次决策附带 **`execution.qa_sandbox`**（确定性硬门槛 / 软告警，无子进程）与 **`execution.executor`**（结构化清单）；**`suggested_cli_probe`** 仅生成安全 argv 模板，不自动执行
- **CLI 沙盒**：`POST /api/sandbox/exec` — `HSEMAS_SANDBOX_EXEC_ENABLED` + **`HSEMAS_EXEC_ALLOWLIST`** 白名单、`asyncio.create_subprocess_exec`、**禁止 shell**
- **状态**：`/api/status` 的 **`search`**（外搜 Key）、**`sandbox_exec`**（沙盒就绪度）与 **`roadmap.phase3: shipped`**

## Phase 4（已闭环）

- **YAML 垂直场景**：`backend/scenarios/{mode_id}.yaml` 可选覆盖 `label`、`department_labels`、`scenario_description`、`default_task_hint`、`gene_seeds`；`GET /api/modes` 返回合并后的 `ModeInfo`（含 `scenario_yaml` 文件名标记）。仓库内已为四个内置 `mode_id` 各提供示例 YAML
- **基因种子**：无磁盘 Active 基因时，`build_initial_gene_prompt` 将对应部门的 `gene_seeds` 段落并入默认 prompt（决策管线与 `GET /api/genes/...` 首次落盘一致）
- **DSPy 风格进化**：`POST /api/genes/{mode_id}/{dept}/evolve` — LiteLLM 下用独立 system 角色做 meta-prompt；`simulated` 下返回确定性 stub；可选 `save_shadow: true` 写入新版本供 Shadow A/B
- **可观测**：`/api/status` 的 **`scenario_templates`**（目录与 `*.yaml` 列表）与 **`roadmap.phase4: shipped`**

## Phase 5（已闭环）

- **YAML 全量注册模式**：在 **`backend/scenarios/extra/*.yaml`** 声明完整 `mode_id` / `label` / `departments` / `department_labels` 等（`departments` 必须为 `app.models.DeptName` 中已有槽位），无需改 **`app/modes.py`** 的 `MODES` 表即可出现在 **`GET /api/modes`** 与决策链路中
- **双层 YAML**：同一 `mode_id` 仍可叠加根目录 **`backend/scenarios/{mode_id}.yaml`**（与 Phase 4 一致）；`gene_seeds` 与 extra 文件合并而非整表覆盖
- **示例**：`generic_consulting`（`scenarios/extra/generic_consulting.yaml` + 可选 `scenarios/generic_consulting.yaml`）
- **可观测**：`/api/status.scenario_templates` 增加 **`extra_modes_dir`**、**`extra_mode_yaml_files`**、**`extra_mode_ids`**；**`modes_reload.enabled`** 反映是否开放 **`POST /api/modes/reload`**；**`roadmap.phase5: shipped`**
- **热重载（可选）**：`HSEMAS_MODES_YAML_RELOAD_ENABLED=true` 时允许 **`POST /api/modes/reload`** 清空 extra 模式内存缓存并重新扫描 `scenarios/extra`（仅信任环境）
- **解析探测**：**`GET /api/modes/lookup/{mode_id}`** 返回 `registry`（`builtin` / `extra` / `fallback`）与合并后的 `mode`，便于排查拼写错误与回退行为

## Phase 6（已闭环）

- **部门槽位目录**：`GET /api/catalog/dept-names` 返回可用于 `scenarios/extra/*.yaml` 的 `departments` 枚举列表
- **严格 mode 校验（可选）**：`POST /api/decision/start` 支持 `reject_unknown_mode: true`，未知 `mode_id` 返回 422（便于排查拼写 / 缺 YAML 注册导致的静默回退）

## Phase 7（已闭环）

- **YAML 校验器**：`POST /api/scenarios/validate` 支持校验两类 YAML 结构：`kind=root_overlay | extra_mode`，返回 `errors`/`warnings` 与 `normalized`（不写盘）
- **YAML 脚手架**：`POST /api/scenarios/scaffold` 生成新 extra 模式的起始 YAML（字符串），便于快速复制到 `backend/scenarios/extra/`

## Phase 8（已闭环）

- **前端作者面板**：在首页底部提供 YAML 编辑区：一键 scaffold、一键 validate、显示 errors/warnings 与 normalized，并可拉取 `DeptName` 枚举（`/api/catalog/dept-names`）

## Phase 9（已闭环）

- **写盘/落地**：`HSEMAS_SCENARIO_WRITE_ENABLED=true` 时开放 `POST /api/scenarios/write`，校验并写入 `backend/scenarios/` 或 `backend/scenarios/extra/`；可选联动 `POST /api/modes/reload`
- **历史快照**：每次写入会在 `backend/scenarios/_history/{mode_id}/` 保存 before/after 快照并写 JSONL 日志

## Phase 10（已闭环）

- **历史查询**：`GET /api/scenarios/history/{mode_id}`
- **回滚**：`POST /api/scenarios/rollback`（同样受写盘开关保护）

## Phase 11（已闭环）

- **质量门槛**：`POST /api/genes/.../evolve` 支持 `require_gate`，用最近任务样本计算改写前后 delta 的 95% 下界（lb95）决定是否允许落 shadow
- **更严格晋升**：shadow 晋升改为按 taskset 的 lb95 判定（并记录 task_hash/decision_id）

## Phase 12（已闭环）

- **产品化 UI**：新增 3 档视图（用户/高级/工程）；用户视图聚焦“模式、任务、结果、历史”，工程细节默认隐藏；结果区增加 Top 3 建议与 RedTeam 风险块，支持一键填入默认任务提示

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

## Run (Docker Compose)

在仓库根目录：

```bash
docker compose up -d --build
```

- Frontend: `http://localhost:3000`
- Backend: `http://127.0.0.1:8000/api/health`
- Qdrant: `http://127.0.0.1:6333`

## Package (B2: single backend serves UI)

Windows:

- Run `.\scripts\package-b2.ps1`
- Output: `backend/dist/h-semas.exe`

Notes:
- This bundles the **exported** frontend into `backend/app/static_ui` and mounts it at `/`.
- API remains under `/api/*`.
- Run exe with optional env: `HSEMAS_HOST=127.0.0.1` `HSEMAS_PORT=8000`.

## Qdrant（Phase 2 可选）

`RAG_BACKEND=qdrant` 时需要本机 Qdrant：

- Docker：仓库根目录 `docker compose up -d qdrant`
- 无 Docker：`RAG_BACKEND=local`（SQLite FTS）或 `simulated`

## Data isolation (important)

All state is namespaced by `mode_id` to prevent cross-domain “self-evolution pollution”:

- Decision history: `backend/data/<mode_id>/decisions.jsonl`
- Active genes: `backend/data/<mode_id>/genes/active/*.json`
- Shadow genes: `backend/data/<mode_id>/genes/shadow/<dept>/*.json`
- Shadow scores: `backend/data/<mode_id>/shadow_scores/<dept>/<shadow_version>.jsonl`

### Phase 3 env quick ref（英文）

- `BENCHMARK_WEB_SEARCH`, `TAVILY_API_KEY`, `EXA_API_KEY`
- `HSEMAS_SANDBOX_EXEC_ENABLED`, `HSEMAS_EXEC_ALLOWLIST`, `HSEMAS_EXEC_CWD`, …（见 `.env.example`）

### Decision history API

- `GET /api/memory/{mode_id}?limit=50&compact=1` — list recent decisions; **`compact=1`** drops `dept_reports` bodies, slims `heatmap` / `execution`, and **truncates** long `task` / `ceo_decision` (see `task_truncated` / `ceo_decision_truncated` flags).
- `GET /api/memory/{mode_id}/decision/{decision_id}` — **full** persisted summary (same shape as WebSocket `decision_done`), used by the UI after picking a compact history row.

**Tests** (from `backend/`): `python -m unittest discover -s tests -v` — includes Memory API integration (`tests/test_memory_api.py`, writes then deletes `backend/data/__test_memory_api__/`)
