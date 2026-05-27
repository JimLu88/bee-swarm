"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  HSEMAS_BACKEND_STORAGE_KEY,
  httpToWsOrigin,
  normalizeBackendUrl,
  resolveBackendHttpBase,
} from "../../lib/backend";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

import { ModePicker, BUILTIN_MODES, type ModeOption } from "./ModePicker";
import { TaskInput } from "./TaskInput";
import { DifficultySlider, DIFFICULTY_INFO, type Difficulty } from "./DifficultySlider";
import { ResultPanel, type DecisionSummary } from "./ResultPanel";
import { HistoryPanel, type HistoryRow } from "./HistoryPanel";
import { ViewTabs, type ViewMode } from "./ViewTabs";
import { SwarmDashboardModal, type DeptHeat } from "./SwarmDashboardModal";
import { GeneEditor } from "./advanced/GeneEditor";
import { ScenarioYamlAuthor } from "./advanced/ScenarioYamlAuthor";
import { ThinkingFrameworksPanel } from "./advanced/ThinkingFrameworksPanel";
import { SandboxPanel } from "./engineer/SandboxPanel";
import { ShadowABPanel } from "./engineer/ShadowABPanel";
import { CoordinatorPanel } from "./engineer/CoordinatorPanel";
import { SettingsPanel } from "./SettingsPanel";

/**
 * BeeSwarmShell — 新版 v4 主壳
 *
 * 布局:
 *   - 顶部: 5+1 场景卡片
 *   - 中部: 任务输入 + 4 档难度滑块(AI 建议高亮)
 *   - 下部: 结果区 + 历史
 *   - 右上: ⚙ 设置 / 🐝 蜂群面板 / 📊 记账
 *   - 三档视图: 用户(默认) / 高级 / 工程
 */

const DIFFICULTY_TO_ROUNDS: Record<Difficulty, number> = { 1: 1, 2: 2, 3: 3, 4: 5 };

export function BeeSwarmShell() {
  // --- core state ---
  const [view, setView] = useState<ViewMode>("user");
  const [mode, setMode] = useState<string>("program_management");
  const [task, setTask] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty>(2);
  const [aiSuggested, setAiSuggested] = useState<Difficulty | undefined>();
  const [aiReason, setAiReason] = useState<string | undefined>();
  const [estimateText, setEstimateText] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState<DecisionSummary | null>(null);
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  // dashboard
  const [dashOpen, setDashOpen] = useState(false);
  const [heats, setHeats] = useState<DeptHeat[]>([]);
  const [progress, setProgress] = useState<number>(0);

  // thinking frameworks
  const [frameworks, setFrameworks] = useState<string[]>([]);
  const [aiFrameworks, setAiFrameworks] = useState<string[]>([]);

  // --- backend URL ---
  const backendUrl = useMemo(() => resolveBackendHttpBase(), []);
  const wsBase = useMemo(() => httpToWsOrigin(backendUrl), [backendUrl]);

  // --- AI 自动判断难度(防抖,task 改动 1 秒后调用 /estimate) ---
  const estTimer = useRef<number | null>(null);
  useEffect(() => {
    if (!task.trim()) {
      setAiSuggested(undefined);
      setAiReason(undefined);
      setEstimateText(undefined);
      return;
    }
    if (estTimer.current) window.clearTimeout(estTimer.current);
    estTimer.current = window.setTimeout(async () => {
      try {
        const res = await fetchWithTimeout(
          `${backendUrl}/api/decision/estimate`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task, mode_id: mode, debate_rounds: DIFFICULTY_TO_ROUNDS[difficulty] }),
          },
          TIMEOUT_MS.default,
        );
        if (!res.ok) throw new Error(`estimate ${res.status}`);
        const j = await res.json();
        if (j.difficulty) {
          setAiSuggested(j.difficulty as Difficulty);
          setAiReason(j.reason ?? undefined);
        }
        if (j.estimate_yuan != null) {
          setEstimateText(`约 ¥${Number(j.estimate_yuan).toFixed(2)} · ${j.estimate_tokens ?? "?"} tokens · ${j.eta_sec ?? "?"} 秒`);
        }
        if (Array.isArray(j.suggested_frameworks)) {
          setAiFrameworks(j.suggested_frameworks);
        }
      } catch {
        // backend not yet supports /estimate → silent fallback
        setEstimateText(undefined);
      }
    }, 700) as unknown as number;
    return () => { if (estTimer.current) window.clearTimeout(estTimer.current); };
  }, [task, mode, difficulty, backendUrl]);

  // --- 拉历史 ---
  const refreshHistory = useCallback(async () => {
    try {
      const res = await fetchWithTimeout(`${backendUrl}/api/memory/${mode}?limit=20&compact=1`, undefined, TIMEOUT_MS.default);
      if (!res.ok) throw new Error(`memory ${res.status}`);
      const j = await res.json();
      const rows: HistoryRow[] = Array.isArray(j?.items) ? j.items : Array.isArray(j) ? j : [];
      setHistory(rows);
    } catch {
      setHistory([]);
    }
  }, [backendUrl, mode]);

  useEffect(() => { refreshHistory(); }, [refreshHistory]);

  // --- 启动决策 ---
  const startDecision = useCallback(async () => {
    if (!task.trim()) { setError("请先输入任务"); return; }
    setError(null);
    setBusy(true);
    setSummary(null);
    setHeats([]);
    setProgress(0);

    try {
      const res = await fetchWithTimeout(
        `${backendUrl}/api/decision/start`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            task,
            mode_id: mode,
            debate_rounds: DIFFICULTY_TO_ROUNDS[difficulty],
            thinking_frameworks: frameworks.length > 0 ? frameworks : undefined,
          }),
        },
        TIMEOUT_MS.decisionStart,
      );
      if (!res.ok) throw new Error(`decision/start ${res.status}`);
      const j = await res.json();
      const decisionId: string | undefined = j?.decision_id;
      if (!decisionId) throw new Error("缺少 decision_id");

      // listen WebSocket
      const ws = new WebSocket(`${wsBase}/api/decision/stream/${decisionId}`);
      ws.onmessage = (ev) => {
        try {
          const e = JSON.parse(ev.data);
          if (e.type === "dispatcher_ready") {
            setProgress(10);
          } else if (e.type === "fanout_started") {
            setProgress(20);
            const depts: string[] = Array.isArray(e.payload?.depts) ? e.payload.depts : [];
            setHeats(depts.map((d) => ({ dept: d, heat: 0, status: "idle" })));
          } else if (e.type === "dept_done") {
            const d = String(e.payload?.dept ?? "");
            setHeats((prev) => prev.map((h) => h.dept === d ? { ...h, heat: 1, status: "done", callCount: (h.callCount ?? 0) + 1, opinion: e.payload?.consensus } : h));
            setProgress((p) => Math.min(95, p + 8));
          } else if (e.type === "decision_done") {
            setProgress(100);
            setSummary(e.payload as DecisionSummary);
            setBusy(false);
            refreshHistory();
            ws.close();
          } else if (e.type === "debate_round_start") {
            // v4-B
          } else if (e.type === "debate_converged") {
            setProgress(90);
          }
        } catch { /* ignore */ }
      };
      ws.onerror = () => { setError("WebSocket 异常"); setBusy(false); };
      ws.onclose = () => { /* ok */ };
    } catch (e: unknown) {
      setError((e as Error).message ?? "未知错误");
      setBusy(false);
    }
  }, [task, mode, difficulty, frameworks, backendUrl, wsBase, refreshHistory]);

  // --- 历史详情 ---
  const pickHistory = useCallback(async (decisionId: string) => {
    try {
      const res = await fetchWithTimeout(`${backendUrl}/api/memory/${mode}/decision/${decisionId}`, undefined, TIMEOUT_MS.default);
      if (!res.ok) throw new Error(`detail ${res.status}`);
      const j = await res.json();
      setSummary(j as DecisionSummary);
    } catch (e: unknown) {
      setError((e as Error).message ?? "拉取详情失败");
    }
  }, [backendUrl, mode]);

  // --- 范式 toggle ---
  const toggleFramework = useCallback((id: string) => {
    setFrameworks((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  }, []);

  // 当 AI 建议范式变化,自动同步勾选(用户没手动改时)
  useEffect(() => {
    if (frameworks.length === 0 && aiFrameworks.length > 0) {
      setFrameworks(aiFrameworks);
    }
  }, [aiFrameworks, frameworks.length]);

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Header */}
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22 }}>🐝 蜂群</h1>
          <div style={{ fontSize: 12, opacity: 0.6 }}>你好,今天想做什么?</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" onClick={() => setDashOpen(true)} style={iconBtn}>🐝 蜂群面板</button>
        </div>
      </header>

      <ViewTabs value={view} onChange={setView} />

      {/* 用户视图 (默认) */}
      {view === "user" && (
        <>
          <ModePicker selected={mode} onSelect={setMode} onOpenCustom={() => alert("自定义场景: 见高级视图 → ScenarioYamlAuthor")} />
          <TaskInput value={task} onChange={setTask} />
          <DifficultySlider
            value={difficulty}
            aiSuggested={aiSuggested}
            aiReason={aiReason}
            estimateText={estimateText}
            onChange={setDifficulty}
          />
          <div>
            <button
              type="button"
              onClick={startDecision}
              disabled={busy || !task.trim()}
              style={{
                padding: "12px 24px",
                fontSize: 16,
                fontWeight: 600,
                borderRadius: 8,
                border: "none",
                background: busy ? "rgba(250,204,21,0.4)" : "#facc15",
                color: "#000",
                cursor: busy ? "not-allowed" : "pointer",
              }}
            >
              {busy ? "🐝 正在讨论中…" : "🚀 开始"}
            </button>
            {error && <span style={{ marginLeft: 12, color: "#f87171", fontSize: 13 }}>{error}</span>}
          </div>
          <ResultPanel summary={summary} />
          <HistoryPanel rows={history} onPick={pickHistory} />
        </>
      )}

      {/* 高级视图 */}
      {view === "advanced" && (
        <>
          <ModePicker selected={mode} onSelect={setMode} onOpenCustom={() => {}} />
          <TaskInput value={task} onChange={setTask} />
          <DifficultySlider value={difficulty} aiSuggested={aiSuggested} aiReason={aiReason} estimateText={estimateText} onChange={setDifficulty} />
          <SettingsPanel />
          <ThinkingFrameworksPanel enabled={frameworks} aiPicked={aiFrameworks} onToggle={toggleFramework} />
          <GeneEditor />
          <ScenarioYamlAuthor />
          <div>
            <button type="button" onClick={startDecision} disabled={busy || !task.trim()} style={{ padding: "10px 20px", borderRadius: 8, border: "1px solid #facc15", background: "rgba(250,204,21,0.18)", color: "inherit", cursor: busy ? "not-allowed" : "pointer" }}>
              {busy ? "🐝 讨论中…" : "🚀 开始(高级)"}
            </button>
          </div>
          <ResultPanel summary={summary} />
        </>
      )}

      {/* 工程视图 */}
      {view === "engineer" && (
        <>
          <div style={{ padding: 12, borderRadius: 10, background: "rgba(250,204,21,0.06)", border: "1px solid rgba(250,204,21,0.2)", fontSize: 12 }}>
            ⚙️ 工程视图保留了完整的 legacy DecisionHub 组件入口(<code>/?legacy=1</code>),以及 Sandbox / Shadow / Coordinator 三个面板。
          </div>
          <SandboxPanel />
          <ShadowABPanel />
          <CoordinatorPanel />
        </>
      )}

      <SwarmDashboardModal
        open={dashOpen}
        onClose={() => setDashOpen(false)}
        heats={heats}
        progressPct={progress > 0 ? progress : undefined}
        flowText={"用户输入 → 分诊 → 部门并行 → CEO 终审 → 输出"}
      />
    </div>
  );
}

const iconBtn = {
  padding: "8px 12px",
  borderRadius: 6,
  border: "1px solid rgba(255,255,255,0.12)",
  background: "rgba(255,255,255,0.05)",
  cursor: "pointer",
  color: "inherit",
  font: "inherit",
  fontSize: 12,
};
