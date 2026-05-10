"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { httpToWsOrigin, resolveBackendHttpBase } from "../lib/backend";
import { fetchWithTimeout, TIMEOUT_MS } from "../lib/http";

type StreamEvent = {
  type: string;
  decision_id: string;
  payload: Record<string, unknown>;
};

type ModeInfo = {
  mode_id: string;
  label: string;
  departments: string[];
  department_labels?: Record<string, string>;
};

type DeptReport = {
  dept?: string;
  consensus?: string;
  conflicts?: string[];
  credibility_weight?: number;
  confidence_score?: number;
  dissent_intensity?: number;
  debate_log_id?: string;
  dispatcher_context?: string;
  rag_context?: unknown[];
  raw_debate?: { role?: string; content?: string }[];
};

type DecisionSummary = {
  decision_id?: string;
  task?: string;
  created_at?: string;
  mode_id?: string;
  mode_label?: string;
  heatmap?: { dept?: string; confidence_score?: number; dissent_intensity?: number; alert?: string; debate_log_id?: string }[];
  dept_reports?: DeptReport[];
  ceo_decision?: string;
  red_team_risks?: string[];
  dispatcher?: Record<string, unknown>;
  execution?: {
    qa_sandbox?: { ok?: boolean; sandbox?: string; [key: string]: unknown };
    executor?: Record<string, unknown>;
    [key: string]: unknown;
  };
  dept_reports_preview?: { count?: number; depts?: string[] };
  /** Present when loaded from GET .../memory?compact=1 — click row to fetch full summary */
  _compact?: boolean;
  task_truncated?: boolean;
  ceo_decision_truncated?: boolean;
};

type GeneRecord = {
  dept?: string;
  version?: number;
  prompt?: string;
  created_at?: string;
  status?: string;
};

type ShadowStatus = {
  verdict?: { promote?: boolean; reason?: string; shadow_version?: number };
  scores?: { ts?: string; score_active?: number; score_shadow?: number; delta?: number }[];
};

type ModeConfig = {
  mode_id?: string;
  updated_at?: string | null;
  trusted_sources?: Record<string, number>;
};

type BackendStatusPayload = {
  llm?: { provider?: string; ok?: boolean; detail?: string; default_model?: string };
  rag?: { backend?: string; ok?: boolean; detail?: string; qdrant_url?: string };
  search?: {
    benchmark_web_search_enabled?: boolean;
    tavily_configured?: boolean;
    exa_configured?: boolean;
    ok?: boolean;
    detail?: string;
  };
  sandbox_exec?: {
    enabled?: boolean;
    ok?: boolean;
    detail?: string;
    allowlist_count?: number;
    exec_cwd?: string;
    cwd_resolution_note?: string | null;
    timeout_sec?: number;
  };
};

function pretty(obj: unknown) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

export default function HomePage() {
  const backendBase = useMemo(() => resolveBackendHttpBase(), []);
  const [task, setTask] = useState("测试：做一个Phase1 MVP");
  const [modes, setModes] = useState<ModeInfo[]>([]);
  const [modeId, setModeId] = useState("program_management");
  const [decisionId, setDecisionId] = useState<string>("");
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [history, setHistory] = useState<DecisionSummary[]>([]);
  const [latestSummary, setLatestSummary] = useState<DecisionSummary | null>(null);
  const [openDept, setOpenDept] = useState<string>("");
  const [deptId, setDeptId] = useState<string>("finance");
  const [gene, setGene] = useState<GeneRecord | null>(null);
  const [genePrompt, setGenePrompt] = useState<string>("");
  const [shadows, setShadows] = useState<GeneRecord[]>([]);
  const [shadowStatus, setShadowStatus] = useState<ShadowStatus | null>(null);
  const [modeConfig, setModeConfig] = useState<ModeConfig | null>(null);
  const [trustedSourcesText, setTrustedSourcesText] = useState<string>("");
  const [backendStatus, setBackendStatus] = useState<BackendStatusPayload | null>(null);
  const [ragText, setRagText] = useState<string>(
    "chunk_id:demo-001\ntitle:示例资料\ncontent:这是一个示例知识片段，用于测试 RAG ingest/search。\nsource_url:https://github.com/example/repo\n",
  );
  const [ragQuery, setRagQuery] = useState<string>("示例");
  const [ragResults, setRagResults] = useState<any[]>([]);
  const [ragLastIngest, setRagLastIngest] = useState<any>(null);
  /** JSON array argv for POST /api/sandbox/exec (each element becomes one argv token; no shell) */
  const [sandboxArgvJson, setSandboxArgvJson] = useState<string>('["python", "-V"]');
  const [sandboxExecResult, setSandboxExecResult] = useState<unknown>(null);
  const [historyLoadingId, setHistoryLoadingId] = useState<string | null>(null);
  const [historyFetchError, setHistoryFetchError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const deptLabels = useMemo(() => {
    return modes.find((m) => m.mode_id === modeId)?.department_labels || {};
  }, [modes, modeId]);

  useEffect(() => {
    // auto-load modes once
    loadModes().catch(() => {});
    loadBackendStatus().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setHistoryFetchError(null);
    loadHistory().catch(() => {});
    loadModeConfig().catch(() => {});
    const m = modes.find((x) => x.mode_id === modeId);
    const firstDept = m?.departments?.[0];
    if (firstDept) setDeptId(firstDept);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modeId]);

  useEffect(() => {
    loadGene().catch(() => {});
    loadShadows().catch(() => {});
    setShadowStatus(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modeId, deptId]);

  async function loadModes() {
    const res = await fetchWithTimeout(`${backendBase}/api/modes`);
    const data = (await res.json()) as ModeInfo[];
    setModes(data);
    if (!data.find((m) => m.mode_id === modeId) && data[0]) {
      setModeId(data[0].mode_id);
    }
  }

  async function loadBackendStatus() {
    const res = await fetchWithTimeout(`${backendBase}/api/status`);
    setBackendStatus((await res.json()) as BackendStatusPayload);
  }

  async function runSandboxExec() {
    let argv: string[];
    try {
      const parsed = JSON.parse(sandboxArgvJson) as unknown;
      if (!Array.isArray(parsed) || parsed.some((x) => typeof x !== "string")) {
        throw new Error("shape");
      }
      argv = parsed;
    } catch {
      setSandboxExecResult({ error: "invalid_json_argv", hint: 'expected JSON array of strings, e.g. ["pytest","--version"]' });
      return;
    }
    const res = await fetchWithTimeout(
      `${backendBase}/api/sandbox/exec`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ argv }),
      },
      TIMEOUT_MS.sandboxExec,
    );
    const raw = await res.text();
    let body: unknown = {};
    try {
      body = raw ? JSON.parse(raw) : {};
    } catch {
      body = { parse_error: true, raw };
    }
    const merged =
      typeof body === "object" && body !== null && !Array.isArray(body)
        ? { ...(body as Record<string, unknown>), http_status: res.status }
        : { payload: body, http_status: res.status };
    setSandboxExecResult(merged);
    await loadBackendStatus();
  }

  async function ragIngest() {
    // very small parser: blocks separated by blank lines; each block has key:value
    const blocks = ragText.split(/\n\s*\n/g).map((b) => b.trim()).filter(Boolean);
    const items = blocks.map((b) => {
      const obj: any = {};
      for (const line of b.split("\n")) {
        const idx = line.indexOf(":");
        if (idx <= 0) continue;
        const k = line.slice(0, idx).trim();
        const v = line.slice(idx + 1).trim();
        obj[k] = v;
      }
      return {
        chunk_id: obj.chunk_id || `chunk-${Date.now()}`,
        title: obj.title || "untitled",
        content: obj.content || "",
        source_url: obj.source_url || "",
        meta: { from: "ui" },
      };
    });
    const res = await fetchWithTimeout(
      `${backendBase}/api/rag/ingest/${encodeURIComponent(modeId)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      },
      TIMEOUT_MS.ingest,
    );
    const data = await res.json();
    setRagLastIngest(data);
    setEvents((xs) => [
      ...xs,
      { type: "ui.rag_ingest", decision_id: decisionId || "ui", payload: { mode_id: modeId, response: data } },
    ]);
  }

  async function ragSearch() {
    const res = await fetchWithTimeout(
      `${backendBase}/api/rag/search/${encodeURIComponent(modeId)}?q=${encodeURIComponent(ragQuery)}&k=5&dept=${encodeURIComponent(
        deptId,
      )}`,
    );
    setRagResults(await res.json());
  }

  async function loadHistory() {
    setHistoryFetchError(null);
    try {
      const res = await fetchWithTimeout(`${backendBase}/api/memory/${encodeURIComponent(modeId)}?limit=20&compact=1`);
      if (!res.ok) {
        setHistoryFetchError(`刷新历史列表失败（HTTP ${res.status}）`);
        return;
      }
      const data = (await res.json()) as DecisionSummary[];
      setHistory(data.reverse()); // newest first
    } catch (e) {
      const aborted = e instanceof DOMException && e.name === "AbortError";
      const abortedLegacy = e instanceof Error && e.name === "AbortError";
      if (aborted || abortedLegacy) {
        setHistoryFetchError("刷新历史超时（20s），后端可能未启动或阻塞");
      } else {
        setHistoryFetchError("无法连接后端，历史列表未更新");
      }
    }
  }

  async function openHistoryDetail(h: DecisionSummary) {
    const id = h.decision_id || "";
    setOpenDept("");
    setHistoryFetchError(null);
    if (!id) {
      setLatestSummary(h);
      return;
    }
    setHistoryLoadingId(id);
    try {
      const res = await fetchWithTimeout(`${backendBase}/api/memory/${encodeURIComponent(modeId)}/decision/${encodeURIComponent(id)}`);
      if (!res.ok) {
        setHistoryFetchError(
          res.status === 404 ? "未找到完整决策记录（404），可能文件未写入或 ID 不一致" : `加载全文失败（HTTP ${res.status}）`,
        );
        setLatestSummary(h);
        return;
      }
      setLatestSummary((await res.json()) as DecisionSummary);
    } catch (e) {
      const aborted = e instanceof DOMException && e.name === "AbortError";
      const abortedLegacy = e instanceof Error && e.name === "AbortError";
      if (aborted || abortedLegacy) {
        setHistoryFetchError("加载全文超时（20s），已暂时显示列表节选");
      } else {
        setHistoryFetchError("无法连接后端，已暂时显示列表中的节选内容");
      }
      setLatestSummary(h);
    } finally {
      setHistoryLoadingId(null);
    }
  }

  async function loadModeConfig() {
    const res = await fetchWithTimeout(`${backendBase}/api/config/${encodeURIComponent(modeId)}`);
    const data = (await res.json()) as ModeConfig;
    setModeConfig(data);
    setTrustedSourcesText(pretty(data.trusted_sources || {}));
  }

  async function saveModeConfig() {
    let trusted: Record<string, number> = {};
    try {
      const parsed = JSON.parse(trustedSourcesText || "{}");
      if (parsed && typeof parsed === "object") trusted = parsed;
    } catch {
      // ignore parse error; backend will get empty object
    }
    const res = await fetchWithTimeout(`${backendBase}/api/config/${encodeURIComponent(modeId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...modeConfig, trusted_sources: trusted }),
    });
    const data = (await res.json()) as ModeConfig;
    setModeConfig(data);
  }

  async function loadGene() {
    const res = await fetchWithTimeout(`${backendBase}/api/genes/${encodeURIComponent(modeId)}/${encodeURIComponent(deptId)}`);
    const data = (await res.json()) as GeneRecord;
    setGene(data);
    setGenePrompt(String(data.prompt || ""));
  }

  async function loadShadows() {
    const res = await fetchWithTimeout(
      `${backendBase}/api/genes/${encodeURIComponent(modeId)}/${encodeURIComponent(deptId)}/shadow?limit=10`,
    );
    const data = (await res.json()) as GeneRecord[];
    setShadows(data);
  }

  async function loadShadowStatus(shadowVersion: number) {
    const res = await fetchWithTimeout(
      `${backendBase}/api/shadow/${encodeURIComponent(modeId)}/${encodeURIComponent(deptId)}/${encodeURIComponent(
        String(shadowVersion),
      )}?trials=3`,
    );
    const data = (await res.json()) as ShadowStatus;
    setShadowStatus(data);
  }

  async function saveGene() {
    const res = await fetchWithTimeout(`${backendBase}/api/genes/${encodeURIComponent(modeId)}/${encodeURIComponent(deptId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: genePrompt }),
    });
    const data = (await res.json()) as GeneRecord;
    setGene(data);
  }

  async function saveShadow() {
    await fetchWithTimeout(`${backendBase}/api/genes/${encodeURIComponent(modeId)}/${encodeURIComponent(deptId)}/shadow`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: genePrompt }),
    });
    await loadShadows();
  }

  async function start() {
    setEvents([]);
    setDecisionId("");
    setLatestSummary(null);
    setOpenDept("");

    const res = await fetchWithTimeout(
      `${backendBase}/api/decision/start`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task, mode_id: modeId }),
      },
      TIMEOUT_MS.decisionStart,
    );
    const data = (await res.json()) as { decision_id: string };
    setDecisionId(data.decision_id);

    wsRef.current?.close();
    const ws = new WebSocket(`${httpToWsOrigin(backendBase)}/api/decision/stream/${data.decision_id}`);
    wsRef.current = ws;
    ws.onmessage = (msg) => {
      try {
        const evt = JSON.parse(msg.data) as StreamEvent;
        setEvents((prev) => [...prev, evt]);
        if (evt.type === "decision_done") {
          loadHistory().catch(() => {});
          const summary = (evt.payload as any)?.summary as DecisionSummary | undefined;
          if (summary) setLatestSummary(summary);
        }
      } catch {
        // ignore
      }
    };
  }

  return (
    <div style={{ padding: 20, maxWidth: 1100, margin: "0 auto" }}>
      <h1 style={{ marginTop: 0 }}>H-SEMAS Phase 1</h1>
      <p style={{ marginTop: 6, color: "#444" }}>
        当前是最小可运行骨架：后端模拟 7 个部门并行产出，按 WebSocket 流式推送事件。
      </p>
      {backendStatus ? (
        <div style={{ marginTop: 10, padding: 10, border: "1px solid #eee", borderRadius: 10, background: "#fff" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
            <div style={{ fontWeight: 700 }}>后端状态</div>
            <button
              onClick={loadBackendStatus}
              style={{ padding: "6px 10px", borderRadius: 10, border: "1px solid #bbb", background: "#fff", cursor: "pointer", fontSize: 12 }}
            >
              刷新状态
            </button>
          </div>
          <div style={{ marginTop: 6, fontSize: 12, color: "#333" }}>
            LLM: {backendStatus.llm?.provider} / {backendStatus.llm?.ok ? "ok" : "not-ready"} / {backendStatus.llm?.detail}
          </div>
          <div style={{ marginTop: 4, fontSize: 12, color: "#333" }}>
            RAG: {backendStatus.rag?.backend} / {backendStatus.rag?.ok ? "ok" : "not-ready"} / {backendStatus.rag?.detail}
          </div>
          {backendStatus.search ? (
            <div style={{ marginTop: 4, fontSize: 12, color: "#333" }}>
              外搜 (benchmark / xlab): {backendStatus.search.benchmark_web_search_enabled ? "开启" : "关闭"} /{" "}
              {backendStatus.search.ok ? "ready" : "not-ready"} / Tavily{" "}
              {backendStatus.search.tavily_configured ? "已配置" : "未配置"} · Exa{" "}
              {backendStatus.search.exa_configured ? "已配置" : "未配置"} / {backendStatus.search.detail}
            </div>
          ) : (
            <div style={{ marginTop: 4, fontSize: 12, color: "#888" }}>
              外搜: （后端未返回 search 字段，请升级后端）
            </div>
          )}
          {backendStatus.sandbox_exec ? (
            <div style={{ marginTop: 4, fontSize: 12, color: "#333" }}>
              沙盒 CLI: {backendStatus.sandbox_exec.enabled ? "开启" : "关闭"} /{" "}
              {backendStatus.sandbox_exec.ok ? "ready" : "not-ready"} / allow={backendStatus.sandbox_exec.allowlist_count}{" "}
              / cwd={backendStatus.sandbox_exec.exec_cwd ?? "—"} / {backendStatus.sandbox_exec.detail}
            </div>
          ) : null}
          <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px dashed #ddd" }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Phase 3 · CLI 沙盒演示</div>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>
              POST <code>/api/sandbox/exec</code> · 仅白名单二进制 · 工作在 backend 根目录或其子路径 · <strong>不落 shell</strong>
            </div>
            <textarea
              value={sandboxArgvJson}
              onChange={(e) => setSandboxArgvJson(e.target.value)}
              placeholder='需在 .env 中配置 HSEMAS_EXEC_ALLOWLIST 包含 argv[0] 的 stem，例如 python 或 pytest；JSON 每项为独立的 argv token'
              rows={3}
              spellCheck={false}
              style={{ width: "100%", fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", fontSize: 12 }}
            />
            <button
              onClick={() => runSandboxExec().catch(() => {})}
              style={{
                marginTop: 6,
                padding: "8px 12px",
                borderRadius: 10,
                border: "1px solid #bbb",
                background: "#fff",
                cursor: "pointer",
                fontSize: 12,
              }}
            >
              运行 argv（JSON）
            </button>
            {sandboxExecResult ? (
              <pre
                style={{
                  marginTop: 8,
                  padding: 10,
                  borderRadius: 10,
                  border: "1px solid #eee",
                  background: "#fafafa",
                  fontSize: 11,
                  maxHeight: 280,
                  overflow: "auto",
                }}
              >
                {pretty(sandboxExecResult)}
              </pre>
            ) : null}
          </div>
        </div>
      ) : null}

      <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
        <div style={{ flex: 1 }}>
          <label style={{ display: "block", fontWeight: 600, marginBottom: 6 }}>模式</label>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <select
              value={modeId}
              onChange={(e) => setModeId(e.target.value)}
              style={{ padding: 10, borderRadius: 8, border: "1px solid #ccc", minWidth: 280 }}
            >
              {modes.length === 0 ? (
                <option value={modeId}>{modeId}</option>
              ) : (
                modes.map((m) => (
                  <option key={m.mode_id} value={m.mode_id}>
                        {m.label}（{m.mode_id}）
                  </option>
                ))
              )}
            </select>
            <button
              onClick={loadModes}
              style={{
                padding: "10px 12px",
                borderRadius: 10,
                border: "1px solid #bbb",
                background: "#fff",
                cursor: "pointer",
              }}
            >
              刷新模式列表
            </button>
          </div>
          <div style={{ marginTop: 6, color: "#666", fontSize: 12 }}>
            不同模式的历史记录/基因库/影子测试按 <code>mode_id</code> 隔离保存（已实现）。
          </div>

          <label style={{ display: "block", fontWeight: 600, marginBottom: 6 }}>任务</label>
          <textarea
            value={task}
            onChange={(e) => setTask(e.target.value)}
            rows={5}
            style={{ width: "100%", padding: 10, borderRadius: 8, border: "1px solid #ccc" }}
          />
          <div style={{ marginTop: 10, display: "flex", gap: 10, alignItems: "center" }}>
            <button
              onClick={start}
              style={{
                padding: "10px 14px",
                borderRadius: 10,
                border: "1px solid #222",
                background: "#111",
                color: "#fff",
                cursor: "pointer",
              }}
            >
              开始决策（MVP）
            </button>
            <div style={{ color: "#333" }}>
              <div style={{ fontSize: 12, color: "#666" }}>decision_id</div>
              <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" }}>
                {decisionId || "-"}
              </div>
            </div>
          </div>

          <div style={{ marginTop: 16 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ fontWeight: 600 }}>本模式历史记录（隔离）</div>
              <button
                onClick={loadHistory}
                style={{
                  padding: "8px 10px",
                  borderRadius: 10,
                  border: "1px solid #bbb",
                  background: "#fff",
                  cursor: "pointer",
                  fontSize: 12,
                }}
              >
                刷新历史
              </button>
            </div>
            {historyFetchError ? (
              <div
                style={{
                  marginTop: 8,
                  padding: "8px 10px",
                  borderRadius: 10,
                  background: "#fff8e1",
                  border: "1px solid #ffcc80",
                  fontSize: 12,
                  color: "#bf360c",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 10,
                  flexWrap: "wrap",
                }}
              >
                <span>{historyFetchError}</span>
                <button
                  type="button"
                  onClick={() => setHistoryFetchError(null)}
                  style={{ fontSize: 11, cursor: "pointer", border: "none", background: "transparent", textDecoration: "underline", color: "#bf360c" }}
                >
                  关闭
                </button>
              </div>
            ) : null}
            <div
              style={{
                marginTop: 8,
                border: "1px solid #eee",
                borderRadius: 10,
                padding: 10,
                background: "#fff",
              }}
            >
              {history.length === 0 ? (
                <div style={{ color: "#666", fontSize: 12 }}>（该模式暂无历史，跑一次决策就会出现）</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {history.map((h, idx) => (
                    <button
                      key={`${h.decision_id || "x"}-${idx}`}
                      onClick={() => void openHistoryDetail(h)}
                      style={{
                        textAlign: "left",
                        border: "none",
                        background: "transparent",
                        padding: 0,
                        cursor: "pointer",
                      }}
                    >
                      <div
                        style={{
                          borderTop: idx === 0 ? "none" : "1px solid #f0f0f0",
                          paddingTop: idx === 0 ? 0 : 10,
                        }}
                      >
                        <div style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap" }}>
                          <div
                            style={{
                              fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
                              fontSize: 12,
                            }}
                          >
                            {h.decision_id || "-"}
                          </div>
                          <div style={{ color: "#666", fontSize: 12 }}>{h.created_at || ""}</div>
                        </div>
                        <div style={{ marginTop: 6, fontSize: 13, color: "#222" }}>
                          {h.task || ""}
                          {h.task_truncated ? (
                            <span style={{ marginLeft: 6, fontSize: 11, color: "#888" }}>（列表节选）</span>
                          ) : null}
                        </div>
                      {h.mode_label ? (
                        <div style={{ marginTop: 6, fontSize: 12, color: "#666" }}>
                          <b>模式</b>：{h.mode_label}
                        </div>
                      ) : null}
                        {h.dispatcher && typeof h.dispatcher.level === "string" ? (
                          <div style={{ marginTop: 6, fontSize: 11, color: "#55708f" }}>
                            <b>分诊</b>：{h.dispatcher.level}
                            {typeof h.dispatcher.urgency === "string" ? ` · ${h.dispatcher.urgency}` : ""}
                          </div>
                        ) : null}
                        {h.execution ? (
                          <div
                            style={{
                              marginTop: 6,
                              fontSize: 11,
                              display: "flex",
                              gap: 8,
                              flexWrap: "wrap",
                              alignItems: "center",
                            }}
                          >
                            <span
                              style={{
                                padding: "2px 8px",
                                borderRadius: 999,
                                background: h.execution.qa_sandbox?.ok ? "#e8f5e9" : "#ffebee",
                                color: "#222",
                              }}
                            >
                              QA {h.execution.qa_sandbox?.ok ? "hard OK" : "hard 未过"}
                            </span>
                            <span style={{ padding: "2px 8px", borderRadius: 999, background: "#ede7f6", color: "#222" }}>
                              Executor {String((h.execution.executor as { status?: string } | undefined)?.status ?? "—")}
                            </span>
                            {(h.execution.executor as { suggested_cli_probe?: { enabled?: boolean } } | undefined)?.suggested_cli_probe
                              ?.enabled ? (
                              <span style={{ padding: "2px 8px", borderRadius: 999, background: "#e3f2fd", color: "#1565c0" }}>
                                CLI 提示已生成
                              </span>
                            ) : null}
                          </div>
                        ) : null}
                        {h.dept_reports_preview ? (
                          <div style={{ marginTop: 6, fontSize: 11, color: "#666" }}>
                            <b>部门产出</b>：{h.dept_reports_preview.count ?? 0} 条
                            {h.dept_reports_preview.depts && h.dept_reports_preview.depts.length > 0
                              ? `（${h.dept_reports_preview.depts.join(" · ")}）`
                              : ""}
                          </div>
                        ) : null}
                        {h.ceo_decision ? (
                          <div style={{ marginTop: 6, fontSize: 12, color: "#444" }}>
                            <b>CEO</b>：{h.ceo_decision}
                            {h.ceo_decision_truncated ? (
                              <span style={{ marginLeft: 6, fontSize: 11, color: "#888" }}>（节选）</span>
                            ) : null}
                          </div>
                        ) : null}
                        {h.red_team_risks && h.red_team_risks.length > 0 ? (
                          <div style={{ marginTop: 6, fontSize: 12, color: "#8a2a00" }}>
                            <b>RedTeam</b>：{h.red_team_risks.join("；")}
                          </div>
                        ) : null}
                        <div style={{ marginTop: 6, fontSize: 12, color: "#666" }}>
                          {historyLoadingId === h.decision_id ? (
                            <span style={{ color: "#1565c0" }}>加载完整决策中…</span>
                          ) : (
                            <>（点击拉取全文含部门 RAG/辩论；列表为 compact 节选）</>
                          )}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div style={{ marginTop: 16 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ fontWeight: 600 }}>本模式基因（Prompt）</div>
              <button
                onClick={loadGene}
                style={{
                  padding: "8px 10px",
                  borderRadius: 10,
                  border: "1px solid #bbb",
                  background: "#fff",
                  cursor: "pointer",
                  fontSize: 12,
                }}
              >
                刷新基因
              </button>
            </div>

            <div style={{ marginTop: 8, display: "flex", gap: 10, alignItems: "center" }}>
              <div style={{ fontSize: 12, color: "#666" }}>部门</div>
              <select
                value={deptId}
                onChange={(e) => setDeptId(e.target.value)}
                style={{ padding: 10, borderRadius: 8, border: "1px solid #ccc", minWidth: 220 }}
              >
                {(modes.find((m) => m.mode_id === modeId)?.departments || []).map((d) => (
                  <option key={d} value={d}>
                    {(modes.find((m) => m.mode_id === modeId)?.department_labels || {})[d] ? `${(modes.find((m) => m.mode_id === modeId)?.department_labels || {})[d]}（${d}）` : d}
                  </option>
                ))}
              </select>
              <div style={{ fontSize: 12, color: "#666" }}>
                v{gene?.version ?? "-"} {gene?.created_at ? `@ ${gene.created_at}` : ""}
              </div>
            </div>

            <textarea
              value={genePrompt}
              onChange={(e) => setGenePrompt(e.target.value)}
              rows={4}
              style={{ width: "100%", marginTop: 8, padding: 10, borderRadius: 8, border: "1px solid #ccc" }}
            />
            <div style={{ marginTop: 8, display: "flex", gap: 10 }}>
              <button
                onClick={saveGene}
                style={{
                  padding: "10px 12px",
                  borderRadius: 10,
                  border: "1px solid #222",
                  background: "#111",
                  color: "#fff",
                  cursor: "pointer",
                  fontSize: 12,
                }}
              >
                保存为 Active
              </button>
              <button
                onClick={saveShadow}
                style={{
                  padding: "10px 12px",
                  borderRadius: 10,
                  border: "1px solid #bbb",
                  background: "#fff",
                  cursor: "pointer",
                  fontSize: 12,
                }}
              >
                保存为 Shadow
              </button>
            </div>

            <div style={{ marginTop: 10, fontSize: 12, color: "#666" }}>
              Shadow 列表（本模式隔离）：{shadows.length === 0 ? "暂无" : ""}
            </div>
            {shadows.length > 0 ? (
              <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 6 }}>
                {shadows.map((s, idx) => (
                  <div
                    key={`${s.version ?? "x"}-${idx}`}
                    style={{
                      border: "1px solid #eee",
                      borderRadius: 10,
                      padding: 10,
                      background: "#fafafa",
                    }}
                  >
                    <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "baseline" }}>
                      <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" }}>
                        shadow_v{s.version ?? "-"}
                      </div>
                      <div style={{ color: "#777" }}>{s.created_at || ""}</div>
                      {typeof s.version === "number" ? (
                        <button
                          onClick={() => loadShadowStatus(s.version as number)}
                          style={{
                            marginLeft: "auto",
                            padding: "6px 10px",
                            borderRadius: 10,
                            border: "1px solid #bbb",
                            background: "#fff",
                            cursor: "pointer",
                            fontSize: 12,
                          }}
                        >
                          查看影子测试
                        </button>
                      ) : null}
                    </div>
                    <div style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{String(s.prompt || "").slice(0, 260)}</div>
                  </div>
                ))}
              </div>
            ) : null}

            {shadowStatus ? (
              <div style={{ marginTop: 10, border: "1px solid #eee", borderRadius: 10, padding: 10, background: "#fff" }}>
                <div style={{ fontWeight: 600, marginBottom: 6 }}>
                  影子测试结果：{shadowStatus.verdict?.promote ? "✅ 可晋升" : "⏳ 继续观察"}（{shadowStatus.verdict?.reason || ""}）
                </div>
                <div style={{ fontSize: 12, color: "#666" }}>
                  最近得分（delta = shadow - active）：
                </div>
                <div
                  style={{
                    marginTop: 6,
                    border: "1px solid #eee",
                    borderRadius: 10,
                    background: "#fafafa",
                    padding: 10,
                    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
                    fontSize: 12,
                    whiteSpace: "pre-wrap",
                    maxHeight: 180,
                    overflow: "auto",
                  }}
                >
                  {(shadowStatus.scores || []).length === 0
                    ? "（暂无评分记录，跑几次决策后会出现）"
                    : (shadowStatus.scores || [])
                        .map(
                          (r) =>
                            `${r.ts}  active=${Number(r.score_active ?? 0).toFixed(2)}  shadow=${Number(
                              r.score_shadow ?? 0,
                            ).toFixed(2)}  delta=${Number(r.delta ?? 0).toFixed(2)}`,
                        )
                        .join("\\n")}
                </div>
              </div>
            ) : null}
          </div>

          <div style={{ marginTop: 16 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ fontWeight: 600 }}>本模式设置：可信信源权重（Benchmark 用）</div>
              <div style={{ fontSize: 12, color: "#666" }}>{modeConfig?.updated_at ? `更新于 ${modeConfig.updated_at}` : ""}</div>
            </div>
            <div style={{ marginTop: 8, color: "#666", fontSize: 12 }}>
              格式是 JSON：{"{ \"github.com\": 0.95, \"arxiv.org\": 1.0 }"}
            </div>
            <textarea
              value={trustedSourcesText}
              onChange={(e) => setTrustedSourcesText(e.target.value)}
              rows={5}
              style={{ width: "100%", marginTop: 8, padding: 10, borderRadius: 8, border: "1px solid #ccc" }}
            />
            <div style={{ marginTop: 8, display: "flex", gap: 10 }}>
              <button
                onClick={saveModeConfig}
                style={{
                  padding: "10px 12px",
                  borderRadius: 10,
                  border: "1px solid #222",
                  background: "#111",
                  color: "#fff",
                  cursor: "pointer",
                  fontSize: 12,
                }}
              >
                保存设置
              </button>
              <button
                onClick={loadModeConfig}
                style={{
                  padding: "10px 12px",
                  borderRadius: 10,
                  border: "1px solid #bbb",
                  background: "#fff",
                  cursor: "pointer",
                  fontSize: 12,
                }}
              >
                重新加载
              </button>
            </div>
          </div>

          <div style={{ marginTop: 16 }}>
            <div style={{ fontWeight: 600 }}>本模式 RAG（Qdrant / Local）</div>
            <div style={{ marginTop: 6, color: "#666", fontSize: 12 }}>
              先粘贴知识片段 → 点 Ingest。再输入查询 → Search。数据按 <code>mode_id</code> 隔离。
            </div>
            {backendStatus?.rag?.backend === "simulated" ? (
              <div style={{ marginTop: 8, padding: 10, borderRadius: 10, border: "1px solid #eee", background: "#fffbe6", fontSize: 12, color: "#333" }}>
                当前 <b>RAG_BACKEND=simulated</b>：Ingest 是 <b>no-op</b>，Search 会返回空数组。要启用本地可检索 RAG（无需 Docker），把 <code>.env</code>{" "}
                设为 <code>RAG_BACKEND=local</code>，然后重启后端。
              </div>
            ) : null}
            {ragLastIngest ? (
              <div style={{ marginTop: 8, fontSize: 12, color: "#333" }}>
                最近一次 ingest：<span style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" }}>{pretty(ragLastIngest)}</span>
              </div>
            ) : null}
            <textarea
              value={ragText}
              onChange={(e) => setRagText(e.target.value)}
              rows={6}
              style={{ width: "100%", marginTop: 8, padding: 10, borderRadius: 8, border: "1px solid #ccc" }}
            />
            <div style={{ marginTop: 8, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <button
                onClick={ragIngest}
                style={{
                  padding: "10px 12px",
                  borderRadius: 10,
                  border: "1px solid #222",
                  background: "#111",
                  color: "#fff",
                  cursor: "pointer",
                  fontSize: 12,
                }}
              >
                Ingest
              </button>
              <input
                value={ragQuery}
                onChange={(e) => setRagQuery(e.target.value)}
                placeholder="搜索关键词"
                style={{ padding: 10, borderRadius: 8, border: "1px solid #ccc", minWidth: 220 }}
              />
              <button
                onClick={ragSearch}
                style={{
                  padding: "10px 12px",
                  borderRadius: 10,
                  border: "1px solid #bbb",
                  background: "#fff",
                  cursor: "pointer",
                  fontSize: 12,
                }}
              >
                Search
              </button>
            </div>
            {ragResults.length > 0 ? (
              <div style={{ marginTop: 8, border: "1px solid #eee", borderRadius: 10, padding: 10, background: "#fff" }}>
                <div style={{ fontSize: 12, color: "#666" }}>结果：</div>
                <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 8 }}>
                  {ragResults.map((r, idx) => (
                    <div key={idx} style={{ borderTop: idx === 0 ? "none" : "1px solid #f0f0f0", paddingTop: idx === 0 ? 0 : 8 }}>
                      <div style={{ fontWeight: 700 }}>{r.title}</div>
                      <div style={{ fontSize: 12, color: "#666" }}>
                        score={Number(r.score ?? 0).toFixed(3)} chunk_id={r.chunk_id}
                        {r?.meta?.domain ? ` domain=${r.meta.domain}` : ""}
                        {typeof r?.meta?.trusted_weight === "number" ? ` weight=${Number(r.meta.trusted_weight).toFixed(2)}` : ""}
                        {typeof r?.meta?.weighted_score === "number" ? ` weighted=${Number(r.meta.weighted_score).toFixed(3)}` : ""}
                      </div>
                      <div style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{String(r.content || "").slice(0, 260)}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>

        <div style={{ width: 420 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>事件流</div>
          <div
            style={{
              height: 280,
              overflow: "auto",
              border: "1px solid #ddd",
              borderRadius: 10,
              background: "#fafafa",
              padding: 10,
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
              fontSize: 12,
              whiteSpace: "pre-wrap",
            }}
          >
            {events.length === 0 ? "（暂无事件）" : events.map((e, i) => `#${i + 1} ${e.type}\n${pretty(e.payload)}\n`).join("\n")}
          </div>
          <div style={{ marginTop: 8, color: "#666", fontSize: 12 }}>
            下一步：把热力图矩阵 + 部门产出详情面板接到 UI（Phase 2）。
          </div>
        </div>
      </div>

      {latestSummary ? (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>最新一次决策产出（本模式）</div>

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "baseline" }}>
            <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", fontSize: 12 }}>
              {latestSummary.decision_id}
            </div>
            <div style={{ color: "#666", fontSize: 12 }}>{latestSummary.task}</div>
          </div>

          {latestSummary.ceo_decision ? (
            <div style={{ marginTop: 8, padding: 10, borderRadius: 10, border: "1px solid #eee", background: "#fff" }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>CEO</div>
              <div style={{ whiteSpace: "pre-wrap" }}>{latestSummary.ceo_decision}</div>
            </div>
          ) : null}

          {latestSummary.execution ? (
            <div style={{ marginTop: 10, padding: 10, borderRadius: 10, border: "1px solid #ede8ff", background: "#faf8ff" }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Phase 3 · QA 沙箱 + Executor</div>
              <div style={{ fontSize: 12, marginBottom: 8, color: "#444" }}>
                校验为确定性逻辑（不落盘 subprocess）；执行清单供人工跟进。若后端配置了 CLI 白名单，可出现「CLI 探测建议」，一键填入页顶沙盒（仍须手动点运行）。
              </div>
              {latestSummary.execution.qa_sandbox ? (
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>
                    QA {latestSummary.execution.qa_sandbox.ok ? "✓ hard OK" : "✗ hard 未通过"}
                  </div>
                  <pre style={{ margin: "6px 0 0", fontSize: 11, whiteSpace: "pre-wrap", overflow: "auto", maxHeight: 200 }}>
                    {pretty(latestSummary.execution.qa_sandbox)}
                  </pre>
                </div>
              ) : null}
              {latestSummary.execution.executor ? (
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>
                    Executor 状态：<span style={{ color: latestSummary.execution.executor.status === "ready" ? "#0a7" : "#c53" }}>
                      {String(latestSummary.execution.executor.status || "")}
                    </span>
                    {latestSummary.execution.executor.blocked_reason ? (
                      <span style={{ marginLeft: 8, fontSize: 12, color: "#666" }}>{String(latestSummary.execution.executor.blocked_reason)}</span>
                    ) : null}
                  </div>
                  {(() => {
                    const probe = latestSummary.execution!.executor!.suggested_cli_probe as
                      | { enabled?: boolean; argv?: string[]; note?: string; reason?: string }
                      | undefined;
                    if (!probe) return null;
                    if (probe.enabled && Array.isArray(probe.argv) && probe.argv.length > 0) {
                      const line = JSON.stringify(probe.argv);
                      return (
                        <div
                          style={{
                            marginTop: 8,
                            marginBottom: 8,
                            padding: 10,
                            borderRadius: 10,
                            border: "1px solid #c8e6c9",
                            background: "#f1faf3",
                            fontSize: 12,
                          }}
                        >
                          <div style={{ fontWeight: 600 }}>CLI 探测建议（与 HSEMAS_EXEC_ALLOWLIST 对齐，不自动执行）</div>
                          <div style={{ marginTop: 6, fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", wordBreak: "break-all" }}>
                            {line}
                          </div>
                          <button
                            type="button"
                            onClick={() => setSandboxArgvJson(line)}
                            style={{
                              marginTop: 8,
                              padding: "6px 10px",
                              borderRadius: 8,
                              border: "1px solid #81c784",
                              background: "#fff",
                              cursor: "pointer",
                              fontSize: 12,
                            }}
                          >
                            填入页顶「CLI 沙盒」JSON
                          </button>
                          {probe.note ? <div style={{ marginTop: 6, color: "#555" }}>{probe.note}</div> : null}
                        </div>
                      );
                    }
                    if (probe.enabled && (!probe.argv || probe.argv.length === 0)) {
                      const stems = (probe as { allowed_stems?: string[] }).allowed_stems;
                      if (stems && stems.length > 0) {
                        return (
                          <div style={{ marginTop: 6, fontSize: 11, color: "#666" }}>
                            白名单 stem：{stems.join(", ")} — {probe.note || "无预置 --version 类模板，请在页顶手写 argv"}
                          </div>
                        );
                      }
                    }
                    return (
                      <div style={{ marginTop: 6, fontSize: 11, color: "#888" }}>
                        CLI 提示：
                        {probe.reason === "sandbox_disabled"
                          ? "后端未开启 HSEMAS_SANDBOX_EXEC"
                          : probe.reason === "allowlist_empty"
                            ? "白名单为空"
                            : probe.reason || "无可用 argv 模板"}
                      </div>
                    );
                  })()}
                  <pre style={{ margin: "6px 0 0", fontSize: 11, whiteSpace: "pre-wrap", overflow: "auto", maxHeight: 240 }}>
                    {pretty(latestSummary.execution.executor)}
                  </pre>
                </div>
              ) : null}
            </div>
          ) : null}

          {latestSummary.dispatcher && Object.keys(latestSummary.dispatcher).length > 0 ? (
            <div style={{ marginTop: 10, padding: 10, borderRadius: 10, border: "1px solid #e8f4ff", background: "#f7fbff" }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>预处理分诊官（Dispatcher）</div>
              <pre style={{ margin: 0, fontSize: 12, whiteSpace: "pre-wrap", fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" }}>
                {pretty(latestSummary.dispatcher)}
              </pre>
            </div>
          ) : null}

          {latestSummary.heatmap && latestSummary.heatmap.length > 0 ? (
            <div style={{ marginTop: 10, padding: 10, borderRadius: 10, border: "1px solid #eee", background: "#fff" }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>热力图（点击部门展开详情）</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {latestSummary.heatmap.map((c, idx) => (
                  <button
                    key={`${c.dept ?? "x"}-${idx}`}
                    onClick={() => setOpenDept(openDept === c.dept ? "" : String(c.dept || ""))}
                    style={{
                      textAlign: "left",
                      padding: "8px 10px",
                      borderRadius: 10,
                      border: "1px solid #eee",
                      background: c.alert === "red" ? "#fff3f0" : c.alert === "yellow" ? "#fffbe6" : "#f3fff6",
                      cursor: "pointer",
                    }}
                  >
                    <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "baseline" }}>
                      <div style={{ fontWeight: 700 }}>
                        {c.dept ? (deptLabels[c.dept] ? `${deptLabels[c.dept]}（${c.dept}）` : c.dept) : ""}
                      </div>
                      <div style={{ fontSize: 12, color: "#666" }}>
                        conf={Number(c.confidence_score ?? 0).toFixed(2)} dissent={Number(c.dissent_intensity ?? 0).toFixed(2)} alert={c.alert}
                      </div>
                      <div style={{ fontSize: 12, color: "#888" }}>{c.debate_log_id}</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {openDept && latestSummary.dept_reports && latestSummary.dept_reports.length > 0 ? (
            <div style={{ marginTop: 10, padding: 10, borderRadius: 10, border: "1px solid #eee", background: "#fff" }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>
                部门详情：{deptLabels[openDept] ? `${deptLabels[openDept]}（${openDept}）` : openDept}
              </div>
              {latestSummary.dept_reports
                .filter((r) => r.dept === openDept)
                .map((r, idx) => (
                  <div key={idx}>
                    <div style={{ fontSize: 12, color: "#666" }}>
                      confidence={Number(r.confidence_score ?? 0).toFixed(2)} dissent={Number(r.dissent_intensity ?? 0).toFixed(2)} weight={Number(r.credibility_weight ?? 0).toFixed(2)}
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <div style={{ fontWeight: 600 }}>Lead 共识</div>
                      <div style={{ whiteSpace: "pre-wrap" }}>{r.consensus}</div>
                    </div>
                    {r.conflicts && r.conflicts.length > 0 ? (
                      <div style={{ marginTop: 8 }}>
                        <div style={{ fontWeight: 600 }}>冲突</div>
                        <ul style={{ margin: "6px 0 0 18px" }}>
                          {r.conflicts.map((c, i) => (
                            <li key={i}>{c}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {r.dispatcher_context ? (
                      <div style={{ marginTop: 8 }}>
                        <div style={{ fontWeight: 600 }}>分诊官下发（本部门）</div>
                        <div
                          style={{
                            marginTop: 6,
                            border: "1px solid #e8f4ff",
                            borderRadius: 10,
                            background: "#fafcff",
                            padding: 10,
                            fontSize: 12,
                            whiteSpace: "pre-wrap",
                          }}
                        >
                          {String(r.dispatcher_context)}
                        </div>
                      </div>
                    ) : null}
                    {r.rag_context && Array.isArray(r.rag_context) && r.rag_context.length > 0 ? (
                      <div style={{ marginTop: 8 }}>
                        <div style={{ fontWeight: 600 }}>
                          {openDept === "benchmark" || openDept === "xlab"
                            ? "本部门注入的检索片段（外搜 + 向量/RAG，顺序已按可信域加权，与 LLM 输入一致）"
                            : "本部门注入的 RAG 片段（与 LLM 输入一致）"}
                        </div>
                        <pre
                          style={{
                            marginTop: 6,
                            padding: 10,
                            borderRadius: 10,
                            border: "1px solid #eee",
                            background: "#fafafa",
                            fontSize: 11,
                            overflow: "auto",
                            maxHeight: 220,
                          }}
                        >
                          {pretty(r.rag_context)}
                        </pre>
                      </div>
                    ) : null}
                    {r.raw_debate && r.raw_debate.length > 0 ? (
                      <div style={{ marginTop: 8 }}>
                        <div style={{ fontWeight: 600 }}>辩论原始日志</div>
                        <div
                          style={{
                            marginTop: 6,
                            border: "1px solid #eee",
                            borderRadius: 10,
                            background: "#fafafa",
                            padding: 10,
                            fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
                            fontSize: 12,
                            whiteSpace: "pre-wrap",
                          }}
                        >
                          {r.raw_debate.map((x, i) => `[${x.role}] ${x.content}`).join("\n\n")}
                        </div>
                      </div>
                    ) : null}
                  </div>
                ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

