"use client";

import Link from "next/link";
import type { CSSProperties } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  HSEMAS_BACKEND_STORAGE_KEY,
  httpToWsOrigin,
  normalizeBackendUrl,
  resolveBackendHttpBase,
  resolveBackendHttpBaseIgnoringStorage,
} from "../lib/backend";
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
  scenario_description?: string | null;
  default_task_hint?: string | null;
};

type DeptReport = {
  dept?: string;
  consensus?: string;
  conflicts?: string[];
  confidence_score?: number;
  dissent_intensity?: number;
};

type HeatCell = {
  dept?: string;
  confidence_score?: number;
  dissent_intensity?: number;
  alert?: string;
};

type DecisionSummary = {
  decision_id?: string;
  task?: string;
  mode_id?: string;
  mode_label?: string;
  created_at?: string;
  heatmap?: HeatCell[];
  dept_reports?: DeptReport[];
  ceo_decision?: string;
  red_team_risks?: string[];
};

type DeptRuntime = {
  dept: string;
  label: string;
  /** pending | running | done */
  phase: "pending" | "running" | "done";
  /** 业务化状态灯：ok | warn | block */
  lamp: "ok" | "warn" | "block";
  caption: string;
  focusRank: number;
};

type GeneRoleSlot = "member_a" | "member_b" | "member_c" | "lead";

type GeneRole = {
  role_title: string;
  persona_prompt: string;
};

type DeptGeneTeam = {
  member_a: GeneRole;
  member_b: GeneRole;
  member_c: GeneRole;
  lead: GeneRole;
};

function emptyGeneRole(): GeneRole {
  return { role_title: "", persona_prompt: "" };
}

function emptyDeptGeneTeam(): DeptGeneTeam {
  return {
    member_a: emptyGeneRole(),
    member_b: emptyGeneRole(),
    member_c: emptyGeneRole(),
    lead: emptyGeneRole(),
  };
}

const GENE_SLOT_ROWS: { id: GeneRoleSlot; label: string; hint: string }[] = [
  { id: "member_a", label: "成员 A", hint: "CEO 分配的职能视角一" },
  { id: "member_b", label: "成员 B", hint: "CEO 分配的职能视角二" },
  { id: "member_c", label: "成员 C", hint: "CEO 分配的职能视角三" },
  { id: "lead", label: "部门主管 (Lead)", hint: "主持内部辩论；汇总共识与无法调和的冲突上报 CEO" },
];

function alertFromScores(confidence: number, dissent: number): "green" | "yellow" | "red" {
  if (dissent > 0.7 || confidence < 0.5) return "red";
  if (dissent > 0.4 || confidence < 0.65) return "yellow";
  return "green";
}

function lampLabel(alert: "green" | "yellow" | "red", confidence: number): { lamp: DeptRuntime["lamp"]; caption: string } {
  if (alert === "red") {
    if (confidence < 0.5) {
      return { lamp: "block", caption: "异常拦截：信息不足或评估信心偏低，建议补充材料后再评" };
    }
    return { lamp: "warn", caption: "业务告警：存在强分歧或高风险信号，请在汇总区重点核对" };
  }
  if (alert === "yellow") {
    return { lamp: "warn", caption: "业务告警：存在中等分歧或不确定性，建议结合其他部门意见判断" };
  }
  return { lamp: "ok", caption: "已完成本部门评估" };
}

function focusRankFrom(alert: "green" | "yellow" | "red", confidence: number): number {
  if (alert === "red") return confidence < 0.5 ? 300 : 200;
  if (alert === "yellow") return 100;
  return 0;
}

function inferStance(text: string): { tag: string; color: string } {
  const t = text || "";
  if (/反对|不建议|否决|风险过高|不可行|暂缓/i.test(t)) return { tag: "审慎 / 反对倾向", color: "#b71c1c" };
  if (/条件|前提|需.*确认|取决于/i.test(t)) return { tag: "有条件支持", color: "#e65100" };
  if (/支持|赞同|建议推进|可行/i.test(t)) return { tag: "支持倾向", color: "#1b5e20" };
  return { tag: "中性 / 待对齐", color: "#37474f" };
}

/** Keys accepted by ``PUT /api/settings/hub`` (same family as multi-brand AI 客服项目). */
const HUB_SERVER_KEYS = [
  "llm_provider",
  "litellm_base_url",
  "litellm_default_model",
  "litellm_fallback_models",
  "litellm_max_retries",
  "litellm_retry_base_ms",
  "litellm_embedding_model",
  "embedding_vector_dim",
  "anthropic_api_key",
  "openai_api_key",
  "gemini_api_key",
  "deepseek_api_key",
  "doubao_api_key",
  "rag_backend",
  "rag_hybrid_local_fts",
  "qdrant_url",
  "qdrant_api_key",
  "benchmark_web_search",
  "tavily_api_key",
  "exa_api_key",
] as const;

function emptyHubForm(): Record<string, string> {
  return Object.fromEntries(HUB_SERVER_KEYS.map((k) => [k, ""])) as Record<string, string>;
}

function settingsResponseToForm(s: Record<string, unknown>): Record<string, string> {
  const out = emptyHubForm();
  for (const k of HUB_SERVER_KEYS) {
    const v = s[k];
    if (v === null || v === undefined) out[k] = "";
    else if (typeof v === "boolean") out[k] = v ? "true" : "false";
    else out[k] = String(v);
  }
  return out;
}

function valueForHubPayload(k: string, rawTrimmed: string): unknown {
  const intKeys = new Set<string>(["litellm_max_retries", "litellm_retry_base_ms", "embedding_vector_dim"]);
  const boolKeys = new Set<string>(["rag_hybrid_local_fts", "benchmark_web_search"]);
  if (boolKeys.has(k)) {
    return rawTrimmed === "true" || rawTrimmed === "1" || rawTrimmed === "yes" || rawTrimmed === "on";
  }
  if (intKeys.has(k)) {
    if (rawTrimmed === "") return "";
    const n = parseInt(rawTrimmed, 10);
    return Number.isNaN(n) ? rawTrimmed : n;
  }
  return rawTrimmed;
}

/** Build partial PUT body: only keys that differ from baseline (avoids wiping hub file on first mis-click). */
function hubDiffPayload(form: Record<string, string>, baseline: Record<string, string>): Record<string, unknown> {
  const p: Record<string, unknown> = {};
  for (const k of HUB_SERVER_KEYS) {
    const cur = (form[k] ?? "").trim();
    const base = (baseline[k] ?? "").trim();
    if (cur === base) continue;
    if (cur === "") {
      p[k] = "";
      continue;
    }
    if (String(cur).startsWith("***")) continue;
    p[k] = valueForHubPayload(k, cur);
  }
  return p;
}

type HubDeptRoutingRow = {
  dept_id: string;
  label: string;
  ai_profile_id?: string | null;
  ai_profile_label?: string | null;
  override_model?: string | null;
  resolved_model: string;
  source: string;
};

type HubAiProfileRow = { id: string; label: string; model: string };

type HubDeptRoutingPayload = {
  mode_id: string;
  mode_label?: string;
  default_model?: string | null;
  rows: HubDeptRoutingRow[];
};

function parseDeptModelsMap(raw: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return out;
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof v === "string") out[k] = v;
  }
  return out;
}

function parseAiProfiles(raw: unknown): HubAiProfileRow[] {
  if (!Array.isArray(raw)) return [];
  const out: HubAiProfileRow[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const o = item as Record<string, unknown>;
    const id = String(o.id ?? "").trim();
    const model = String(o.model ?? "").trim();
    if (!id || !model) continue;
    out.push({ id, label: String(o.label ?? id).trim() || id, model });
  }
  return out;
}

/** Keys where department override model changed vs last loaded baseline (empty string clears override). */
function deptModelsPatch(cur: Record<string, string>, baseline: Record<string, string>): Record<string, string> | null {
  const keys = new Set([...Object.keys(cur), ...Object.keys(baseline)]);
  const patch: Record<string, string> = {};
  for (const k of keys) {
    const a = (cur[k] ?? "").trim();
    const b = (baseline[k] ?? "").trim();
    if (a !== b) patch[k] = a;
  }
  return Object.keys(patch).length ? patch : null;
}

type DiagResultRow = { label: string; result: "pass" | "fail" | "skip"; hint: string };

const PROVIDER_SLOT_LABEL: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  gemini: "Gemini",
  deepseek: "DeepSeek",
  doubao: "豆包",
};

function diagBadgeStyle(result: DiagResultRow["result"]): { text: string; fg: string; bg: string } {
  if (result === "pass") return { text: "通过", fg: "#1b5e20", bg: "#e8f5e9" };
  if (result === "fail") return { text: "未通过", fg: "#b71c1c", bg: "#ffebee" };
  return { text: "跳过", fg: "#455a64", bg: "#eceff1" };
}

/** Turn ``/api/settings/hub/diagnostics/connectivity`` JSON into human-readable rows (no raw dump). */
function buildConnectivitySummary(payload: unknown): DiagResultRow[] {
  if (!payload || typeof payload !== "object") return [];
  const j = payload as Record<string, unknown>;
  const rows: DiagResultRow[] = [];
  const provRaw = String(j.llm_provider ?? "").trim();
  const prov = provRaw.toLowerCase();
  const validProv = prov === "litellm" || prov === "simulated";
  rows.push({
    label: "LLM 模式（提供商字段）",
    result: validProv ? "pass" : "fail",
    hint: validProv
      ? prov === "litellm"
        ? "litellm：通过 LiteLLM 调用真实模型（需配置密钥）"
        : "simulated：演示模式，不调外部大模型"
      : "此处只能填 litellm 或 simulated，不能填店铺名、昵称（如当前内容）。保存时会校验。",
  });

  const qdrant = j.qdrant as Record<string, unknown> | undefined;
  if (qdrant) {
    const ok = Boolean(qdrant.ok);
    rows.push({
      label: "向量 / RAG",
      result: ok ? "pass" : "fail",
      hint: `${String(qdrant.detail ?? "")}${qdrant.rag_backend != null ? ` · 后端 ${String(qdrant.rag_backend)}` : ""}`,
    });
  }

  const proxy = j.litellm_proxy as Record<string, unknown> | undefined;
  if (proxy) {
    const skipped = Boolean(proxy.skipped);
    const ok = Boolean(proxy.ok);
    rows.push({
      label: "LiteLLM 代理地址",
      result: skipped ? "skip" : ok ? "pass" : "fail",
      hint: skipped
        ? String(proxy.detail ?? "未填写 Base URL（直连厂商时可不填）")
        : String(proxy.detail ?? ""),
    });
  }

  const llmKeys = Array.isArray(j.llm_keys) ? j.llm_keys : [];
  for (const item of llmKeys) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    const id = String(row.id ?? "");
    const skipped = Boolean(row.skipped);
    const ok = Boolean(row.ok);
    const detail = String(row.detail ?? "");
    let result: DiagResultRow["result"] = "fail";
    let hint = detail;
    if (skipped) {
      result = "skip";
      if (detail.includes("not_configured")) hint = "未填写该槽位 API Key（跳过）";
      else if (detail.includes("llm_provider!=litellm"))
        hint =
          prov === "litellm"
            ? "内部跳过（请忽略）"
            : "当前为 simulated 或非 litellm，不检测真实大模型密钥槽位";
      else hint = detail || "跳过";
    } else {
      result = ok ? "pass" : "fail";
    }
    rows.push({
      label: `密钥槽 · ${PROVIDER_SLOT_LABEL[id] || id}`,
      result,
      hint,
    });
  }

  const search = Array.isArray(j.search) ? j.search : [];
  for (const item of search) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    const id = String(row.id ?? "");
    const skipped = Boolean(row.skipped);
    const ok = Boolean(row.ok);
    const label = id === "tavily" ? "外搜 · Tavily" : id === "exa" ? "外搜 · Exa" : `外搜 · ${id}`;
    let result: DiagResultRow["result"];
    let hint: string;
    if (skipped) {
      result = "skip";
      hint = detailIncludesNotConfigured(String(row.detail ?? "")) ? "未配置 API Key（跳过）" : String(row.detail ?? "");
    } else {
      result = ok ? "pass" : "fail";
      hint = String(row.detail ?? "");
    }
    rows.push({ label, result, hint });
  }

  return rows;
}

function detailIncludesNotConfigured(detail: string): boolean {
  return detail.includes("not_configured");
}

/** Turn ``/api/settings/hub/diagnostics/chat`` JSON into human-readable rows. */
function buildChatSummary(payload: unknown): DiagResultRow[] {
  if (!payload || typeof payload !== "object") return [];
  const j = payload as Record<string, unknown>;
  const rows: DiagResultRow[] = [];
  const prov = String(j.llm_provider ?? "").trim().toLowerCase();
  if (prov && prov !== "litellm") {
    rows.push({
      label: "说明",
      result: "skip",
      hint: "未启用 litellm 时，对话探测会跳过（与「提供商」设置一致）。",
    });
  }
  const llmChat = Array.isArray(j.llm_chat) ? j.llm_chat : [];
  for (const item of llmChat) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    const id = String(row.id ?? "");
    const skipped = Boolean(row.skipped);
    const ok = Boolean(row.ok);
    const preview = String(row.preview ?? "").slice(0, 100);
    let result: DiagResultRow["result"];
    let hint: string;
    if (skipped) {
      result = "skip";
      hint = String(row.detail ?? "跳过");
    } else {
      result = ok ? "pass" : "fail";
      hint = ok ? (preview ? `有回复：${preview}` : "已返回内容") : String(row.detail ?? "调用失败");
    }
    rows.push({
      label: `对话 · ${PROVIDER_SLOT_LABEL[id] || id}`,
      result,
      hint,
    });
  }
  const def = j.litellm_default as Record<string, unknown> | null | undefined;
  if (def && typeof def === "object") {
    const skipped = Boolean(def.skipped);
    const ok = Boolean(def.ok);
    const preview = String(def.preview ?? "").slice(0, 120);
    rows.push({
      label: "对话 · 默认模型（网关）",
      result: skipped ? "skip" : ok ? "pass" : "fail",
      hint: skipped ? String(def.detail ?? "") : ok ? (preview ? preview : "成功") : String(def.detail ?? ""),
    });
  }
  return rows;
}

function extractBullets(text: string, k = 4): string[] {
  const lines = String(text || "")
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
  const items = lines
    .map((l) => l.replace(/^(\-|\*|\d+[\.\)]|•)\s+/, "").trim())
    .filter((l) => l.length >= 4);
  const uniq: string[] = [];
  for (const it of items) {
    if (!uniq.includes(it)) uniq.push(it);
    if (uniq.length >= k) break;
  }
  return uniq;
}

export function DecisionHub() {
  /** 与后端通信的根地址；可在「连接设置」中写入本机浏览器 localStorage 覆盖默认值。 */
  const [backendBase, setBackendBase] = useState("http://127.0.0.1:8000");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsDraft, setSettingsDraft] = useState("");
  const [settingsMsg, setSettingsMsg] = useState<string | null>(null);
  const [hubServer, setHubServer] = useState<Record<string, string>>(() => emptyHubForm());
  const [hubServerBusy, setHubServerBusy] = useState(false);
  const hubBaselineRef = useRef<Record<string, string>>(emptyHubForm());
  /** Full persisted map dept_id -> LiteLLM model override (empty = use default). */
  const [hubDeptModels, setHubDeptModels] = useState<Record<string, string>>({});
  const hubDeptModelsBaselineRef = useRef<Record<string, string>>({});
  const [hubAiProfiles, setHubAiProfiles] = useState<HubAiProfileRow[]>([]);
  const hubAiProfilesBaselineRef = useRef<HubAiProfileRow[]>([]);
  /** dept_id -> ai profile id (optional); overrides manual model when set. */
  const [hubDeptAiProfile, setHubDeptAiProfile] = useState<Record<string, string>>({});
  const hubDeptAiProfileBaselineRef = useRef<Record<string, string>>({});
  const [hubDeptRouting, setHubDeptRouting] = useState<HubDeptRoutingPayload | null>(null);
  const [hubDiagBusy, setHubDiagBusy] = useState<"conn" | "chat" | null>(null);
  const [hubDiagConnectivity, setHubDiagConnectivity] = useState<unknown>(null);
  const [hubDiagChat, setHubDiagChat] = useState<unknown>(null);
  /** Backend-resolved absolute path to hub_settings.json (exe 旁 data 目录或开发 backend/data). */
  const [hubSettingsPathResolved, setHubSettingsPathResolved] = useState("");
  const [hubDiagShowTechnical, setHubDiagShowTechnical] = useState(false);

  /** 当前业务类型（mode_id）下各部门「基因」提示词 — 在系统设置中加载/编辑/AI 生成 */
  const [geneTeams, setGeneTeams] = useState<Record<string, DeptGeneTeam>>({});
  const [geneOverwrite, setGeneOverwrite] = useState(true);
  const [geneBusy, setGeneBusy] = useState(false);
  const [geneGenBusy, setGeneGenBusy] = useState(false);
  const [geneRoleDialog, setGeneRoleDialog] = useState<{ dept: string; slot: GeneRoleSlot } | null>(null);
  const [geneRolePreference, setGeneRolePreference] = useState("");
  const [geneSlotBusy, setGeneSlotBusy] = useState<string | null>(null);

  const [modes, setModes] = useState<ModeInfo[]>([]);
  const [modeId, setModeId] = useState("program_management");
  const [task, setTask] = useState("");
  const [rejectUnknownMode, setRejectUnknownMode] = useState(false);

  const [decisionId, setDecisionId] = useState("");
  const [running, setRunning] = useState(false);
  const [deptRows, setDeptRows] = useState<DeptRuntime[]>([]);
  const [latestSummary, setLatestSummary] = useState<DecisionSummary | null>(null);
  const [history, setHistory] = useState<DecisionSummary[]>([]);

  const [contextOpen, setContextOpen] = useState(false);
  const [attachedNames, setAttachedNames] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const [selectedDepts, setSelectedDepts] = useState<Set<string>>(new Set());
  const [rejectReason, setRejectReason] = useState("");
  const [confirmMenuOpen, setConfirmMenuOpen] = useState(false);
  const [outcome, setOutcome] = useState<"open" | "archived" | "exec_doc" | "gold_sop" | "rejected">("open");
  const [outcomeNote, setOutcomeNote] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, []);

  useEffect(() => {
    setBackendBase(resolveBackendHttpBase());
    setSettingsDraft(resolveBackendHttpBase());
  }, []);

  const currentMode = useMemo(() => modes.find((m) => m.mode_id === modeId), [modes, modeId]);
  const deptLabels = useMemo(() => currentMode?.department_labels ?? {}, [currentMode]);

  const initDeptRows = useCallback(() => {
    const depts = currentMode?.departments?.length ? currentMode.departments : [];
    setDeptRows(
      depts.map((d) => ({
        dept: d,
        label: deptLabels[d] || d,
        phase: "running",
        lamp: "ok",
        caption: "正在形成部门意见…",
        focusRank: 0,
      })),
    );
  }, [currentMode?.departments, deptLabels]);

  useEffect(() => {
    void (async () => {
      const res = await fetchWithTimeout(`${backendBase}/api/modes`);
      const data = (await res.json()) as ModeInfo[];
      setModes(data);
      setModeId((prev) => (data.find((m) => m.mode_id === prev) ? prev : data[0]?.mode_id || prev));
    })();
  }, [backendBase]);

  useEffect(() => {
    loadHistory().catch(() => {});
    const m = modes.find((x) => x.mode_id === modeId);
    if (m?.default_task_hint && !task.trim()) {
      setTask(m.default_task_hint);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modeId, modes, backendBase]);

  useEffect(() => {
    if (!settingsOpen) return;
    let cancelled = false;
    void (async () => {
      try {
        const q = modeId ? `?mode_id=${encodeURIComponent(modeId)}` : "";
        const res = await fetchWithTimeout(`${backendBase}/api/settings/hub${q}`, {}, 15_000);
        if (!res.ok) {
          if (!cancelled) setSettingsMsg(`无法加载服务端设置（HTTP ${res.status}）。请确认后端地址与 /api/settings/hub 已启用。`);
          return;
        }
        const data = (await res.json()) as {
          settings?: Record<string, unknown>;
          dept_routing?: HubDeptRoutingPayload | { error?: string };
          hub_settings_path?: string;
        };
        if (!cancelled && data.hub_settings_path) setHubSettingsPathResolved(data.hub_settings_path);
        if (!cancelled && data.settings) {
          const f = settingsResponseToForm(data.settings);
          setHubServer(f);
          hubBaselineRef.current = { ...f };
          const dm = parseDeptModelsMap(data.settings.dept_llm_models);
          setHubDeptModels(dm);
          hubDeptModelsBaselineRef.current = { ...dm };
          const ap = parseAiProfiles(data.settings.ai_profiles);
          setHubAiProfiles(ap);
          hubAiProfilesBaselineRef.current = [...ap];
          const dap = parseDeptModelsMap(data.settings.dept_ai_profile);
          setHubDeptAiProfile(dap);
          hubDeptAiProfileBaselineRef.current = { ...dap };
        }
        if (!cancelled && data.dept_routing && typeof data.dept_routing === "object" && "rows" in data.dept_routing) {
          setHubDeptRouting(data.dept_routing as HubDeptRoutingPayload);
        } else if (!cancelled) {
          setHubDeptRouting(null);
        }
      } catch (e) {
        if (!cancelled) setSettingsMsg(`加载服务端设置失败：${e instanceof Error ? e.message : String(e)}`);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [settingsOpen, backendBase, modeId]);

  async function loadHistory() {
    try {
      const res = await fetchWithTimeout(`${backendBase}/api/memory/${encodeURIComponent(modeId)}?limit=12&compact=1`);
      if (!res.ok) return;
      const data = (await res.json()) as DecisionSummary[];
      setHistory(data.reverse());
    } catch {
      // ignore
    }
  }

  function applyHistoryTask(h: DecisionSummary) {
    const t = h.task || "";
    setTask((prev) => {
      const head = prev.trim() ? `${prev.trim()}\n\n` : "";
      return `${head}—— 引用历史决策（${h.created_at || h.decision_id || "未命名"}）——\n${t}`;
    });
    setContextOpen(false);
  }

  function onFilesPicked(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files?.length) return;
    setAttachedNames(Array.from(files).map((f) => f.name));
  }

  const overallPct = useMemo(() => {
    if (!deptRows.length) return 0;
    const done = deptRows.filter((r) => r.phase === "done").length;
    if (!running && latestSummary) return 100;
    return Math.min(95, Math.round((done / deptRows.length) * 95));
  }, [deptRows, running, latestSummary]);

  const sortedDeptRows = useMemo(() => {
    return [...deptRows].sort((a, b) => b.focusRank - a.focusRank || a.label.localeCompare(b.label, "zh-CN"));
  }, [deptRows]);

  async function start() {
    if (!task.trim()) return;
    setLatestSummary(null);
    setOutcome("open");
    setOutcomeNote(null);
    setSelectedDepts(new Set());
    setRejectReason("");
    setDecisionId("");
    setRunning(true);
    initDeptRows();

    let bodyTask = task.trim();
    if (attachedNames.length) {
      bodyTask += `\n\n【参考附件】${attachedNames.join("、")}`;
    }

    const res = await fetchWithTimeout(
      `${backendBase}/api/decision/start`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task: bodyTask, mode_id: modeId, reject_unknown_mode: rejectUnknownMode }),
      },
      TIMEOUT_MS.decisionStart,
    );
    if (!res.ok) {
      setRunning(false);
      setDeptRows([]);
      setOutcomeNote("无法启动本轮决策，请检查网络或稍后重试。");
      return;
    }
    const data = (await res.json()) as { decision_id: string };
    setDecisionId(data.decision_id);

    wsRef.current?.close();
    const ws = new WebSocket(`${httpToWsOrigin(backendBase)}/api/decision/stream/${data.decision_id}`);
    wsRef.current = ws;
    ws.onmessage = (msg) => {
      try {
        const evt = JSON.parse(msg.data) as StreamEvent;
        if (evt.type === "dept_done") {
          const payload = evt.payload as { dept?: string; report?: DeptReport };
          const dept = String(payload.dept || payload.report?.dept || "");
          const rep = payload.report || {};
          const c = Number(rep.confidence_score ?? 0.7);
          const d = Number(rep.dissent_intensity ?? 0.2);
          const al = alertFromScores(c, d);
          const { lamp, caption } = lampLabel(al, c);
          const fr = focusRankFrom(al, c);
          setDeptRows((rows) =>
            rows.map((row) =>
              row.dept === dept
                ? {
                    ...row,
                    phase: "done",
                    lamp,
                    caption,
                    focusRank: fr,
                  }
                : row,
            ),
          );
        }
        if (evt.type === "decision_done") {
          setRunning(false);
          loadHistory().catch(() => {});
          const summary = (evt.payload as { summary?: DecisionSummary })?.summary;
          if (summary?.heatmap?.length) {
            const map = new Map(summary.heatmap.map((h) => [String(h.dept || ""), h]));
            setDeptRows((rows) =>
              rows.map((row) => {
                const h = map.get(row.dept);
                if (!h) return { ...row, phase: "done" as const };
                const c = Number(h.confidence_score ?? 0.7);
                const d = Number(h.dissent_intensity ?? 0.2);
                const al = (h.alert as "green" | "yellow" | "red") || alertFromScores(c, d);
                const { lamp, caption } = lampLabel(al, c);
                return {
                  ...row,
                  phase: "done",
                  lamp,
                  caption,
                  focusRank: focusRankFrom(al, c),
                };
              }),
            );
          }
          if (summary) setLatestSummary(summary);
        }
      } catch {
        // ignore
      }
    };
    ws.onerror = () => {
      setOutcomeNote("连接中断，若结果未出请重新发起。");
    };
  }

  function toggleDeptSelect(d: string) {
    setSelectedDepts((prev) => {
      const next = new Set(prev);
      if (next.has(d)) next.delete(d);
      else next.add(d);
      return next;
    });
  }

  function finalizeConfirm(kind: "archived" | "exec_doc" | "gold_sop") {
    setOutcome(kind);
    setConfirmMenuOpen(false);
    const labels = {
      archived: "已确认并归档（结论已记录在本系统）。",
      exec_doc: "已确认：将生成执行文档（后续版本将自动对接下游流程）。",
      gold_sop: "已确认：已标记为黄金 SOP 候选（后续版本将支持一键沉淀模板）。",
    };
    setOutcomeNote(labels[kind]);
  }

  function finalizeReject() {
    if (!rejectReason.trim()) {
      setOutcomeNote("请填写驳回原因。");
      return;
    }
    setOutcome("rejected");
    setOutcomeNote(`已驳回：${rejectReason.trim()}`);
  }

  function partialRerunHint() {
    if (!selectedDepts.size) {
      setOutcomeNote("请先在下方部门卡片勾选需要重评的部门。");
      return;
    }
    setOutcomeNote(
      "「仅重评所选部门」需后端协同接口；当前建议：将不满意部门的要点复制到任务描述中，重新点击「开始决策」；工程排期请见开发者面板说明。",
    );
  }

  async function testBackendConnection() {
    setSettingsMsg(null);
    try {
      const url = normalizeBackendUrl(settingsDraft || backendBase);
      new URL(url.includes("://") ? url : `http://${url}`);
      const res = await fetchWithTimeout(`${url}/api/health`, {}, 8000);
      const ok = res.ok;
      const j = ok ? ((await res.json()) as Record<string, unknown>) : null;
      setSettingsMsg(ok ? `连接正常（${url}）：${JSON.stringify(j)}` : `无法访问（HTTP ${res.status}）：${url}`);
    } catch (e) {
      setSettingsMsg(`连接失败：${e instanceof Error ? e.message : String(e)}`);
    }
  }

  function saveBackendUrl() {
    setSettingsMsg(null);
    try {
      const raw = settingsDraft.trim();
      if (!raw) {
        setSettingsMsg("请先填写服务地址。");
        return;
      }
      const url = normalizeBackendUrl(raw.includes("://") ? raw : `http://${raw}`);
      new URL(url);
      window.localStorage.setItem(HSEMAS_BACKEND_STORAGE_KEY, url);
      setBackendBase(url);
      setSettingsDraft(url);
      setSettingsMsg("已保存。下方业务类型将随新地址自动刷新。");
    } catch {
      setSettingsMsg("地址格式不正确，示例：http://127.0.0.1:8000");
    }
  }

  function clearSavedBackendUrl() {
    setSettingsMsg(null);
    try {
      window.localStorage.removeItem(HSEMAS_BACKEND_STORAGE_KEY);
    } catch {
      // ignore
    }
    const next = resolveBackendHttpBaseIgnoringStorage();
    setBackendBase(next);
    setSettingsDraft(next);
    setSettingsMsg("已清除本机保存的地址，恢复默认/构建时配置。");
  }

  function setHubField(key: string, value: string) {
    setHubServer((prev) => ({ ...prev, [key]: value }));
  }

  function setHubDeptModelField(deptId: string, value: string) {
    setHubDeptModels((prev) => ({ ...prev, [deptId]: value }));
  }

  function setHubDeptAiProfileField(deptId: string, profileId: string) {
    setHubDeptAiProfile((prev) => ({ ...prev, [deptId]: profileId }));
  }

  function updateAiProfileRow(index: number, patch: Partial<HubAiProfileRow>) {
    setHubAiProfiles((rows) => rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  function addAiProfileRow() {
    setHubAiProfiles((rows) => [...rows, { id: `brand_${rows.length + 1}`, label: "新品牌", model: hubServer.litellm_default_model || "gpt-4o-mini" }]);
  }

  function removeAiProfileRow(index: number) {
    setHubAiProfiles((rows) => rows.filter((_, i) => i !== index));
  }

  const connectivitySummaryRows = useMemo(() => buildConnectivitySummary(hubDiagConnectivity), [hubDiagConnectivity]);
  const chatSummaryRows = useMemo(() => buildChatSummary(hubDiagChat), [hubDiagChat]);

  const deptRoutingRows: HubDeptRoutingRow[] = useMemo(() => {
    if (hubDeptRouting?.rows?.length) return hubDeptRouting.rows;
    const m = modes.find((x) => x.mode_id === modeId);
    if (!m) return [];
    const def = (hubServer.litellm_default_model || "").trim() || "gpt-4o-mini";
    return m.departments.map((d) => {
      const ov = (hubDeptModels[d] ?? "").trim();
      const pid = (hubDeptAiProfile[d] ?? "").trim();
      let profModel: string | null = null;
      let profLabel: string | null = null;
      if (pid) {
        const pr = hubAiProfiles.find((x) => x.id === pid);
        if (pr) {
          profModel = pr.model.trim() || null;
          profLabel = pr.label || null;
        }
      }
      const resolved = profModel || ov || def;
      let source = "default";
      if (pid && profModel) source = "profile";
      else if (ov) source = "override";
      return {
        dept_id: d,
        label: m.department_labels?.[d] || d,
        ai_profile_id: pid || null,
        ai_profile_label: profLabel,
        override_model: ov || null,
        resolved_model: resolved,
        source,
      };
    });
  }, [hubDeptRouting, modes, modeId, hubDeptModels, hubDeptAiProfile, hubAiProfiles, hubServer.litellm_default_model]);

  const loadGeneTeams = useCallback(async () => {
    if (!modeId) return;
    try {
      const res = await fetchWithTimeout(`${backendBase}/api/genes/${encodeURIComponent(modeId)}/teams`, {}, 30_000);
      if (!res.ok) return;
      const data = (await res.json()) as { teams?: Record<string, Partial<DeptGeneTeam>> };
      const raw = data.teams ?? {};
      const next: Record<string, DeptGeneTeam> = {};
      for (const [d, t] of Object.entries(raw)) {
        const base = emptyDeptGeneTeam();
        for (const row of GENE_SLOT_ROWS) {
          const slot = row.id;
          const r = t?.[slot];
          if (r && typeof r === "object") {
            base[slot] = {
              role_title: String((r as GeneRole).role_title ?? ""),
              persona_prompt: String((r as GeneRole).persona_prompt ?? ""),
            };
          }
        }
        next[d] = base;
      }
      setGeneTeams(next);
    } catch {
      /* ignore */
    }
  }, [backendBase, modeId]);

  useEffect(() => {
    if (!settingsOpen) return;
    void loadGeneTeams();
  }, [settingsOpen, loadGeneTeams]);

  async function saveGeneTeamsAll() {
    setGeneBusy(true);
    setSettingsMsg(null);
    try {
      const res = await fetchWithTimeout(
        `${backendBase}/api/genes/${encodeURIComponent(modeId)}/teams`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ teams: geneTeams }),
        },
        120_000,
      );
      const raw = await res.text();
      let data: { saved?: number; errors?: string[] } = {};
      try {
        data = raw ? JSON.parse(raw) : {};
      } catch {
        data = {};
      }
      if (!res.ok) {
        setSettingsMsg(`保存部门团队失败（HTTP ${res.status}）。`);
        return;
      }
      let msg = `已保存 ${data.saved ?? 0} 个部门的 3+1 团队（业务类型：${currentMode?.label ?? modeId}）。`;
      if (data.errors?.length) msg += ` 提示：${data.errors.join("；")}`;
      setSettingsMsg(msg);
    } catch (e) {
      setSettingsMsg(`保存异常：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setGeneBusy(false);
    }
  }

  async function generateGenePromptsAll() {
    setGeneGenBusy(true);
    setSettingsMsg(null);
    try {
      const res = await fetchWithTimeout(
        `${backendBase}/api/genes/${encodeURIComponent(modeId)}/generate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ overwrite: geneOverwrite }),
        },
        300_000,
      );
      if (!res.ok) {
        const raw = await res.text();
        setSettingsMsg(`AI 生成失败（HTTP ${res.status}）：${raw.slice(0, 240)}`);
        return;
      }
      await loadGeneTeams();
      setSettingsMsg(
        `已按 CEO 逻辑为各部门生成 3+1 微型团队（${geneOverwrite ? "已覆盖" : "已跳过非空部门"}）。`,
      );
    } catch (e) {
      setSettingsMsg(`AI 生成异常：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setGeneGenBusy(false);
    }
  }

  function updateGeneTeamField(dept: string, slot: GeneRoleSlot, field: keyof GeneRole, value: string) {
    setGeneTeams((prev) => {
      const t = { ...(prev[dept] ?? emptyDeptGeneTeam()) };
      t[slot] = { ...t[slot], [field]: value };
      return { ...prev, [dept]: t };
    });
  }

  async function confirmRegenerateGeneRole() {
    if (!geneRoleDialog) return;
    const { dept, slot } = geneRoleDialog;
    const key = `${dept}:${slot}`;
    setGeneSlotBusy(key);
    setSettingsMsg(null);
    try {
      const res = await fetchWithTimeout(
        `${backendBase}/api/genes/${encodeURIComponent(modeId)}/${encodeURIComponent(dept)}/team/regenerate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slot, preference: geneRolePreference }),
        },
        120_000,
      );
      const raw = await res.text();
      let data: { ok?: boolean; record?: { team?: DeptGeneTeam } } = {};
      try {
        data = raw ? JSON.parse(raw) : {};
      } catch {
        data = {};
      }
      if (!res.ok) {
        setSettingsMsg(`重新生成职能失败（HTTP ${res.status}）：${raw.slice(0, 200)}`);
        return;
      }
      const team = data.record?.team as Partial<DeptGeneTeam> | undefined;
      if (team) {
        setGeneTeams((prev) => {
          const base = { ...(prev[dept] ?? emptyDeptGeneTeam()) };
          for (const row of GENE_SLOT_ROWS) {
            const s = row.id;
            const r = team[s];
            if (r && typeof r === "object") {
              base[s] = {
                role_title: String((r as GeneRole).role_title ?? ""),
                persona_prompt: String((r as GeneRole).persona_prompt ?? ""),
              };
            }
          }
          return { ...prev, [dept]: base };
        });
      } else {
        await loadGeneTeams();
      }
      setGeneRoleDialog(null);
      setGeneRolePreference("");
      setSettingsMsg("已重新生成该席位人设（可继续编辑后点「保存」）。");
    } catch (e) {
      setSettingsMsg(`重新生成异常：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setGeneSlotBusy(null);
    }
  }

  async function runHubDiagnosticsConnectivity() {
    setHubDiagBusy("conn");
    setSettingsMsg(null);
    try {
      const res = await fetchWithTimeout(`${backendBase}/api/settings/hub/diagnostics/connectivity`, { method: "POST" }, 60_000);
      const j = await res.json().catch(() => ({}));
      setHubDiagConnectivity(j);
      setSettingsMsg(res.ok ? "① 连通性检测已完成（见下表）。" : `① 检测失败 HTTP ${res.status}`);
    } catch (e) {
      setHubDiagConnectivity(null);
      setSettingsMsg(`① 检测异常：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setHubDiagBusy(null);
    }
  }

  async function runHubDiagnosticsChat() {
    setHubDiagBusy("chat");
    setSettingsMsg(null);
    try {
      const res = await fetchWithTimeout(`${backendBase}/api/settings/hub/diagnostics/chat`, { method: "POST" }, 120_000);
      const j = await res.json().catch(() => ({}));
      setHubDiagChat(j);
      setSettingsMsg(res.ok ? "② 回复探测已完成（可能产生少量费用；见下表）。" : `② 探测失败 HTTP ${res.status}`);
    } catch (e) {
      setHubDiagChat(null);
      setSettingsMsg(`② 探测异常：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setHubDiagBusy(null);
    }
  }

  async function saveHubServerSettings() {
    setHubServerBusy(true);
    setSettingsMsg(null);
    try {
      const diff = hubDiffPayload(hubServer, hubBaselineRef.current);
      const deptPatch = deptModelsPatch(hubDeptModels, hubDeptModelsBaselineRef.current);
      const deptAiPatch = deptModelsPatch(hubDeptAiProfile, hubDeptAiProfileBaselineRef.current);
      const profilesDirty = JSON.stringify(hubAiProfiles) !== JSON.stringify(hubAiProfilesBaselineRef.current);
      const body: Record<string, unknown> = { ...diff };
      if (deptPatch) body.dept_llm_models = deptPatch;
      if (deptAiPatch) body.dept_ai_profile = deptAiPatch;
      if (profilesDirty) body.ai_profiles = hubAiProfiles;
      if (Object.keys(body).length === 0) {
        setSettingsMsg("没有检测到变更，无需保存。");
        setHubServerBusy(false);
        return;
      }
      const res = await fetchWithTimeout(
        `${backendBase}/api/settings/hub`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        45_000,
      );
      const raw = await res.text();
      let data: { ok?: boolean; detail?: string; settings?: Record<string, unknown>; hub_settings_path?: string } = {};
      try {
        data = raw ? JSON.parse(raw) : {};
      } catch {
        data = {};
      }
      if (!res.ok) {
        setSettingsMsg(`保存失败（HTTP ${res.status}）：${String(data.detail || raw || "unknown")}`);
        return;
      }
      if (data.settings) {
        const f = settingsResponseToForm(data.settings);
        setHubServer(f);
        hubBaselineRef.current = { ...f };
        const dm = parseDeptModelsMap(data.settings.dept_llm_models);
        setHubDeptModels(dm);
        hubDeptModelsBaselineRef.current = { ...dm };
        const ap = parseAiProfiles(data.settings.ai_profiles);
        setHubAiProfiles(ap);
        hubAiProfilesBaselineRef.current = [...ap];
        const dap = parseDeptModelsMap(data.settings.dept_ai_profile);
        setHubDeptAiProfile(dap);
        hubDeptAiProfileBaselineRef.current = { ...dap };
      }
      if (data.hub_settings_path) setHubSettingsPathResolved(data.hub_settings_path);
      setSettingsMsg("服务端 API 与模型配置已保存并生效（密钥行如为 *** 结尾表示未改动原值）。");
    } catch (e) {
      setSettingsMsg(`保存失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setHubServerBusy(false);
    }
  }

  const hubLocked = running;
  const showSummary = Boolean(latestSummary) && !running;

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#f6f7f9",
        color: "#1a1d21",
        padding: "24px 20px 48px",
        boxSizing: "border-box",
      }}
    >
      <div style={{ maxWidth: 1040, margin: "0 auto" }}>
        <header style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginBottom: 12, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 12, letterSpacing: "0.06em", color: "#5c6370", textTransform: "uppercase" }}>H-SEMAS</div>
            <h1 style={{ margin: "4px 0 0", fontSize: 22, fontWeight: 650, letterSpacing: "-0.02em" }}>业务决策中枢</h1>
            <div style={{ marginTop: 6, fontSize: 12, color: "#78909c", wordBreak: "break-all" }}>
              当前服务：<span style={{ color: "#37474f" }}>{backendBase}</span>
            </div>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
            <button
              type="button"
              onClick={() => {
                setSettingsOpen((v) => !v);
                setSettingsMsg(null);
                setSettingsDraft(backendBase);
              }}
              style={{
                fontSize: 13,
                padding: "8px 12px",
                borderRadius: 8,
                border: settingsOpen ? "1px solid #3949ab" : "1px solid #d5dbe3",
                background: settingsOpen ? "#eef0ff" : "#fff",
                color: "#283593",
                cursor: "pointer",
              }}
            >
              系统设置
            </button>
            <Link
              href="/legacy"
              style={{
                fontSize: 13,
                color: "#3d4f5f",
                textDecoration: "none",
                padding: "8px 12px",
                borderRadius: 8,
                border: "1px solid #d5dbe3",
                background: "#fff",
              }}
            >
              开发者面板
            </Link>
          </div>
        </header>

        <div
          style={{
            marginBottom: 14,
            padding: "10px 14px",
            borderRadius: 10,
            border: "1px solid #c5cae9",
            background: "#f8f9ff",
            fontSize: 13,
            color: "#1a237e",
            lineHeight: 1.5,
          }}
        >
          <strong>配置 API：</strong>请点击右上角「<strong>系统设置</strong>」填写后端地址、LiteLLM、模型 Key、Qdrant、外搜等（与 Hub 项目一致）。若此处没有「系统设置」按钮，说明当前为<strong>旧版界面</strong>，请重新运行打包脚本生成新的 <code style={{ fontSize: 12 }}>h-semas.exe</code> 或强制刷新缓存（Ctrl+F5）。
        </div>

        {settingsOpen ? (
          <section
            style={{
              background: "#fff",
              borderRadius: 12,
              border: "1px solid #e6e9ef",
              padding: 16,
              marginBottom: 16,
              boxShadow: "0 1px 2px rgba(16,24,40,0.04)",
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>一、前端 → 后端地址</div>
            <p style={{ margin: "0 0 12px", fontSize: 12, color: "#5c6370", lineHeight: 1.55 }}>
              填写<strong>本浏览器访问的 API 根地址</strong>（与全渠道客服项目一致：前端只认一个 Base URL），保存在本机浏览器。下方「服务端 API」写入后端磁盘上的{" "}
              <code style={{ fontSize: 11 }}>hub_settings.json</code>
              {hubSettingsPathResolved ? (
                <>
                  ，当前解析路径为：
                  <span style={{ wordBreak: "break-all", color: "#37474f" }}> {hubSettingsPathResolved}</span>
                </>
              ) : (
                <>（打开本节时会从服务器读取绝对路径）</>
              )}
              <br />
              使用打包的 <code style={{ fontSize: 11 }}>h-semas.exe</code> 时，配置通常在与 exe 同目录的{" "}
              <code style={{ fontSize: 11 }}>data\hub_settings.json</code>，更换 exe 位置时请一并复制 <code style={{ fontSize: 11 }}>data</code> 文件夹。
            </p>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 6, color: "#455a64" }}>后端地址</label>
            <input
              value={settingsDraft}
              onChange={(e) => setSettingsDraft(e.target.value)}
              placeholder="http://127.0.0.1:8000"
              spellCheck={false}
              style={{
                width: "100%",
                maxWidth: 520,
                padding: "10px 12px",
                borderRadius: 8,
                border: "1px solid #d5dbe3",
                fontSize: 14,
                boxSizing: "border-box",
              }}
            />
            <div style={{ marginTop: 12, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              <button
                type="button"
                onClick={() => void testBackendConnection()}
                style={{
                  padding: "8px 14px",
                  borderRadius: 8,
                  border: "1px solid #3949ab",
                  background: "#fff",
                  color: "#283593",
                  fontWeight: 600,
                  cursor: "pointer",
                  fontSize: 13,
                }}
              >
                测试连接
              </button>
              <button
                type="button"
                onClick={saveBackendUrl}
                style={{
                  padding: "8px 14px",
                  borderRadius: 8,
                  border: "none",
                  background: "#1a237e",
                  color: "#fff",
                  fontWeight: 600,
                  cursor: "pointer",
                  fontSize: 13,
                }}
              >
                保存并应用
              </button>
              <button
                type="button"
                onClick={clearSavedBackendUrl}
                style={{
                  padding: "8px 14px",
                  borderRadius: 8,
                  border: "1px solid #cfd6e0",
                  background: "#fafbfc",
                  color: "#546e7a",
                  cursor: "pointer",
                  fontSize: 13,
                }}
              >
                清除本机保存
              </button>
            </div>

            <hr style={{ margin: "20px 0", border: "none", borderTop: "1px solid #eceff4" }} />

            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>二、服务端 API（LiteLLM / RAG / 外搜）</div>
            <p style={{ margin: "0 0 14px", fontSize: 12, color: "#5c6370", lineHeight: 1.55 }}>
              与常见「Hub 配置」相同：密钥行显示为 <code style={{ fontSize: 11 }}>***</code> 后四位表示已配置；不修改则保持原值。留空并保存表示清除该条覆盖（回退到{" "}
              <code style={{ fontSize: 11 }}>.env</code>）。生产环境请在服务器上关闭写入：环境变量{" "}
              <code style={{ fontSize: 11 }}>HSEMAS_HUB_SETTINGS_WRITE_ENABLED=false</code>。
            </p>

            <div style={{ display: "grid", gap: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#37474f" }}>LLM 网关</div>
              {[
                ["llm_provider", "提供商（须填 litellm 或 simulated）"],
                ["litellm_base_url", "LiteLLM / 代理 Base URL（可空）"],
                ["litellm_default_model", "默认模型"],
                ["litellm_fallback_models", "降级模型列表（逗号分隔）"],
                ["litellm_max_retries", "最大重试次数（整数）"],
                ["litellm_retry_base_ms", "重试间隔基数 ms（整数）"],
              ].map(([key, label]) => (
                <label key={key} style={{ display: "block", fontSize: 12 }}>
                  <span style={{ fontWeight: 600, color: "#455a64" }}>{label}</span>
                  <input
                    value={hubServer[key] ?? ""}
                    onChange={(e) => setHubField(key, e.target.value)}
                    type="text"
                    autoComplete="off"
                    spellCheck={false}
                    style={{
                      display: "block",
                      width: "100%",
                      maxWidth: 560,
                      marginTop: 4,
                      padding: "8px 10px",
                      borderRadius: 8,
                      border: "1px solid #d5dbe3",
                      fontSize: 13,
                      boxSizing: "border-box",
                    }}
                  />
                </label>
              ))}

              <div style={{ fontSize: 12, fontWeight: 700, color: "#37474f", marginTop: 4 }}>API 密钥（写入进程 + 同步到常见环境变量名）</div>
              {[
                ["openai_api_key", "OpenAI / 兼容"],
                ["anthropic_api_key", "Anthropic"],
                ["gemini_api_key", "Gemini（同步 GEMINI_API_KEY / GOOGLE_API_KEY）"],
                ["deepseek_api_key", "DeepSeek"],
                ["doubao_api_key", "豆包"],
              ].map(([key, label]) => (
                <label key={key} style={{ display: "block", fontSize: 12 }}>
                  <span style={{ fontWeight: 600, color: "#455a64" }}>{label}</span>
                  <input
                    value={hubServer[key] ?? ""}
                    onChange={(e) => setHubField(key, e.target.value)}
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    style={{
                      display: "block",
                      width: "100%",
                      maxWidth: 560,
                      marginTop: 4,
                      padding: "8px 10px",
                      borderRadius: 8,
                      border: "1px solid #d5dbe3",
                      fontSize: 13,
                      boxSizing: "border-box",
                    }}
                  />
                </label>
              ))}

              <div style={{ fontSize: 12, fontWeight: 700, color: "#37474f", marginTop: 4 }}>向量检索 RAG</div>
              {[
                ["rag_backend", "RAG 后端 simulated | local | qdrant"],
                ["qdrant_url", "Qdrant URL"],
                ["qdrant_api_key", "Qdrant API Key"],
                ["litellm_embedding_model", "Embedding 模型名（可空=哈希向量）"],
                ["embedding_vector_dim", "向量维度覆盖（整数，可空）"],
              ].map(([key, label]) => (
                <label key={key} style={{ display: "block", fontSize: 12 }}>
                  <span style={{ fontWeight: 600, color: "#455a64" }}>{label}</span>
                  <input
                    value={hubServer[key] ?? ""}
                    onChange={(e) => setHubField(key, e.target.value)}
                    type={key === "qdrant_api_key" ? "password" : "text"}
                    autoComplete="off"
                    spellCheck={false}
                    style={{
                      display: "block",
                      width: "100%",
                      maxWidth: 560,
                      marginTop: 4,
                      padding: "8px 10px",
                      borderRadius: 8,
                      border: "1px solid #d5dbe3",
                      fontSize: 13,
                      boxSizing: "border-box",
                    }}
                  />
                </label>
              ))}
              <label style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 12, color: "#455a64" }}>
                <input
                  type="checkbox"
                  checked={hubServer.rag_hybrid_local_fts === "true"}
                  onChange={(e) => setHubField("rag_hybrid_local_fts", e.target.checked ? "true" : "false")}
                />
                RAG 混合本地全文（rag_hybrid_local_fts）
              </label>

              <div style={{ fontSize: 12, fontWeight: 700, color: "#37474f", marginTop: 4 }}>外搜（benchmark / xlab）</div>
              <label style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 12, color: "#455a64" }}>
                <input
                  type="checkbox"
                  checked={hubServer.benchmark_web_search === "true"}
                  onChange={(e) => setHubField("benchmark_web_search", e.target.checked ? "true" : "false")}
                />
                启用外搜 benchmark_web_search
              </label>
              {[
                ["tavily_api_key", "Tavily API Key"],
                ["exa_api_key", "Exa API Key"],
              ].map(([key, label]) => (
                <label key={key} style={{ display: "block", fontSize: 12 }}>
                  <span style={{ fontWeight: 600, color: "#455a64" }}>{label}</span>
                  <input
                    value={hubServer[key] ?? ""}
                    onChange={(e) => setHubField(key, e.target.value)}
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    style={{
                      display: "block",
                      width: "100%",
                      maxWidth: 560,
                      marginTop: 4,
                      padding: "8px 10px",
                      borderRadius: 8,
                      border: "1px solid #d5dbe3",
                      fontSize: 13,
                      boxSizing: "border-box",
                    }}
                  />
                </label>
              ))}
            </div>

            <hr style={{ margin: "20px 0", border: "none", borderTop: "1px solid #eceff4" }} />

            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>API 分步检测（逐项）</div>
            <p style={{ margin: "0 0 12px", fontSize: 12, color: "#5c6370", lineHeight: 1.55 }}>
              ① 连通性：Qdrant、LiteLLM 代理、外搜、各密钥槽位与网络可达性（不强制消耗大模型 token）。②
              回复：对已配置的每个供应商各发一条极短补全（可能产生少量费用）。当前业务类型为 <strong>{modeId}</strong>，与下方「部门路由」一致。
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
              <button
                type="button"
                disabled={hubDiagBusy !== null || hubServerBusy}
                onClick={() => void runHubDiagnosticsConnectivity()}
                style={{
                  padding: "8px 14px",
                  borderRadius: 8,
                  border: "1px solid #3949ab",
                  background: "#fff",
                  color: "#283593",
                  fontWeight: 600,
                  cursor: hubDiagBusy || hubServerBusy ? "wait" : "pointer",
                  fontSize: 13,
                }}
              >
                {hubDiagBusy === "conn" ? "① 检测中…" : "① 逐项检测连通"}
              </button>
              <button
                type="button"
                disabled={hubDiagBusy !== null || hubServerBusy}
                onClick={() => void runHubDiagnosticsChat()}
                style={{
                  padding: "8px 14px",
                  borderRadius: 8,
                  border: "1px solid #6a1b9a",
                  background: "#faf5ff",
                  color: "#4a148c",
                  fontWeight: 600,
                  cursor: hubDiagBusy || hubServerBusy ? "wait" : "pointer",
                  fontSize: 13,
                }}
              >
                {hubDiagBusy === "chat" ? "② 探测中…" : "② 逐项检测回复"}
              </button>
            </div>
            {hubDiagConnectivity ? (
              <div style={{ margin: "0 0 14px" }}>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: "#37474f" }}>① 连通性结果</div>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, marginBottom: 8 }}>
                  <thead>
                    <tr style={{ color: "#455a64", textAlign: "left" }}>
                      <th style={{ padding: "6px 8px", borderBottom: "1px solid #eceff4", width: "34%" }}>检测项</th>
                      <th style={{ padding: "6px 8px", borderBottom: "1px solid #eceff4", width: "14%" }}>结果</th>
                      <th style={{ padding: "6px 8px", borderBottom: "1px solid #eceff4" }}>说明</th>
                    </tr>
                  </thead>
                  <tbody>
                    {connectivitySummaryRows.map((r, i) => {
                      const b = diagBadgeStyle(r.result);
                      return (
                        <tr key={`c-${i}`}>
                          <td style={{ padding: "8px", borderBottom: "1px solid #f0f2f5", verticalAlign: "top" }}>{r.label}</td>
                          <td style={{ padding: "8px", borderBottom: "1px solid #f0f2f5", verticalAlign: "top" }}>
                            <span
                              style={{
                                display: "inline-block",
                                padding: "2px 8px",
                                borderRadius: 6,
                                fontWeight: 600,
                                fontSize: 11,
                                color: b.fg,
                                background: b.bg,
                              }}
                            >
                              {b.text}
                            </span>
                          </td>
                          <td style={{ padding: "8px", borderBottom: "1px solid #f0f2f5", color: "#546e7a", lineHeight: 1.45 }}>{r.hint}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : null}
            {hubDiagChat ? (
              <div style={{ margin: "0 0 14px" }}>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: "#37474f" }}>② 对话回复结果</div>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, marginBottom: 8 }}>
                  <thead>
                    <tr style={{ color: "#455a64", textAlign: "left" }}>
                      <th style={{ padding: "6px 8px", borderBottom: "1px solid #eceff4", width: "34%" }}>检测项</th>
                      <th style={{ padding: "6px 8px", borderBottom: "1px solid #eceff4", width: "14%" }}>结果</th>
                      <th style={{ padding: "6px 8px", borderBottom: "1px solid #eceff4" }}>说明</th>
                    </tr>
                  </thead>
                  <tbody>
                    {chatSummaryRows.map((r, i) => {
                      const b = diagBadgeStyle(r.result);
                      return (
                        <tr key={`ch-${i}`}>
                          <td style={{ padding: "8px", borderBottom: "1px solid #f0f2f5", verticalAlign: "top" }}>{r.label}</td>
                          <td style={{ padding: "8px", borderBottom: "1px solid #f0f2f5", verticalAlign: "top" }}>
                            <span
                              style={{
                                display: "inline-block",
                                padding: "2px 8px",
                                borderRadius: 6,
                                fontWeight: 600,
                                fontSize: 11,
                                color: b.fg,
                                background: b.bg,
                              }}
                            >
                              {b.text}
                            </span>
                          </td>
                          <td style={{ padding: "8px", borderBottom: "1px solid #f0f2f5", color: "#546e7a", lineHeight: 1.45 }}>{r.hint}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : null}
            {Boolean(hubDiagConnectivity || hubDiagChat) ? (
              <div style={{ marginBottom: 12 }}>
                <button
                  type="button"
                  onClick={() => setHubDiagShowTechnical((v) => !v)}
                  style={{
                    padding: "6px 12px",
                    fontSize: 12,
                    borderRadius: 6,
                    border: "1px solid #cfd6e0",
                    background: "#fafbfc",
                    color: "#546e7a",
                    cursor: "pointer",
                  }}
                >
                  {hubDiagShowTechnical ? "隐藏技术详情（原始 JSON）" : "显示技术详情（原始 JSON）"}
                </button>
                {hubDiagShowTechnical ? (
                  <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
                    {hubDiagConnectivity ? (
                      <pre
                        style={{
                          margin: 0,
                          padding: 10,
                          borderRadius: 8,
                          background: "#f5f5f5",
                          border: "1px solid #e0e0e0",
                          fontSize: 11,
                          maxHeight: 200,
                          overflow: "auto",
                          lineHeight: 1.35,
                        }}
                      >
                        {JSON.stringify(hubDiagConnectivity, null, 2)}
                      </pre>
                    ) : null}
                    {hubDiagChat ? (
                      <pre
                        style={{
                          margin: 0,
                          padding: 10,
                          borderRadius: 8,
                          background: "#faf5ff",
                          border: "1px solid #e1bee7",
                          fontSize: 11,
                          maxHeight: 200,
                          overflow: "auto",
                          lineHeight: 1.35,
                        }}
                      >
                        {JSON.stringify(hubDiagChat, null, 2)}
                      </pre>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}

            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>三、AI 档案（多品牌 / 多模型）</div>
            <p style={{ margin: "0 0 10px", fontSize: 12, color: "#5c6370", lineHeight: 1.55 }}>
              先在下方表格中为每条线路填写<strong>档案 ID</strong>（英文/数字）、<strong>显示名称</strong>和<strong>LiteLLM 模型名</strong>（与网关路由一致，如{" "}
              <code style={{ fontSize: 11 }}>gpt-4o-mini</code>、<code style={{ fontSize: 11 }}>gemini/gemini-2.0-flash</code>
              ）。密钥仍使用上方各厂商槽位；模型名决定走哪条供应商。保存后写入{" "}
              <code style={{ fontSize: 11 }}>hub_settings.json</code> 的 <code style={{ fontSize: 11 }}>ai_profiles</code>。
            </p>
            <div style={{ overflowX: "auto", marginBottom: 14 }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "#455a64" }}>
                    <th style={{ padding: "6px 8px", borderBottom: "1px solid #eceff4" }}>档案 ID</th>
                    <th style={{ padding: "6px 8px", borderBottom: "1px solid #eceff4" }}>显示名称</th>
                    <th style={{ padding: "6px 8px", borderBottom: "1px solid #eceff4" }}>模型名（LiteLLM）</th>
                    <th style={{ padding: "6px 8px", borderBottom: "1px solid #eceff4", width: 72 }}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {hubAiProfiles.map((p, idx) => (
                    <tr key={`${p.id}-${idx}`}>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #f0f2f5" }}>
                        <input
                          value={p.id}
                          onChange={(e) => updateAiProfileRow(idx, { id: e.target.value })}
                          disabled={hubServerBusy}
                          spellCheck={false}
                          style={{ width: "100%", minWidth: 120, padding: "6px 8px", borderRadius: 6, border: "1px solid #d5dbe3", fontSize: 12 }}
                        />
                      </td>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #f0f2f5" }}>
                        <input
                          value={p.label}
                          onChange={(e) => updateAiProfileRow(idx, { label: e.target.value })}
                          disabled={hubServerBusy}
                          style={{ width: "100%", minWidth: 120, padding: "6px 8px", borderRadius: 6, border: "1px solid #d5dbe3", fontSize: 12 }}
                        />
                      </td>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #f0f2f5" }}>
                        <input
                          value={p.model}
                          onChange={(e) => updateAiProfileRow(idx, { model: e.target.value })}
                          disabled={hubServerBusy}
                          spellCheck={false}
                          style={{ width: "100%", minWidth: 200, padding: "6px 8px", borderRadius: 6, border: "1px solid #d5dbe3", fontSize: 12, fontFamily: "monospace" }}
                        />
                      </td>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #f0f2f5" }}>
                        <button
                          type="button"
                          disabled={hubServerBusy}
                          onClick={() => removeAiProfileRow(idx)}
                          style={{ fontSize: 11, padding: "4px 8px", cursor: hubServerBusy ? "wait" : "pointer" }}
                        >
                          删除
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button
              type="button"
              disabled={hubServerBusy}
              onClick={addAiProfileRow}
              style={{
                marginBottom: 18,
                padding: "6px 12px",
                fontSize: 12,
                borderRadius: 6,
                border: "1px solid #3949ab",
                background: "#fff",
                color: "#283593",
                cursor: hubServerBusy ? "wait" : "pointer",
              }}
            >
              + 添加 AI 档案
            </button>

            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>四、部门 → 选用 AI（当前业务类型）</div>
            <p style={{ margin: "0 0 10px", fontSize: 12, color: "#5c6370", lineHeight: 1.55 }}>
              每个部门可先在下拉中选<strong> AI 档案</strong>（优先使用档案里的模型名）；不选档案时再填「覆盖模型」。档案与手动模型均写入{" "}
              <code style={{ fontSize: 11 }}>hub_settings.json</code>（<code style={{ fontSize: 11 }}>dept_ai_profile</code> /{" "}
              <code style={{ fontSize: 11 }}>dept_llm_models</code>）。
            </p>
            <div style={{ overflowX: "auto", marginBottom: 8 }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "#455a64" }}>
                    <th style={{ padding: "6px 8px", borderBottom: "1px solid #eceff4" }}>部门 ID</th>
                    <th style={{ padding: "6px 8px", borderBottom: "1px solid #eceff4" }}>名称</th>
                    <th style={{ padding: "6px 8px", borderBottom: "1px solid #eceff4", minWidth: 200 }}>选用 AI 档案</th>
                    <th style={{ padding: "6px 8px", borderBottom: "1px solid #eceff4" }}>覆盖模型（可空）</th>
                    <th style={{ padding: "6px 8px", borderBottom: "1px solid #eceff4" }}>解析后模型</th>
                    <th style={{ padding: "6px 8px", borderBottom: "1px solid #eceff4" }}>来源</th>
                  </tr>
                </thead>
                <tbody>
                  {deptRoutingRows.map((row) => (
                    <tr key={row.dept_id}>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #f0f2f5", fontFamily: "monospace" }}>{row.dept_id}</td>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #f0f2f5" }}>{row.label}</td>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #f0f2f5" }}>
                        <select
                          value={hubDeptAiProfile[row.dept_id] ?? ""}
                          onChange={(e) => setHubDeptAiProfileField(row.dept_id, e.target.value)}
                          disabled={hubServerBusy}
                          style={{
                            width: "100%",
                            maxWidth: 280,
                            padding: "6px 8px",
                            borderRadius: 6,
                            border: "1px solid #d5dbe3",
                            fontSize: 12,
                            background: "#fff",
                          }}
                        >
                          <option value="">（不指定档案，用手动覆盖模型）</option>
                          {hubAiProfiles.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.label} — {p.model}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #f0f2f5" }}>
                        <input
                          value={hubDeptModels[row.dept_id] ?? ""}
                          onChange={(e) => setHubDeptModelField(row.dept_id, e.target.value)}
                          placeholder={hubServer.litellm_default_model || "默认模型"}
                          spellCheck={false}
                          disabled={hubServerBusy}
                          style={{
                            width: "100%",
                            minWidth: 160,
                            padding: "6px 8px",
                            borderRadius: 6,
                            border: "1px solid #d5dbe3",
                            fontSize: 12,
                            boxSizing: "border-box",
                          }}
                        />
                      </td>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #f0f2f5", color: "#37474f", fontFamily: "monospace", fontSize: 11 }}>
                        {row.resolved_model}
                      </td>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #f0f2f5", fontSize: 11 }}>
                        {row.source === "profile" ? "档案" : row.source === "override" ? "手动覆盖" : "默认"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, marginTop: 8 }}>五、业务人员提示词（3+1 微型团队 · 当前业务类型）</div>
            <p style={{ margin: "0 0 10px", fontSize: 12, color: "#5c6370", lineHeight: 1.55 }}>
              每个部门为<strong>成员 A / B / C + 部门主管 (Lead)</strong>：前三者由<strong>总 CEO（AI）</strong>分配互补职能并生成人设；Lead
              负责主持内部辩论，汇总「共识」与「无法调和的冲突」上报 CEO。与主界面所选业务类型（
              <code style={{ fontSize: 11 }}>{modeId}</code>
              {currentMode?.label ? ` · ${currentMode.label}` : ""}）对应。点「AI 一键生成」将按当前 Hub 与部门模型生成全套团队；职能后「更换职能」可填写倾向或留空由
              AI 自由生成。修改后请点「保存到服务端」。
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", marginBottom: 12 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, cursor: hubServerBusy || geneGenBusy ? "wait" : "pointer" }}>
                <input
                  type="checkbox"
                  checked={geneOverwrite}
                  disabled={hubServerBusy || geneGenBusy}
                  onChange={(e) => setGeneOverwrite(e.target.checked)}
                />
                生成时覆盖已有提示词
              </label>
              <button
                type="button"
                disabled={hubServerBusy || geneGenBusy || !modeId || !(currentMode?.departments?.length ?? 0)}
                onClick={() => void generateGenePromptsAll()}
                style={{
                  padding: "8px 14px",
                  fontSize: 12,
                  borderRadius: 6,
                  border: "1px solid #5c6bc0",
                  background: "#fff",
                  color: "#3949ab",
                  fontWeight: 600,
                  cursor: hubServerBusy || geneGenBusy ? "wait" : "pointer",
                }}
              >
                {geneGenBusy ? "AI 生成中…" : "AI 一键生成全部部门（3+1）"}
              </button>
              <button
                type="button"
                disabled={hubServerBusy || geneBusy}
                onClick={() => void saveGeneTeamsAll()}
                style={{
                  padding: "8px 14px",
                  fontSize: 12,
                  borderRadius: 6,
                  border: "none",
                  background: hubServerBusy || geneBusy ? "#b0bec5" : "#3949ab",
                  color: "#fff",
                  fontWeight: 600,
                  cursor: hubServerBusy || geneBusy ? "wait" : "pointer",
                }}
              >
                {geneBusy ? "保存中…" : "保存到服务端"}
              </button>
              <button
                type="button"
                disabled={hubServerBusy || geneBusy}
                onClick={() => void loadGeneTeams()}
                style={{
                  padding: "8px 12px",
                  fontSize: 12,
                  borderRadius: 6,
                  border: "1px solid #cfd8dc",
                  background: "#fff",
                  color: "#546e7a",
                  cursor: hubServerBusy || geneBusy ? "wait" : "pointer",
                }}
              >
                重新加载
              </button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              {(currentMode?.departments ?? []).map((d) => {
                const team = geneTeams[d] ?? emptyDeptGeneTeam();
                return (
                  <div
                    key={d}
                    style={{
                      border: "1px solid #e0e4ea",
                      borderRadius: 10,
                      padding: 12,
                      background: "#fafbfd",
                    }}
                  >
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10, color: "#263238" }}>
                      {deptLabels[d] || d}{" "}
                      <span style={{ fontWeight: 400, fontFamily: "monospace", color: "#78909c", fontSize: 11 }}>({d})</span>
                      <span style={{ marginLeft: 8, fontSize: 11, fontWeight: 400, color: "#607d8b" }}>· 3+1 微型团队</span>
                    </div>
                    {GENE_SLOT_ROWS.map((row) => {
                      const role = team[row.id];
                      return (
                        <div
                          key={row.id}
                          style={{
                            marginBottom: 12,
                            padding: 10,
                            borderRadius: 8,
                            background: "#fff",
                            border: "1px solid #eceff1",
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              flexWrap: "wrap",
                              alignItems: "center",
                              justifyContent: "space-between",
                              gap: 8,
                              marginBottom: 6,
                            }}
                          >
                            <div>
                              <span style={{ fontSize: 12, fontWeight: 600, color: "#37474f" }}>{row.label}</span>
                              <span style={{ fontSize: 11, color: "#90a4ae", marginLeft: 8 }}>{row.hint}</span>
                            </div>
                            <button
                              type="button"
                              disabled={hubServerBusy || !!geneSlotBusy || geneGenBusy}
                              onClick={() => {
                                setGeneRolePreference("");
                                setGeneRoleDialog({ dept: d, slot: row.id });
                              }}
                              style={{
                                fontSize: 11,
                                padding: "4px 10px",
                                borderRadius: 6,
                                border: "1px solid #5c6bc0",
                                background: "#fff",
                                color: "#3949ab",
                                cursor: hubServerBusy || geneSlotBusy || geneGenBusy ? "wait" : "pointer",
                              }}
                            >
                              更换职能
                            </button>
                          </div>
                          <input
                            value={role.role_title}
                            onChange={(e) => updateGeneTeamField(d, row.id, "role_title", e.target.value)}
                            disabled={hubServerBusy}
                            placeholder="职能名称（简短）"
                            style={{
                              width: "100%",
                              maxWidth: 420,
                              marginBottom: 6,
                              padding: "6px 8px",
                              borderRadius: 6,
                              border: "1px solid #d5dbe3",
                              fontSize: 12,
                            }}
                          />
                          <textarea
                            value={role.persona_prompt}
                            onChange={(e) => updateGeneTeamField(d, row.id, "persona_prompt", e.target.value)}
                            disabled={hubServerBusy}
                            spellCheck={false}
                            placeholder="职能人设提示词…"
                            style={{
                              width: "100%",
                              minHeight: 72,
                              padding: "8px 10px",
                              borderRadius: 8,
                              border: "1px solid #d5dbe3",
                              fontSize: 12,
                              lineHeight: 1.45,
                              boxSizing: "border-box",
                              fontFamily: "inherit",
                              resize: "vertical",
                            }}
                          />
                        </div>
                      );
                    })}
                  </div>
                );
              })}
              {!currentMode?.departments?.length ? (
                <div style={{ fontSize: 12, color: "#90a4ae" }}>请先确认业务类型已加载；若列表为空请检查后端 /api/modes。</div>
              ) : null}
            </div>

            {geneRoleDialog ? (
              <div
                style={{
                  position: "fixed",
                  inset: 0,
                  background: "rgba(0,0,0,0.35)",
                  zIndex: 50,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: 16,
                }}
                onClick={() => {
                  if (!geneSlotBusy) {
                    setGeneRoleDialog(null);
                    setGeneRolePreference("");
                  }
                }}
              >
                <div
                  style={{
                    background: "#fff",
                    borderRadius: 12,
                    padding: 18,
                    maxWidth: 480,
                    width: "100%",
                    boxShadow: "var(--shadow-lg)",
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>更换职能 · CEO 重新生成</div>
                  <div style={{ fontSize: 12, color: "#546e7a", marginBottom: 10 }}>
                    部门 {geneRoleDialog.dept} /{" "}
                    {GENE_SLOT_ROWS.find((x) => x.id === geneRoleDialog.slot)?.label ?? geneRoleDialog.slot}
                  </div>
                  <label style={{ fontSize: 12, display: "block", marginBottom: 4 }}>
                    倾向文本（可选：希望找什么样的职能；留空则 CEO 自由发挥）
                  </label>
                  <textarea
                    value={geneRolePreference}
                    onChange={(e) => setGeneRolePreference(e.target.value)}
                    disabled={!!geneSlotBusy}
                    rows={4}
                    style={{
                      width: "100%",
                      marginBottom: 12,
                      padding: 8,
                      borderRadius: 8,
                      border: "1px solid #cfd8dc",
                      fontSize: 12,
                      boxSizing: "border-box",
                    }}
                  />
                  <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                    <button
                      type="button"
                      disabled={!!geneSlotBusy}
                      onClick={() => {
                        setGeneRoleDialog(null);
                        setGeneRolePreference("");
                      }}
                      style={{
                        padding: "6px 14px",
                        fontSize: 12,
                        borderRadius: 6,
                        border: "1px solid #cfd8dc",
                        background: "#fff",
                      }}
                    >
                      取消
                    </button>
                    <button
                      type="button"
                      disabled={!!geneSlotBusy}
                      onClick={() => void confirmRegenerateGeneRole()}
                      style={{
                        padding: "6px 14px",
                        fontSize: 12,
                        borderRadius: 6,
                        border: "none",
                        background: geneSlotBusy ? "#b0bec5" : "#3949ab",
                        color: "#fff",
                        fontWeight: 600,
                        cursor: geneSlotBusy ? "wait" : "pointer",
                      }}
                    >
                      {geneSlotBusy ? "生成中…" : "确定生成"}
                    </button>
                  </div>
                </div>
              </div>
            ) : null}

            <div style={{ marginTop: 16, display: "flex", flexWrap: "wrap", gap: 8 }}>
              <button
                type="button"
                disabled={hubServerBusy}
                onClick={() => void saveHubServerSettings()}
                style={{
                  padding: "10px 18px",
                  borderRadius: 8,
                  border: "none",
                  background: hubServerBusy ? "#b0bec5" : "#0d47a1",
                  color: "#fff",
                  fontWeight: 600,
                  cursor: hubServerBusy ? "wait" : "pointer",
                  fontSize: 13,
                }}
              >
                {hubServerBusy ? "保存中…" : "保存服务端 API 配置"}
              </button>
            </div>

            {settingsMsg ? (
              <div
                style={{
                  marginTop: 12,
                  padding: "10px 12px",
                  borderRadius: 8,
                  fontSize: 12,
                  background: "#f5f7ff",
                  border: "1px solid #c5cae9",
                  color: "#1a237e",
                  wordBreak: "break-word",
                }}
              >
                {settingsMsg}
              </div>
            ) : null}
          </section>
        ) : null}

        {/* 区域 A */}
        <section
          style={{
            background: "#fff",
            borderRadius: 12,
            border: "1px solid #e6e9ef",
            padding: 20,
            marginBottom: 16,
            boxShadow: "0 1px 2px rgba(16,24,40,0.04)",
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>任务下达</div>
          <div style={{ fontSize: 12, color: "#5c6370", marginBottom: 12 }}>用业务语言描述背景、目标与约束；选择一种协同模式后启动。</div>

          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>业务类型（SOP 模式）</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {modes.map((m) => {
                const active = m.mode_id === modeId;
                return (
                  <button
                    key={m.mode_id}
                    type="button"
                    disabled={hubLocked}
                    onClick={() => setModeId(m.mode_id)}
                    style={{
                      textAlign: "left",
                      padding: "10px 12px",
                      borderRadius: 10,
                      border: active ? "1px solid #1a237e" : "1px solid #e0e4ea",
                      background: active ? "#eef0ff" : "#fafbfc",
                      cursor: hubLocked ? "not-allowed" : "pointer",
                      maxWidth: 280,
                      opacity: hubLocked ? 0.65 : 1,
                    }}
                  >
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{m.label}</div>
                    {m.scenario_description ? (
                      <div style={{ fontSize: 11, color: "#5c6370", marginTop: 4, lineHeight: 1.4 }}>{m.scenario_description}</div>
                    ) : null}
                  </button>
                );
              })}
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
            <textarea
              value={task}
              onChange={(e) => setTask(e.target.value)}
              disabled={hubLocked}
              rows={5}
              placeholder="请描述本次决策背景、目标、关键约束与希望对齐的部门关注点…"
              style={{
                flex: 1,
                padding: 12,
                borderRadius: 10,
                border: "1px solid #d5dbe3",
                fontSize: 14,
                resize: "vertical",
                minHeight: 120,
                fontFamily: "inherit",
              }}
            />
            <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "stretch" }}>
              <button
                type="button"
                disabled={hubLocked}
                title="关联历史决策或附件"
                onClick={() => setContextOpen((v) => !v)}
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 10,
                  border: "1px solid #d5dbe3",
                  background: contextOpen ? "#eef0ff" : "#fff",
                  cursor: hubLocked ? "not-allowed" : "pointer",
                  fontSize: 18,
                  lineHeight: 1,
                }}
              >
                📎
              </button>
              <input ref={fileRef} type="file" multiple style={{ display: "none" }} onChange={onFilesPicked} />
              <button
                type="button"
                disabled={hubLocked}
                onClick={() => fileRef.current?.click()}
                style={{
                  fontSize: 11,
                  padding: "6px 8px",
                  borderRadius: 8,
                  border: "1px solid #d5dbe3",
                  background: "#fff",
                  cursor: hubLocked ? "not-allowed" : "pointer",
                  color: "#3d4f5f",
                }}
              >
                上传参考
              </button>
            </div>
          </div>

          {attachedNames.length ? (
            <div style={{ marginTop: 8, fontSize: 12, color: "#37474f" }}>
              已选附件（将随任务一并提交）：{attachedNames.join("、")}
            </div>
          ) : null}

          {contextOpen ? (
            <div
              style={{
                marginTop: 12,
                padding: 12,
                borderRadius: 10,
                border: "1px solid #e6e9ef",
                background: "#fafbfc",
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>引用历史决策（摘要）</div>
              {history.length === 0 ? (
                <div style={{ fontSize: 12, color: "#78909c" }}>暂无历史记录；完成一次决策后会出现在此。</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 200, overflow: "auto" }}>
                  {history.map((h, idx) => (
                    <button
                      key={`${h.decision_id}-${idx}`}
                      type="button"
                      onClick={() => applyHistoryTask(h)}
                      style={{
                        textAlign: "left",
                        padding: "8px 10px",
                        borderRadius: 8,
                        border: "1px solid #e0e4ea",
                        background: "#fff",
                        cursor: "pointer",
                        fontSize: 12,
                      }}
                    >
                      <div style={{ color: "#78909c", fontSize: 11 }}>{h.created_at || h.decision_id}</div>
                      <div style={{ marginTop: 4, color: "#263238" }}>{(h.task || "").slice(0, 120)}{(h.task || "").length > 120 ? "…" : ""}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : null}

          <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12, fontSize: 12, color: "#5c6370" }}>
            <input type="checkbox" checked={rejectUnknownMode} disabled={hubLocked} onChange={(e) => setRejectUnknownMode(e.target.checked)} />
            仅允许已在清单中的业务类型（避免误选未发布模板）
          </label>

          <div style={{ marginTop: 14, display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
            <button
              type="button"
              disabled={hubLocked || !task.trim() || !modes.length || !(currentMode?.departments?.length ?? 0)}
              onClick={() => void start()}
              style={{
                padding: "12px 20px",
                borderRadius: 10,
                border: "none",
                background: hubLocked || !task.trim() || !modes.length || !(currentMode?.departments?.length ?? 0) ? "#b0bec5" : "#1a237e",
                color: "#fff",
                fontWeight: 600,
                fontSize: 14,
                cursor: hubLocked || !task.trim() || !modes.length || !(currentMode?.departments?.length ?? 0) ? "not-allowed" : "pointer",
              }}
            >
              {running ? "决策进行中…" : "开始决策"}
            </button>
            <button
              type="button"
              disabled={hubLocked}
              onClick={() => {
                setTask("");
                setAttachedNames([]);
              }}
              style={{
                padding: "10px 14px",
                borderRadius: 10,
                border: "1px solid #cfd6e0",
                background: "#fff",
                fontSize: 13,
                cursor: hubLocked ? "not-allowed" : "pointer",
                color: "#455a64",
              }}
            >
              清空
            </button>
            {currentMode?.default_task_hint ? (
              <button
                type="button"
                disabled={hubLocked}
                onClick={() => setTask(currentMode.default_task_hint || "")}
                style={{
                  padding: "10px 14px",
                  borderRadius: 10,
                  border: "1px solid #cfd6e0",
                  background: "#fff",
                  fontSize: 13,
                  cursor: hubLocked ? "not-allowed" : "pointer",
                  color: "#455a64",
                }}
              >
                填入模板提示
              </button>
            ) : null}
          </div>
        </section>

        {/* 区域 B */}
        <section
          style={{
            background: "#fff",
            borderRadius: 12,
            border: "1px solid #e6e9ef",
            padding: 20,
            marginBottom: 16,
            boxShadow: "0 1px 2px rgba(16,24,40,0.04)",
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>进度监控</div>
          <div style={{ fontSize: 12, color: "#5c6370", marginBottom: 12 }}>
            关注区优先展示异常拦截与业务告警部门；不展示技术日志。
          </div>
          <div style={{ height: 8, borderRadius: 999, background: "#eceff4", overflow: "hidden", marginBottom: 14 }}>
            <div
              style={{
                height: "100%",
                width: `${overallPct}%`,
                borderRadius: 999,
                background: "linear-gradient(90deg,#3949ab,#5c6bc0)",
                transition: "width 0.35s ease",
              }}
            />
          </div>
          <div style={{ fontSize: 11, color: "#78909c", marginBottom: 10 }}>
            总体进度 {overallPct}% {running ? "· 正在协同评估" : latestSummary ? "· 已形成汇总" : "· 待命"}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10 }}>
            {sortedDeptRows.map((row) => {
              const ring =
                row.lamp === "block"
                  ? "0 0 0 2px #c62828"
                  : row.lamp === "warn"
                    ? "0 0 0 2px #ef6c00"
                    : "0 0 0 1px #e6e9ef";
              const dot =
                row.phase !== "done" ? "#5c6bc0" : row.lamp === "block" ? "#c62828" : row.lamp === "warn" ? "#ef6c00" : "#2e7d32";
              return (
                <div
                  key={row.dept}
                  style={{
                    borderRadius: 10,
                    padding: "10px 12px",
                    border: "1px solid #e6e9ef",
                    boxShadow: ring,
                    background: "#fafbfc",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ width: 10, height: 10, borderRadius: 999, background: dot, flexShrink: 0 }} />
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{row.label}</div>
                  </div>
                  <div style={{ marginTop: 6, fontSize: 12, color: "#455a64", lineHeight: 1.45 }}>{row.caption}</div>
                </div>
              );
            })}
          </div>
          {!sortedDeptRows.length ? (
            <div style={{ fontSize: 12, color: "#90a4ae", marginTop: 8 }}>选择业务类型后将显示相关部门进度。</div>
          ) : null}
        </section>

        {/* 区域 C */}
        <section
          style={{
            background: "#fff",
            borderRadius: 12,
            border: "1px solid #e6e9ef",
            padding: 20,
            boxShadow: "0 1px 2px rgba(16,24,40,0.04)",
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>决策汇总</div>
          <div style={{ fontSize: 12, color: "#5c6370", marginBottom: 14 }}>先阅读 CEO 调和建议，再查看部门观点与冲突，最后拍板。</div>

          {!showSummary ? (
            <div style={{ fontSize: 13, color: "#90a4ae", padding: "24px 0", textAlign: "center" }}>
              {running ? "汇总将在各部门完成后自动生成。" : "完成一次决策后，这里会展示结论与行动建议。"}
            </div>
          ) : (
            <>
              <div
                style={{
                  padding: 16,
                  borderRadius: 12,
                  border: "1px solid #c5cae9",
                  background: "linear-gradient(180deg,#f8f9ff 0%,#fff 100%)",
                  marginBottom: 14,
                }}
              >
                <div style={{ fontSize: 12, fontWeight: 700, color: "#283593", marginBottom: 8 }}>CEO 中枢调和建议</div>
                <div style={{ fontSize: 14, lineHeight: 1.65, whiteSpace: "pre-wrap", color: "#1a1d21" }}>{latestSummary!.ceo_decision || "（暂无文本）"}</div>
              </div>

              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>结论要点</div>
                {extractBullets(latestSummary!.ceo_decision || "").length ? (
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.55 }}>
                    {extractBullets(latestSummary!.ceo_decision || "").map((b, i) => (
                      <li key={i}>{b}</li>
                    ))}
                  </ul>
                ) : (
                  <div style={{ fontSize: 12, color: "#78909c" }}>（可执行要点将随 CEO 文本结构化输出而增强）</div>
                )}
              </div>

              {latestSummary!.red_team_risks && latestSummary!.red_team_risks.length ? (
                <div
                  style={{
                    marginBottom: 14,
                    padding: 12,
                    borderRadius: 10,
                    border: "1px solid #ffe0b2",
                    background: "#fffaf0",
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 600, color: "#e65100", marginBottom: 6 }}>风险清单</div>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                    {latestSummary!.red_team_risks!.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>部门意见与冲突</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {(latestSummary!.dept_reports || []).map((rep, idx) => {
                  const d = String(rep.dept || idx);
                  const label = deptLabels[d] || d;
                  const text = String(rep.consensus || "");
                  const stance = inferStance(text);
                  const checked = selectedDepts.has(d);
                  return (
                    <div
                      key={`${d}-${idx}`}
                      style={{
                        borderRadius: 10,
                        border: "1px solid #e6e9ef",
                        padding: 12,
                        background: "#fafbfc",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "flex-start", gap: 10, flexWrap: "wrap" }}>
                        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#546e7a", cursor: "pointer" }}>
                          <input type="checkbox" checked={checked} disabled={outcome !== "open"} onChange={() => toggleDeptSelect(d)} />
                          仅重评此部门
                        </label>
                        <div style={{ marginLeft: "auto", fontSize: 12, fontWeight: 700, color: stance.color }}>{stance.tag}</div>
                      </div>
                      <div style={{ fontWeight: 600, fontSize: 14, marginTop: 6 }}>{label}</div>
                      <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{text || "（无摘要）"}</div>
                      {rep.conflicts && rep.conflicts.length ? (
                        <div style={{ marginTop: 8 }}>
                          <div style={{ fontSize: 11, fontWeight: 600, color: "#b71c1c" }}>冲突点</div>
                          <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 12 }}>
                            {rep.conflicts.map((c, i) => (
                              <li key={i}>{c}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>

              {outcome === "open" ? (
                <div style={{ marginTop: 18, paddingTop: 16, borderTop: "1px solid #eceff4" }}>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
                    <div style={{ position: "relative" }}>
                      <button
                        type="button"
                        onClick={() => finalizeConfirm("archived")}
                        style={{
                          padding: "12px 18px",
                          borderRadius: 10,
                          border: "none",
                          background: "#1a237e",
                          color: "#fff",
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        确认结论
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmMenuOpen((v) => !v)}
                        style={{
                          marginLeft: 4,
                          padding: "12px 10px",
                          borderRadius: 10,
                          border: "1px solid #1a237e",
                          background: "#fff",
                          color: "#1a237e",
                          cursor: "pointer",
                          fontWeight: 600,
                        }}
                        title="更多确认动作"
                      >
                        ▾
                      </button>
                      {confirmMenuOpen ? (
                        <div
                          style={{
                            position: "absolute",
                            bottom: "100%",
                            left: 0,
                            marginBottom: 6,
                            minWidth: 220,
                            background: "#fff",
                            border: "1px solid #e0e4ea",
                            borderRadius: 10,
                            boxShadow: "0 8px 24px rgba(16,24,40,0.12)",
                            zIndex: 5,
                          }}
                        >
                          <button
                            type="button"
                            onClick={() => finalizeConfirm("archived")}
                            style={ddBtn}
                          >
                            确认并归档
                          </button>
                          <button type="button" onClick={() => finalizeConfirm("exec_doc")} style={ddBtn}>
                            确认并生成执行文档（占位）
                          </button>
                          <button type="button" onClick={() => finalizeConfirm("gold_sop")} style={ddBtn}>
                            确认并沉淀为黄金 SOP（占位）
                          </button>
                        </div>
                      ) : null}
                    </div>
                    <button
                      type="button"
                      onClick={partialRerunHint}
                      style={{
                        padding: "12px 16px",
                        borderRadius: 10,
                        border: "1px solid #3949ab",
                        background: "#fff",
                        color: "#283593",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      部分重跑（所选部门）
                    </button>
                  </div>
                  <div style={{ marginTop: 14 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>整体驳回</div>
                    <textarea
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value)}
                      rows={2}
                      placeholder="请填写驳回原因（必填）"
                      style={{ width: "100%", maxWidth: 480, padding: 10, borderRadius: 8, border: "1px solid #d5dbe3", fontFamily: "inherit", fontSize: 13 }}
                    />
                    <button
                      type="button"
                      onClick={finalizeReject}
                      style={{
                        marginTop: 8,
                        padding: "10px 16px",
                        borderRadius: 10,
                        border: "1px solid #c62828",
                        background: "#fff",
                        color: "#b71c1c",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      驳回本轮结论
                    </button>
                  </div>
                </div>
              ) : (
                <div
                  style={{
                    marginTop: 18,
                    padding: 14,
                    borderRadius: 10,
                    border: "1px solid #c8e6c9",
                    background: outcome === "rejected" ? "#fff5f5" : "#f4faf4",
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{outcome === "rejected" ? "已驳回" : "已定稿"}</div>
                  {outcomeNote ? <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.5 }}>{outcomeNote}</div> : null}
                </div>
              )}
            </>
          )}
        </section>

        {outcomeNote && outcome === "open" && !running ? (
          <div style={{ marginTop: 12, fontSize: 12, color: "#455a64", padding: 10, background: "#fffde7", border: "1px solid #ffe082", borderRadius: 8 }}>
            {outcomeNote}
          </div>
        ) : null}
      </div>
    </div>
  );
}

const ddBtn: CSSProperties = {
  display: "block",
  width: "100%",
  textAlign: "left",
  padding: "10px 12px",
  border: "none",
  borderBottom: "1px solid #f0f2f6",
  background: "#fff",
  fontSize: 13,
  cursor: "pointer",
  color: "#263238",
};
