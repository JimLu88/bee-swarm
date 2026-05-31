"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ClipboardEvent as ReactClipboardEvent, type DragEvent as ReactDragEvent } from "react";
import {
  HSEMAS_BACKEND_STORAGE_KEY,
  httpToWsOrigin,
  normalizeBackendUrl,
  resolveBackendHttpBase,
} from "../../lib/backend";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

import { ModePicker, BUILTIN_MODES, type ModeOption } from "./ModePicker";
import { TeamPanel } from "./TeamPanel";
import { TaskInput } from "./TaskInput";
import { ImageStrip } from "./ImageStrip";
import { RoutePlanner } from "./RoutePlanner";
import { ScenarioDropdown } from "./ScenarioDropdown";
import { ModelBadgeBar } from "./ModelBadgeBar";
import { DifficultySlider, DIFFICULTY_INFO, type Difficulty } from "./DifficultySlider";
import { ResultPanel, type DecisionSummary } from "./ResultPanel";
import { HistoryPanel, type HistoryRow } from "./HistoryPanel";
import { ViewTabs, type ViewMode } from "./ViewTabs";  // 保留 import 防其它地方引用
import { SettingsDrawer } from "./SettingsDrawer";
import { SwarmDashboardModal, type DeptHeat } from "./SwarmDashboardModal";
import { GeneEditor } from "./advanced/GeneEditor";
import { ScenarioYamlAuthor } from "./advanced/ScenarioYamlAuthor";
import { ThinkingFrameworksPanel } from "./advanced/ThinkingFrameworksPanel";
import { SandboxPanel } from "./engineer/SandboxPanel";
import { ShadowABPanel } from "./engineer/ShadowABPanel";
import { CoordinatorPanel } from "./engineer/CoordinatorPanel";
import { Onboarding } from "./Onboarding";
import { SettingsPanel } from "./SettingsPanel";
import { ReviewPanel } from "./ReviewPanel";
import { BackupConfigPanel } from "./BackupConfigPanel";
import { UpgradeLogPanel } from "./UpgradeLogPanel";
import { NotificationBell } from "./NotificationBell";
import { LogsPanel } from "./LogsPanel";
import { ClarifyAndPlanModal, type Plan } from "./ClarifyAndPlanModal";
import { PendingChangesDrawer } from "./PendingChangesDrawer";
import { TodayOverviewCard } from "./TodayOverviewCard";
import { CommandPalette } from "./CommandPalette";
import { useAutosave } from "../../lib/useAutosave";

/**
 * BeeSwarmShell — 新版 v4 主壳
 *
 * 布局:
 *   - 顶部: 5+1 场景卡片
 *   - 中部: 任务输入 + 4 档难度滑块(AI 建议高亮)
 *   - 下部: 结果区 + 历史
 *   - 右上: ⚙ AI 设置 / 🐝 看 AI 怎么干活 / 📊 记账
 *   - 三档视图: 用户(默认) / 高级 / 工程
 */

const DIFFICULTY_TO_ROUNDS: Record<Difficulty, number> = { 1: 1, 2: 2, 3: 3, 4: 5 };

export function BeeSwarmShell() {
  // --- core state ---
  const [view, setView] = useState<ViewMode>("user");  // 兼容; 主页固定 user
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mode, setMode] = useState<string>("program_management");
  // v6-S10 task 自动备份 — 刷新/崩溃不丢
  const { value: task, setValue: setTask, clear: clearTaskBackup, restored: taskRestored } = useAutosave<string>("task-input", "");
  const [difficulty, setDifficulty] = useState<Difficulty>(2);
  const [aiSuggested, setAiSuggested] = useState<Difficulty | undefined>();
  const [aiReason, setAiReason] = useState<string | undefined>();
  const [estimateText, setEstimateText] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState<DecisionSummary | null>(null);
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  // v6-S/C SettingsDrawer 默认 tab (TodayOverviewCard 点"复习"切到 memory)
  const [settingsInitialTab, setSettingsInitialTab] = useState<"scenario" | "ai" | "memory" | "advanced" | "tech" | undefined>(undefined);

  // v6-W 3 档降级: A=高档旗舰 / B=中档便宜云 / C=离线本地
  // 初值固定 "A" 与 SSR 一致; localStorage 读取放 mount 后 useEffect,
  // 否则首屏 hydration 时 server("A") vs client(saved) 不一致 → hydration error (见 v6-Z-fix).
  const [tier, setTierState] = useState<"A" | "B" | "C">("A");
  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem("h-semas:tier") as "A" | "B" | "C" | null;
    if (saved === "B" || saved === "C") setTierState(saved);
  }, []);
  const setTier = (t: "A" | "B" | "C") => {
    setTierState(t);
    if (typeof window !== "undefined") {
      try { window.localStorage.setItem("h-semas:tier", t); } catch { /* ignore */ }
    }
  };

  // v6-X 图片: data URL, 最多 4 张, 单张 <= 6MB (走视觉模型)
  const [images, setImages] = useState<string[]>([]);
  // v6-Y 文档: xlsx/pdf/docx/pptx/csv/txt, 最多 5 个, 单个 <= 15MB (进程内解析成文字)
  const [docFiles, setDocFiles] = useState<{ name: string; content_b64: string }[]>([]);
  const [attachWarn, setAttachWarn] = useState<string | null>(null);

  const readAsDataUrl = (file: File): Promise<string> => new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result || ""));
    r.onerror = () => reject(new Error("read failed"));
    r.readAsDataURL(file);
  });

  // 统一入口: 图片走 images, 其余走 docFiles
  const addAttachment = useCallback(async (file: File): Promise<void> => {
    const isImage = file.type.startsWith("image/");
    if (isImage) {
      if (file.size > 6 * 1024 * 1024) { setAttachWarn(`图片太大 (>6MB): ${file.name}`); return; }
      const dataUrl = await readAsDataUrl(file);
      setImages((prev) => {
        if (prev.length >= 10) { setAttachWarn("最多 10 张图"); return prev; }
        setAttachWarn(null);
        return [...prev, dataUrl];
      });
      return;
    }
    // 文档
    if (file.size > 15 * 1024 * 1024) { setAttachWarn(`文件太大 (>15MB): ${file.name}`); return; }
    const dataUrl = await readAsDataUrl(file);
    const b64 = dataUrl.includes(",") ? dataUrl.split(",", 2)[1] : dataUrl;
    setDocFiles((prev) => {
      if (prev.length >= 5) { setAttachWarn("最多 5 个文档"); return prev; }
      setAttachWarn(null);
      return [...prev, { name: file.name, content_b64: b64 }];
    });
  }, []);

  const removeImageAt = useCallback((idx: number) => {
    setImages((prev) => prev.filter((_, i) => i !== idx));
    setAttachWarn(null);
  }, []);
  const removeDocAt = useCallback((idx: number) => {
    setDocFiles((prev) => prev.filter((_, i) => i !== idx));
    setAttachWarn(null);
  }, []);
  const onPaste = useCallback((e: ReactClipboardEvent) => {
    const items = Array.from(e.clipboardData?.items || []);
    for (const it of items) {
      if (it.kind === "file") {
        const f = it.getAsFile();
        if (f) { void addAttachment(f); e.preventDefault(); }
      }
    }
  }, [addAttachment]);
  const onDrop = useCallback((e: ReactDragEvent) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer?.files || []);
    for (const f of files) void addAttachment(f);
  }, [addAttachment]);
  const onDragOver = useCallback((e: ReactDragEvent) => { e.preventDefault(); }, []);

  // dashboard
  const [dashOpen, setDashOpen] = useState(false);
  const [heats, setHeats] = useState<DeptHeat[]>([]);
  const [progress, setProgress] = useState<number>(0);

  // v6-S6/S7 决策开始时间 + 重跑中部门
  const decisionStartRef = useRef<number | null>(null);
  const [rerunningDept, setRerunningDept] = useState<string | null>(null);
  const [currentDecisionId, setCurrentDecisionId] = useState<string | null>(null);

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

  // v6-F 决策计划 modal 状态
  const [clarifyOpen, setClarifyOpen] = useState(false);
  // v6-Z 本次决策的路线元数据 (供 ResultPanel 👍👎 回填 bandit)
  const [runMeta, setRunMeta] = useState<{ route: string; rounds_band: string; difficulty: string } | null>(null);

  // 用户点 "开跑" → 先打开 ClarifyAndPlanModal; modal onConfirm 才真调 /decision/start
  const openClarifyPlan = useCallback(() => {
    if (!task.trim()) { setError("先在上面写一句话告诉我你要什么"); return; }
    setError(null);
    setClarifyOpen(true);
  }, [task]);

  // v6-Z 共享: 连 WebSocket 流式接收决策事件 (route 路径与 modal 路径复用)
  const attachStream = useCallback((decisionId: string) => {
    setCurrentDecisionId(decisionId);
    decisionStartRef.current = Date.now();
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
          const _sum = (e.payload as { summary?: DecisionSummary }).summary ?? (e.payload as DecisionSummary);
          if (decisionStartRef.current) {
            _sum.elapsed_sec = (Date.now() - decisionStartRef.current) / 1000;
          }
          setSummary(_sum);
          setBusy(false);
          refreshHistory();
          ws.close();
        } else if (e.type === "debate_converged") {
          setProgress(90);
        }
      } catch { /* ignore */ }
    };
    ws.onerror = () => { setError("和 AI 的连接断了, 刷新一下重试"); setBusy(false); };
    ws.onclose = () => { /* ok */ };
  }, [wsBase, refreshHistory]);

  // 真启动决策 (modal onConfirm 调用) — 走 route=all 兼容路径
  const runDecisionWith = useCallback(async (finalTask: string, plan: Plan) => {
    setClarifyOpen(false);
    setError(null); setBusy(true); setSummary(null); setHeats([]); setProgress(0);
    decisionStartRef.current = Date.now();
    setRunMeta({ route: "all", rounds_band: "medium", difficulty: "medium" });
    try {
      const res = await fetchWithTimeout(
        `${backendUrl}/api/decision/start`,
        {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            task: finalTask, mode_id: mode,
            debate_rounds: Math.max(plan.rounds, 1),
            thinking_frameworks: frameworks.length > 0 ? frameworks : undefined,
            tier, images, files: docFiles,
          }),
        },
        TIMEOUT_MS.decisionStart,
      );
      if (!res.ok) throw new Error(`decision/start ${res.status}`);
      const j = await res.json();
      const decisionId: string | undefined = j?.decision_id;
      if (!decisionId) throw new Error("AI 服务暂时没响应, 等一下再试");
      clearTaskBackup(); setImages([]); setDocFiles([]);
      attachStream(decisionId);
    } catch (e: unknown) {
      setError((e as Error).message ?? "出了点小问题, 等一下重试");
      setBusy(false);
    }
  }, [mode, frameworks, backendUrl, clearTaskBackup, tier, images, docFiles, attachStream]);

  // v6-Z RoutePlanner "生成执行命令" → 按选定路线+轮数启动
  const runWithRoute = useCallback(async (p: { route: string; departments: string[]; rounds: number; rounds_band: string; difficulty: string }) => {
    setError(null); setBusy(true); setSummary(null); setHeats([]); setProgress(0);
    decisionStartRef.current = Date.now();
    setRunMeta({ route: p.route, rounds_band: p.rounds_band, difficulty: p.difficulty });
    try {
      const res = await fetchWithTimeout(
        `${backendUrl}/api/decision/start`,
        {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            task, mode_id: mode,
            debate_rounds: Math.max(p.rounds, 1),
            thinking_frameworks: frameworks.length > 0 ? frameworks : undefined,
            tier, images, files: docFiles,
            route: p.route,
            departments_override: p.departments,
            difficulty_bucket: p.difficulty,
          }),
        },
        TIMEOUT_MS.decisionStart,
      );
      if (!res.ok) throw new Error(`decision/start ${res.status}`);
      const j = await res.json();
      const decisionId: string | undefined = j?.decision_id;
      if (!decisionId) throw new Error("AI 服务暂时没响应, 等一下再试");
      clearTaskBackup(); setImages([]); setDocFiles([]);
      attachStream(decisionId);
    } catch (e: unknown) {
      setError((e as Error).message ?? "出了点小问题, 等一下重试");
      setBusy(false);
    }
  }, [task, mode, frameworks, backendUrl, clearTaskBackup, tier, images, docFiles, attachStream]);

  // v6-Z 👍👎 反馈 → bandit 学习
  const sendFeedback = useCallback(async (reward: number) => {
    if (!currentDecisionId || !runMeta) return;
    try {
      await fetchWithTimeout(
        `${backendUrl}/api/decision/feedback`,
        {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            decision_id: currentDecisionId, mode_id: mode, reward,
            route: runMeta.route, rounds_band: runMeta.rounds_band, difficulty: runMeta.difficulty,
          }),
        },
        TIMEOUT_MS.default,
      );
    } catch { /* silent */ }
  }, [backendUrl, currentDecisionId, runMeta, mode]);

  // 旧 startDecision 接口的兼容包装 (TaskInput 等组件仍调它; 实质走新流程)
  const startDecision = openClarifyPlan;

  // v7 主题开关 (Wave1 占位; Wave2 接 CSS 令牌). 默认 dark, SSR-safe.
  const [theme, setTheme] = useState<"light" | "dark">("dark");
  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem("h-semas:theme");
    const t = saved === "light" ? "light" : "dark";
    setTheme(t);
    document.documentElement.dataset.theme = t;
  }, []);
  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      if (typeof window !== "undefined") {
        document.documentElement.dataset.theme = next;
        try { window.localStorage.setItem("h-semas:theme", next); } catch { /* ignore */ }
      }
      return next;
    });
  }, []);

  // v7 ⚙更多设置: 展开精细路线×轮数 (RoutePlanner)
  const [moreSettings, setMoreSettings] = useState(false);

  // v7 努力程度(difficulty 1-4) → (route, rounds). 简单=CEO单答, 全力=全部门深辩.
  const runByEffort = useCallback(() => {
    if (!task.trim()) { setError("先在上面写一句话告诉我你要什么"); return; }
    const MAP: Record<Difficulty, { route: string; rounds: number; band: string; diff: string }> = {
      1: { route: "ceo_only", rounds: 0, band: "light", diff: "light" },
      2: { route: "all", rounds: 1, band: "light", diff: "medium" },
      3: { route: "all", rounds: 2, band: "medium", diff: "medium" },
      4: { route: "all", rounds: 3, band: "heavy", diff: "heavy" },
    };
    const m = MAP[difficulty];
    void runWithRoute({ route: m.route, departments: [], rounds: m.rounds, rounds_band: m.band, difficulty: m.diff });
  }, [task, difficulty, runWithRoute]);

  // v6-S6 重跑某个部门 (后端有 /api/decision/rerun-dept 时生效)
  const rerunDept = useCallback(async (deptId: string) => {
    if (!currentDecisionId) { setError("没有正在显示的决策"); return; }
    setRerunningDept(deptId);
    setError(null);
    const t0 = Date.now();
    try {
      const res = await fetchWithTimeout(
        `${backendUrl}/api/decision/rerun-dept/${currentDecisionId}/${encodeURIComponent(deptId)}`,
        { method: "POST" }, TIMEOUT_MS.decisionStart,
      );
      if (!res.ok) {
        if (res.status === 404) {
          setError("后端还没装重跑端点 — 暂时用左上角 ⚙️ 设置 → 重生该部门 prompt 后重新提问");
        } else {
          throw new Error(`rerun-dept ${res.status}`);
        }
        return;
      }
      const j = await res.json();
      const newSum: DecisionSummary = j.summary ?? j;
      newSum.elapsed_sec = (Date.now() - t0) / 1000;
      setSummary(newSum);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRerunningDept(null);
    }
  }, [backendUrl, currentDecisionId]);

  // --- 历史详情 ---
  const pickHistory = useCallback(async (decisionId: string) => {
    try {
      const res = await fetchWithTimeout(`${backendUrl}/api/memory/${mode}/decision/${decisionId}`, undefined, TIMEOUT_MS.default);
      if (!res.ok) throw new Error(`detail ${res.status}`);
      const j = await res.json();
      setSummary(j as DecisionSummary);
      setCurrentDecisionId(decisionId);
    } catch (e: unknown) {
      setError((e as Error).message ?? "读历史记录出问题了");
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
    <><Onboarding /><div style={{ maxWidth: 1200, margin: "0 auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Header */}
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22 }}>🐝 我的 AI 智囊团</h1>
          <div style={{ fontSize: 12, opacity: 0.6 }}>有问题? 让 6 位 AI 顾问一起帮你想.</div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {/* v7 档位(高/中/本地)已移到「⚙更多设置」展开区, 首页只留努力程度 */}
          {/* v7 主题深/浅切换 (成本/预算环已删) */}
          <button type="button" onClick={toggleTheme} title="深色/浅色切换"
            style={{
              padding: "6px 10px", fontSize: 14, borderRadius: 6, cursor: "pointer",
              border: "1px solid var(--border)", background: "var(--bg-subtle)", color: "inherit",
            }}>
            {theme === "dark" ? "🌙" : "☀️"}
          </button>
          {/* 通知类按钮带 badge, 必须外露 */}
          <LogsPanel backendUrl={backendUrl} />
          <PendingChangesDrawer backendUrl={backendUrl} />
          <NotificationBell backendUrl={backendUrl} />
          {/* 无状态的次要功能收进 ⋯ 菜单 */}
          <MoreMenu onSeeAI={() => setDashOpen(true)} />
          {/* 主操作: 设置 (黄色高亮) */}
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            style={{
              ...iconBtn,
              borderColor: "var(--accent)",
              background: "var(--accent-bg)",
              color: "var(--accent)",
              fontWeight: 700,
            }}
            title="AI 配置 / 记忆 / 高级 / 技术 都在这里"
          >⚙️ 设置</button>
        </div>
      </header>

      {/* v6-R: 删 ViewTabs, 主页只剩日常视图; 进阶/技术内容都进 SettingsDrawer */}
      {/* <ViewTabs value={view} onChange={setView} /> */}

      {/* v6-S1 首屏今天概览 */}
      <TodayOverviewCard
        backendUrl={backendUrl}
        onClickReview={() => { setSettingsInitialTab("memory"); setSettingsOpen(true); }}
      />

      {/* v6-S10 草稿恢复提示 */}
      {taskRestored && (
        <div style={{
          padding: "8px 12px", borderRadius: 6, fontSize: 12,
          background: "rgba(76,175,80,0.10)",
          borderWidth: 1, borderStyle: "solid", borderColor: "rgba(76,175,80,0.30)",
          color: "#a5d6a7", display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <span>♻️ 已恢复你上次没提交的任务草稿</span>
          <button type="button" onClick={() => { setTask(""); clearTaskBackup(); }}
                  style={{
                    padding: "2px 8px", fontSize: 11, borderRadius: 3, cursor: "pointer",
                    borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
                    background: "transparent", color: "var(--text-dim)",
                  }}>清掉</button>
        </div>
      )}

      {/* 用户视图 (默认) */}
      {view === "user" && (
        <>
          {/* v7 场景下拉 (输入框上方) — 完整场景/顾问团管理已移到 ⚙设置→场景 tab */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <ScenarioDropdown
              selected={mode}
              onSelect={setMode}
              onManage={() => { setSettingsInitialTab("scenario"); setSettingsOpen(true); }}
              backendUrl={backendUrl}
            />
            <span style={{ fontSize: 11, opacity: 0.5 }}>切换场景 = 换一套专科顾问团</span>
          </div>

          {/* v7 输入框置顶 */}
          <div onPaste={onPaste} onDrop={onDrop} onDragOver={onDragOver}>
            <TaskInput value={task} onChange={setTask} />
            <ImageStrip
              images={images}
              docFiles={docFiles}
              onAdd={addAttachment}
              onRemove={removeImageAt}
              onRemoveDoc={removeDocAt}
              warn={attachWarn}
              max={10}
            />
          </div>

          {/* v7 努力程度滑块 (方案C) */}
          <DifficultySlider
            value={difficulty}
            aiSuggested={aiSuggested}
            aiReason={aiReason}
            onChange={setDifficulty}
          />

          {/* v7 开始 + ⚙更多设置(展开精细路线) */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={runByEffort}
              disabled={busy || !task.trim()}
              style={{
                padding: "12px 24px", fontSize: 16, fontWeight: 600, borderRadius: 8, border: "none",
                background: busy ? "var(--accent-bg)" : "var(--accent)", color: "#000",
                cursor: busy ? "not-allowed" : "pointer",
              }}
            >
              {busy ? "🐝 顾问们在讨论, 请稍等..." : "🚀 开始"}
            </button>
            <button type="button" onClick={() => setMoreSettings((v) => !v)}
              style={{
                padding: "10px 14px", fontSize: 13, borderRadius: 8,
                border: "1px solid var(--border-strong)", background: "var(--bg-subtle)",
                color: "inherit", cursor: "pointer",
              }}>
              ⚙ 更多设置 {moreSettings ? "▴" : "▾"}
            </button>
            {error && <span style={{ color: "#f87171", fontSize: 13 }}>{error}</span>}
          </div>

          {/* v7 ⚙更多设置展开: 档位 + CEO 预分析 + 5路线×3轮数 精细控制 */}
          {moreSettings && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {/* 档位 高/中/本地 — 带费用说明 (用户要直观) */}
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span style={{ fontSize: 12, opacity: 0.7 }}>🧠 用多好的脑子 (默认高档; 想省钱/离线再调):</span>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {([
                    { t: "A", emoji: "🟡", name: "高档", desc: "旗舰最准", cost: "约 ¥1/次", color: "var(--accent)" },
                    { t: "B", emoji: "🔵", name: "中档", desc: "便宜云够用", cost: "约 ¥0.1/次", color: "var(--info)" },
                    { t: "C", emoji: "⚪", name: "本地", desc: "离线·慢", cost: "免费", color: "#a0a0a0" },
                  ] as const).map((o) => {
                    const active = tier === o.t;
                    return (
                      <button key={o.t} type="button" onClick={() => setTier(o.t as "A" | "B" | "C")}
                        style={{
                          flex: "1 1 130px", minWidth: 120, padding: "8px 12px", borderRadius: 8, cursor: "pointer",
                          textAlign: "left", color: "inherit",
                          borderWidth: active ? 2 : 1, borderStyle: "solid",
                          borderColor: active ? o.color : "var(--border)",
                          background: active ? "var(--bg-hover)" : "var(--bg-subtle)",
                        }}>
                        <div style={{ fontSize: 13, fontWeight: 600 }}>{o.emoji} {o.name}</div>
                        <div style={{ fontSize: 11, opacity: 0.6 }}>{o.desc}</div>
                        <div style={{ fontSize: 11, fontWeight: 600, color: o.color, marginTop: 2 }}>{o.cost}</div>
                      </button>
                    );
                  })}
                </div>
              </div>
              <RoutePlanner
                backendUrl={backendUrl}
                task={task}
                modeId={mode}
                images={images}
                docFiles={docFiles}
                busy={busy}
                onRun={runWithRoute}
              />
            </div>
          )}

          <ResultPanel summary={summary} onRerunDept={rerunDept} rerunningDept={rerunningDept} onFeedback={sendFeedback} />
          <HistoryPanel rows={history} onPick={pickHistory} backendUrl={backendUrl} />
        </>
      )}

      {/* v6-R 高级视图已迁移到 SettingsDrawer; 这里整段被注释掉 */}
      {false && view === "advanced" && (
        <>
          <ModePicker selected={mode} onSelect={setMode} onOpenCustom={() => {}} />
          <TaskInput value={task} onChange={setTask} />
          <DifficultySlider value={difficulty} aiSuggested={aiSuggested} aiReason={aiReason} estimateText={estimateText} onChange={setDifficulty} />
          <SettingsPanel />
          {/* v6 修脱节: 把后端做好却没 UI 露出的功能挂在这里 */}
          <ReviewPanel backendUrl={backendUrl} />
          <BackupConfigPanel backendUrl={backendUrl} />
          <UpgradeLogPanel backendUrl={backendUrl} />
          {/* v6-P 3 个专家工具折叠 + 加说明; 多数人不用点 */}
          <details style={{
            padding: 12, borderRadius: 8,
            background: "var(--bg-subtle)",
            borderWidth: 1, borderStyle: "solid",
            borderColor: "var(--border)",
          }}>
            <summary style={{
              cursor: "pointer", fontSize: 13, fontWeight: 600, color: "var(--info)",
            }}>
              🧠 思考方法 (默认 AI 自己选, 一般不用动)
            </summary>
            <div style={{
              fontSize: 11, color: "var(--text-dim)", marginTop: 8, marginBottom: 10,
              lineHeight: 1.6, padding: 8, borderRadius: 4,
              background: "var(--info-bg)",
            }}>
              <b>这是什么:</b> 8 套思考方法 (Chain-of-Thought / Tree-of-Thoughts / Self-Ask / Reflexion ...).
              AI 分诊官会根据你的任务自动选 0-2 个最合适的, 不需要你操心.
              <br/><b>什么时候动手:</b> 你想强制让 AI 用某个特定方法时 (例如 "我就要它走 ToT"); 否则保持默认.
            </div>
            <ThinkingFrameworksPanel enabled={frameworks} aiPicked={aiFrameworks} onToggle={toggleFramework} />
          </details>

          <details style={{
            padding: 12, borderRadius: 8,
            background: "var(--bg-subtle)",
            borderWidth: 1, borderStyle: "solid",
            borderColor: "var(--border)",
          }}>
            <summary style={{
              cursor: "pointer", fontSize: 13, fontWeight: 600, color: "#ffb300",
            }}>
              🧬 基因编辑器 (高级 / 给开发者: 直接编辑某部门的 system prompt 模板)
            </summary>
            <div style={{
              fontSize: 11, color: "var(--text-dim)", marginTop: 8, marginBottom: 10,
              lineHeight: 1.6, padding: 8, borderRadius: 4,
              background: "rgba(255,179,0,0.06)",
            }}>
              <b>这是什么:</b> "基因" = 某个部门的底层 system prompt + 方法论.
              蜂群每天会自演化 (p4 / p8 / p15), 你也可以人工改.
              <br/><b>什么时候动手:</b> 你看了某部门多次给出离谱回答, 想直接覆盖它的 prompt 时;
              建议先用 "👤 团队管理" 里的 "重生成 persona" 试一次, 还不行才来这里.
            </div>
            <GeneEditor />
          </details>

          <details style={{
            padding: 12, borderRadius: 8,
            background: "var(--bg-subtle)",
            borderWidth: 1, borderStyle: "solid",
            borderColor: "var(--border)",
          }}>
            <summary style={{
              cursor: "pointer", fontSize: 13, fontWeight: 600, color: "#ce93d8",
            }}>
              📝 自定义场景 YAML (高级 / 给开发者: 写一个新场景)
            </summary>
            <div style={{
              fontSize: 11, color: "var(--text-dim)", marginTop: 8, marginBottom: 10,
              lineHeight: 1.6, padding: 8, borderRadius: 4,
              background: "rgba(206,147,216,0.06)",
            }}>
              <b>这是什么:</b> 现有 14 个内置场景 (家庭医生 / 法律 / 创业...) 如果不满足你的需求,
              你可以在这里写 YAML 加新场景 (mode_id + 部门列表 + 默认 prompt 种子).
              <br/><b>什么时候动手:</b> 14 个场景里没有你想要的; 否则保持默认.
            </div>
            <ScenarioYamlAuthor />
          </details>
          <div>
            <button type="button" onClick={startDecision} disabled={busy || !task.trim()} style={{ padding: "10px 20px", borderRadius: 8, border: "1px solid #facc15", background: "var(--accent-bg)", color: "inherit", cursor: busy ? "not-allowed" : "pointer" }}>
              {busy ? "🐝 讨论中, 等等..." : "🚀 开始让 AI 帮忙(高级)"}
            </button>
          </div>
          <ResultPanel summary={summary} onRerunDept={rerunDept} rerunningDept={rerunningDept} />
        </>
      )}

      {/* v6-R 工程视图已迁移到 SettingsDrawer; 这里整段被注释掉 */}
      {false && view === "engineer" && (
        <>
          <div style={{ padding: 12, borderRadius: 10, background: "var(--accent-bg)", border: "1px solid var(--accent-bg)", fontSize: 12 }}>
            🔧 技术视图 - 给会写代码的人看的. 沙箱跑命令 / AI 自我学习对比 / 系统升级状态 三件套.
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
        flowText={"你的任务 → AI 分析需要哪些顾问 → 6 位顾问同时思考 → 综合给你答案"}
      />

      <ClarifyAndPlanModal
        backendUrl={backendUrl}
        task={task}
        modeId={mode}
        open={clarifyOpen}
        onCancel={() => setClarifyOpen(false)}
        onConfirm={runDecisionWith}
      />

      <SettingsDrawer
        open={settingsOpen}
        onClose={() => { setSettingsOpen(false); setSettingsInitialTab(undefined); }}
        backendUrl={backendUrl}
        frameworks={frameworks}
        aiFrameworks={aiFrameworks}
        onToggleFramework={toggleFramework}
        initialTab={settingsInitialTab}
      />

      {/* v6-S2 全局快捷搜索 Cmd/Ctrl+K */}
      <CommandPalette
        backendUrl={backendUrl}
        modes={BUILTIN_MODES.map((m: ModeOption) => ({ mode_id: m.mode_id, label: m.label }))}
        onPickMode={setMode}
        onPickDecision={(did, mid) => { setMode(mid); setTimeout(() => pickHistory(did), 50); }}
        onOpenSettings={() => setSettingsOpen(true)}
      />
    </div></>);
}

const iconBtn = {
  padding: "8px 12px",
  borderRadius: 6,
  border: "1px solid var(--border)",
  background: "var(--bg-subtle)",
  cursor: "pointer",
  color: "inherit",
  fontFamily: "inherit",
  fontSize: 12,
};

/** v6-S/E 把无状态次要按钮收进一个 ⋯ 菜单 (趋势 / 看 AI 干活) */
function MoreMenu({ onSeeAI }: { onSeeAI: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ position: "relative" }}>
      <button type="button" onClick={() => setOpen((v) => !v)}
        title="更多工具" style={{ ...iconBtn, padding: "8px 10px" }}>⋯ 更多</button>
      {open && (
        <>
          <div onClick={() => setOpen(false)}
               style={{ position: "fixed", inset: 0, zIndex: 200 }} />
          <div style={{
            position: "absolute", top: "calc(100% + 4px)", right: 0,
            minWidth: 200, padding: 6, borderRadius: 8, zIndex: 201,
            background: "var(--bg-card)",
            borderWidth: 1, borderStyle: "solid", borderColor: "var(--border-strong)",
            boxShadow: "0 10px 30px rgba(0,0,0,0.5)",
            display: "flex", flexDirection: "column", gap: 2,
          }}>
            <button type="button" onClick={() => { onSeeAI(); setOpen(false); }}
              style={menuItemStyle}>🐝 看 AI 怎么干活</button>
            <a href="/trends" onClick={() => setOpen(false)}
              style={{ ...menuItemStyle, textDecoration: "none" }}>🌍 全球 AI 趋势</a>
          </div>
        </>
      )}
    </div>
  );
}

const menuItemStyle: CSSProperties = {
  padding: "8px 12px", fontSize: 13, borderRadius: 4, cursor: "pointer",
  background: "transparent", color: "var(--text)", textAlign: "left",
  border: "none", display: "block",
};
