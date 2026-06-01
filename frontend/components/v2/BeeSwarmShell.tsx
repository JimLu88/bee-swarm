"use client";

import {
  useCallback, useEffect, useMemo, useRef, useState,
  type ClipboardEvent as ReactClipboardEvent, type DragEvent as ReactDragEvent,
} from "react";
import { httpToWsOrigin, resolveBackendHttpBase } from "../../lib/backend";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

import { BUILTIN_MODES, type ModeOption } from "./ModePicker";
import { ImageStrip } from "./ImageStrip";
import { RoutePlanner, type RunParams } from "./RoutePlanner";
import { type Difficulty } from "./DifficultySlider";
import { ResultPanel, type DecisionSummary } from "./ResultPanel";
import { type HistoryRow } from "./HistoryPanel";
import { SettingsDrawer } from "./SettingsDrawer";
import { SwarmDashboardModal, type DeptHeat } from "./SwarmDashboardModal";
import { Onboarding } from "./Onboarding";
import { NotificationBell } from "./NotificationBell";
import { PendingChangesDrawer } from "./PendingChangesDrawer";
import { CommandPalette } from "./CommandPalette";
import { useAutosave } from "../../lib/useAutosave";

import { Icon } from "./Icon";
import { Sidebar } from "./Sidebar";
import { SceneSwitcher } from "./SceneSwitcher";
import { Composer } from "./Composer";
import { SwarmStrip } from "./SwarmStrip";
import { RouteFlow } from "./RouteFlow";
import { sceneSuggestions } from "../../lib/scenes";

/**
 * BeeSwarmShell — v8 Jim Clear + Gemini 对话式主壳.
 * 侧栏(Sidebar) + 顶栏(SceneSwitcher) + 居中对话流(turns) + 底部 Composer.
 * 决策链路(WebSocket / REST / bandit)完全沿用, 仅重排 UI.
 */

type View = "welcome" | "thread";

type Turn = {
  id: string;
  user: string;
  images?: string[];
  docNames?: string[];
  effort: Difficulty;
  summary?: DecisionSummary | null;
  status: "running" | "done" | "error";
  decisionId?: string;
  rounds: number;
};

const EFFORT_MAP: Record<Difficulty, { route: string; rounds: number; band: string; diff: string }> = {
  1: { route: "ceo_only", rounds: 0, band: "light", diff: "light" },
  2: { route: "all", rounds: 1, band: "light", diff: "medium" },
  3: { route: "all", rounds: 2, band: "medium", diff: "medium" },
  4: { route: "all", rounds: 3, band: "heavy", diff: "heavy" },
};

function makeId(): string {
  try {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  } catch { /* ignore */ }
  return "t" + Date.now() + "-" + Math.floor(Math.random() * 1e6);
}

/** 完成态/历史的 turn → 由 dept_reports 反推 heats (全 done) */
function deriveHeats(summary?: DecisionSummary | null): DeptHeat[] {
  const reports = summary?.dept_reports ?? [];
  return reports.map((r) => ({
    dept: r.dept ?? "?",
    heat: 1,
    status: "done" as const,
    confidence: r.confidence_score,
    opinion: r.consensus,
  }));
}

export function BeeSwarmShell() {
  // --- shell state ---
  const [view, setView] = useState<View>("welcome");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [railCollapsed, setRailCollapsed] = useState(false);

  // --- core decision state ---
  const [mode, setMode] = useState<string>("program_management");
  const { value: task, setValue: setTask, clear: clearTaskBackup } = useAutosave<string>("task-input", "");
  const [difficulty, setDifficulty] = useState<Difficulty>(3);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryRow[]>([]);
  // 部门 id → 中文名 (当前场景), 用于把 internal_med 等英文 id 显示成中文 + 防溢出
  const [deptLabels, setDeptLabels] = useState<Record<string, string>>({});
  // 用户「我来挑部门/路线」展开 RoutePlanner
  const [showRoute, setShowRoute] = useState(false);

  // settings drawer
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsInitialTab, setSettingsInitialTab] = useState<"scenario" | "ai" | "memory" | "advanced" | "tech" | undefined>(undefined);

  // tier A/B/C (SSR-safe)
  const [tier, setTierState] = useState<"A" | "B" | "C">("A");
  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem("h-semas:tier") as "A" | "B" | "C" | null;
    if (saved === "B" || saved === "C") setTierState(saved);
  }, []);
  const cycleTier = useCallback(() => {
    setTierState((prev) => {
      const next = prev === "A" ? "B" : prev === "B" ? "C" : "A";
      if (typeof window !== "undefined") {
        try { window.localStorage.setItem("h-semas:tier", next); } catch { /* ignore */ }
      }
      return next;
    });
  }, []);

  // attachments
  const [images, setImages] = useState<string[]>([]);
  const [docFiles, setDocFiles] = useState<{ name: string; content_b64: string }[]>([]);
  const [attachWarn, setAttachWarn] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const readAsDataUrl = (file: File): Promise<string> => new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result || ""));
    r.onerror = () => reject(new Error("read failed"));
    r.readAsDataURL(file);
  });

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
  const openFilePicker = useCallback(() => fileInputRef.current?.click(), []);
  const onFilePicked = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    for (const f of files) void addAttachment(f);
    e.target.value = "";
  }, [addAttachment]);

  // live deliberation state (single active decision)
  const [heats, setHeats] = useState<DeptHeat[]>([]);
  const [progress, setProgress] = useState<number>(0);
  const [dashOpen, setDashOpen] = useState(false);

  const decisionStartRef = useRef<number | null>(null);
  const [rerunningDept, setRerunningDept] = useState<string | null>(null);
  const [currentDecisionId, setCurrentDecisionId] = useState<string | null>(null);
  const [runMeta, setRunMeta] = useState<{ route: string; rounds_band: string; difficulty: string } | null>(null);

  // thinking frameworks (AI 自动选; SettingsDrawer 可手动改)
  const [frameworks, setFrameworks] = useState<string[]>([]);
  const [aiFrameworks, setAiFrameworks] = useState<string[]>([]);

  // backend URL
  const backendUrl = useMemo(() => resolveBackendHttpBase(), []);
  const wsBase = useMemo(() => httpToWsOrigin(backendUrl), [backendUrl]);

  // 主题: 默认 light (与设计稿一致), SSR-safe
  const [theme, setTheme] = useState<"light" | "dark">("light");
  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem("h-semas:theme");
    const t = saved === "dark" ? "dark" : "light";
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

  // rail collapse → body class (CSS 控制)
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.body.classList.toggle("rail-collapsed", railCollapsed);
  }, [railCollapsed]);

  // --- AI 自动判断思考方法 (防抖); 仅用于 framework 建议 ---
  const estTimer = useRef<number | null>(null);
  useEffect(() => {
    if (!task.trim()) { setAiFrameworks([]); return; }
    if (estTimer.current) window.clearTimeout(estTimer.current);
    estTimer.current = window.setTimeout(async () => {
      try {
        const res = await fetchWithTimeout(
          `${backendUrl}/api/decision/estimate`,
          {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task, mode_id: mode, debate_rounds: EFFORT_MAP[difficulty].rounds || 1 }),
          },
          TIMEOUT_MS.default,
        );
        if (!res.ok) return;
        const j = await res.json();
        if (Array.isArray(j.suggested_frameworks)) setAiFrameworks(j.suggested_frameworks);
      } catch { /* silent */ }
    }, 700) as unknown as number;
    return () => { if (estTimer.current) window.clearTimeout(estTimer.current); };
  }, [task, mode, difficulty, backendUrl]);

  useEffect(() => {
    if (frameworks.length === 0 && aiFrameworks.length > 0) setFrameworks(aiFrameworks);
  }, [aiFrameworks, frameworks.length]);

  const toggleFramework = useCallback((id: string) => {
    setFrameworks((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  }, []);

  // --- 历史 ---
  const refreshHistory = useCallback(async () => {
    try {
      const res = await fetchWithTimeout(`${backendUrl}/api/memory/${mode}?limit=30&compact=1`, undefined, TIMEOUT_MS.default);
      if (!res.ok) throw new Error(`memory ${res.status}`);
      const j = await res.json();
      const rows: HistoryRow[] = Array.isArray(j?.items) ? j.items : Array.isArray(j) ? j : [];
      setHistory(rows);
    } catch {
      setHistory([]);
    }
  }, [backendUrl, mode]);
  useEffect(() => { refreshHistory(); }, [refreshHistory]);

  // 拉当前场景的部门中文名映射 (department_labels)
  useEffect(() => {
    let aborted = false;
    (async () => {
      try {
        const res = await fetchWithTimeout(`${backendUrl}/api/modes/lookup/${mode}`, undefined, TIMEOUT_MS.default);
        if (!res.ok) return;
        const j = await res.json();
        const labels = (j?.department_labels ?? j?.mode?.department_labels) as Record<string, string> | undefined;
        if (!aborted && labels && typeof labels === "object") setDeptLabels(labels);
      } catch { /* 没有就回退英文 id */ }
    })();
    return () => { aborted = true; };
  }, [backendUrl, mode]);

  // --- WebSocket 流 → 更新 live turn ---
  const attachStream = useCallback((decisionId: string, turnId: string) => {
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
          setHeats(depts.map((d) => ({ dept: d, heat: 0, status: "running" as const })));
        } else if (e.type === "dept_done") {
          const d = String(e.payload?.dept ?? "");
          const conf = e.payload?.confidence;
          setHeats((prev) => prev.map((h) => h.dept === d
            ? { ...h, heat: 1, status: "done", confidence: typeof conf === "number" ? conf : h.confidence, callCount: (h.callCount ?? 0) + 1, opinion: e.payload?.consensus }
            : h));
          setProgress((p) => Math.min(95, p + 8));
        } else if (e.type === "decision_done") {
          setProgress(100);
          const _sum = (e.payload as { summary?: DecisionSummary }).summary ?? (e.payload as DecisionSummary);
          if (decisionStartRef.current) _sum.elapsed_sec = (Date.now() - decisionStartRef.current) / 1000;
          setTurns((prev) => prev.map((t) => t.id === turnId
            ? { ...t, summary: _sum, status: "done", decisionId: _sum.decision_id ?? decisionId }
            : t));
          if (_sum.decision_id) setActiveId(_sum.decision_id);
          setBusy(false);
          refreshHistory();
          ws.close();
        } else if (e.type === "debate_converged") {
          setProgress(90);
        }
      } catch { /* ignore */ }
    };
    ws.onerror = () => {
      setError("和 AI 的连接断了, 刷新一下重试");
      setBusy(false);
      setTurns((prev) => prev.map((t) => t.id === turnId && t.status === "running" ? { ...t, status: "error" } : t));
    };
    ws.onclose = () => { /* ok */ };
  }, [wsBase, refreshHistory]);

  // --- 发起咨询 (Composer 发送 / 建议卡片 / 重新生成) ---
  const submitTask = useCallback((text: string) => {
    const t = text.trim();
    if (!t) { setError("先写一句话告诉我你要什么"); return; }
    if (busy) return;
    setError(null);

    const eff = difficulty;
    const m = EFFORT_MAP[eff];
    const turnId = makeId();
    const curImages = images;
    const curDocs = docFiles;

    setTurns((prev) => [...prev, {
      id: turnId, user: t, effort: eff, status: "running", summary: null, rounds: m.rounds,
      images: curImages.length ? curImages : undefined,
      docNames: curDocs.length ? curDocs.map((d) => d.name) : undefined,
    }]);
    setView("thread");
    setActiveId(turnId);
    setBusy(true); setHeats([]); setProgress(0);
    setRunMeta({ route: m.route, rounds_band: m.band, difficulty: m.diff });

    (async () => {
      try {
        const res = await fetchWithTimeout(
          `${backendUrl}/api/decision/start`,
          {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              task: t, mode_id: mode,
              debate_rounds: Math.max(m.rounds, 1),
              thinking_frameworks: frameworks.length > 0 ? frameworks : undefined,
              tier, images: curImages, files: curDocs,
              route: m.route, departments_override: [], difficulty_bucket: m.diff,
            }),
          },
          TIMEOUT_MS.decisionStart,
        );
        if (!res.ok) throw new Error(`decision/start ${res.status}`);
        const j = await res.json();
        const decisionId: string | undefined = j?.decision_id;
        if (!decisionId) throw new Error("AI 服务暂时没响应, 等一下再试");
        clearTaskBackup(); setImages([]); setDocFiles([]);
        attachStream(decisionId, turnId);
      } catch (e: unknown) {
        setError((e as Error).message ?? "出了点小问题, 等一下重试");
        setBusy(false);
        setTurns((prev) => prev.map((tt) => tt.id === turnId ? { ...tt, status: "error" } : tt));
      }
    })();
  }, [busy, difficulty, images, docFiles, mode, frameworks, tier, backendUrl, clearTaskBackup, attachStream]);

  const onComposerSend = useCallback(() => { submitTask(task); }, [submitTask, task]);

  // RoutePlanner「我来挑部门/路线」→ 按指定 route/部门/轮数发起
  const runWithRoute = useCallback((p: RunParams) => {
    const t = task.trim();
    if (!t) { setError("先写一句话告诉我你要什么"); return; }
    if (busy) return;
    setError(null);
    setShowRoute(false);

    const turnId = makeId();
    const curImages = images;
    const curDocs = docFiles;
    const effGuess: Difficulty = p.rounds >= 3 ? 4 : p.rounds === 2 ? 3 : p.route === "ceo_only" ? 1 : 2;

    setTurns((prev) => [...prev, {
      id: turnId, user: t, effort: effGuess, status: "running", summary: null, rounds: p.rounds,
      images: curImages.length ? curImages : undefined,
      docNames: curDocs.length ? curDocs.map((d) => d.name) : undefined,
    }]);
    setView("thread");
    setActiveId(turnId);
    setBusy(true); setHeats([]); setProgress(0);
    setRunMeta({ route: p.route, rounds_band: p.rounds_band, difficulty: p.difficulty });

    (async () => {
      try {
        const res = await fetchWithTimeout(
          `${backendUrl}/api/decision/start`,
          {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              task: t, mode_id: mode,
              debate_rounds: Math.max(p.rounds, 1),
              thinking_frameworks: frameworks.length > 0 ? frameworks : undefined,
              tier, images: curImages, files: curDocs,
              route: p.route, departments_override: p.departments, difficulty_bucket: p.difficulty,
            }),
          },
          TIMEOUT_MS.decisionStart,
        );
        if (!res.ok) throw new Error(`decision/start ${res.status}`);
        const j = await res.json();
        const decisionId: string | undefined = j?.decision_id;
        if (!decisionId) throw new Error("AI 服务暂时没响应, 等一下再试");
        clearTaskBackup(); setImages([]); setDocFiles([]);
        attachStream(decisionId, turnId);
      } catch (e: unknown) {
        setError((e as Error).message ?? "出了点小问题, 等一下重试");
        setBusy(false);
        setTurns((prev) => prev.map((tt) => tt.id === turnId ? { ...tt, status: "error" } : tt));
      }
    })();
  }, [task, busy, images, docFiles, mode, frameworks, tier, backendUrl, clearTaskBackup, attachStream]);

  // v10 路线图「重新会诊」: 用调整后的部门集重跑同一个问题 (route=multi + departments_override)
  const rerunWithDepts = useCallback((userText: string, depts: string[]) => {
    const t = (userText || "").trim();
    if (!t || busy) return;
    setError(null);
    const rounds = Math.max(EFFORT_MAP[difficulty].rounds, 1);
    const turnId = makeId();
    setTurns((prev) => [...prev, {
      id: turnId, user: t, effort: difficulty, status: "running", summary: null, rounds,
    }]);
    setView("thread"); setActiveId(turnId);
    setBusy(true); setHeats([]); setProgress(0);
    setRunMeta({ route: "multi", rounds_band: EFFORT_MAP[difficulty].band, difficulty: EFFORT_MAP[difficulty].diff });
    (async () => {
      try {
        const res = await fetchWithTimeout(
          `${backendUrl}/api/decision/start`,
          {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              task: t, mode_id: mode, debate_rounds: rounds,
              thinking_frameworks: frameworks.length > 0 ? frameworks : undefined,
              tier, route: "multi", departments_override: depts,
              difficulty_bucket: EFFORT_MAP[difficulty].diff,
            }),
          },
          TIMEOUT_MS.decisionStart,
        );
        if (!res.ok) throw new Error(`decision/start ${res.status}`);
        const j = await res.json();
        const decisionId: string | undefined = j?.decision_id;
        if (!decisionId) throw new Error("AI 服务暂时没响应, 等一下再试");
        attachStream(decisionId, turnId);
      } catch (e: unknown) {
        setError((e as Error).message ?? "出了点小问题, 等一下重试");
        setBusy(false);
        setTurns((prev) => prev.map((tt) => tt.id === turnId ? { ...tt, status: "error" } : tt));
      }
    })();
  }, [busy, difficulty, mode, frameworks, tier, backendUrl, attachStream]);

  // 反馈 → bandit
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

  // 重跑某部门
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
        if (res.status === 404) setError("后端还没装重跑端点 — 暂时在 ⚙ 设置里重生该部门 prompt 后重新提问");
        else throw new Error(`rerun-dept ${res.status}`);
        return;
      }
      const j = await res.json();
      const newSum: DecisionSummary = j.summary ?? j;
      newSum.elapsed_sec = (Date.now() - t0) / 1000;
      setTurns((prev) => prev.map((t) => t.decisionId === currentDecisionId ? { ...t, summary: newSum } : t));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRerunningDept(null);
    }
  }, [backendUrl, currentDecisionId]);

  // --- 历史详情 → 单 turn 展示 ---
  const pickHistory = useCallback(async (decisionId: string) => {
    try {
      const res = await fetchWithTimeout(`${backendUrl}/api/memory/${mode}/decision/${decisionId}`, undefined, TIMEOUT_MS.default);
      if (!res.ok) throw new Error(`detail ${res.status}`);
      const j = await res.json() as DecisionSummary;
      setCurrentDecisionId(decisionId);
      setRunMeta(null);
      setTurns([{
        id: makeId(), user: j.task ?? "(历史咨询)", effort: 3, status: "done",
        summary: j, decisionId, rounds: 2,
      }]);
      setActiveId(decisionId);
      setView("thread");
    } catch (e: unknown) {
      setError((e as Error).message ?? "读历史记录出问题了");
    }
  }, [backendUrl, mode]);

  // 新咨询
  const newConsult = useCallback(() => {
    setTurns([]);
    setActiveId(null);
    setView("welcome");
    setError(null);
    setHeats([]); setProgress(0);
    setCurrentDecisionId(null);
  }, []);

  const openSettings = useCallback((tab?: "scenario" | "ai" | "memory" | "advanced" | "tech") => {
    setSettingsInitialTab(tab);
    setSettingsOpen(true);
  }, []);

  const suggestions = useMemo(() => sceneSuggestions(mode), [mode]);

  // 附件预览 slot (Composer 上方)
  const attachSlot = (images.length > 0 || docFiles.length > 0 || attachWarn) ? (
    <div style={{ marginBottom: 8 }}>
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
  ) : null;

  const composer = (
    <>
      {showRoute && (
        <div style={{ marginBottom: 10 }}>
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
      <Composer
        value={task}
        onChange={setTask}
        effort={difficulty}
        onEffortChange={setDifficulty}
        tier={tier}
        onTierChange={(t) => {
          setTierState(t);
          if (typeof window !== "undefined") {
            try { window.localStorage.setItem("h-semas:tier", t); } catch { /* ignore */ }
          }
        }}
        onSend={onComposerSend}
        onAttach={openFilePicker}
        busy={busy}
        error={error}
        attachSlot={attachSlot}
        frameworks={frameworks}
        aiFrameworks={aiFrameworks}
        onToggleFramework={toggleFramework}
      />
      {/* v10 移除首页"我来挑部门/路线"预选 — 部门调整统一在提问后的路线图上做 */}
    </>
  );

  return (
    <div className="app" onPaste={onPaste} onDrop={onDrop} onDragOver={onDragOver}>
      <Onboarding />
      <input ref={fileInputRef} type="file" multiple onChange={onFilePicked} style={{ display: "none" }} />

      <Sidebar
        history={history}
        activeId={activeId}
        onNewConsult={newConsult}
        onPickHistory={pickHistory}
        onOpenScenario={() => openSettings("scenario")}
        onOpenSwarm={() => setDashOpen(true)}
        onOpenSettings={() => openSettings(undefined)}
        onCollapse={() => setRailCollapsed(true)}
        tier={tier}
        onUserClick={cycleTier}
      />

      <div className="main">
        <header className="topbar">
          <div className="topbar-l">
            {railCollapsed && (
              <button type="button" className="ghost-btn" onClick={() => setRailCollapsed(false)} title="展开侧栏" aria-label="展开侧栏">
                <Icon name="menu" />
              </button>
            )}
            <SceneSwitcher
              selected={mode}
              onSelect={setMode}
              onManage={() => openSettings("scenario")}
              backendUrl={backendUrl}
            />
          </div>
          <div className="topbar-r">
            <button type="button" className="ghost-btn" onClick={toggleTheme} title="深色 / 浅色" aria-label="切换主题">
              <Icon name={theme === "dark" ? "light_mode" : "dark_mode"} />
            </button>
            <NotificationBell backendUrl={backendUrl} />
            <PendingChangesDrawer backendUrl={backendUrl} />
            <button type="button" className="ghost-btn" onClick={() => setDashOpen(true)} title="看顾问怎么协作" aria-label="帮助">
              <Icon name="help" />
            </button>
          </div>
        </header>

        <div className="scroll app-scroll">
          {view === "welcome" ? (
            <section className="welcome">
              <h1 className="greet">你好，<span className="grad">今天想解决什么？</span></h1>
              <p className="greet-sub">
                把你正在纠结的事写下来。我会先分诊，再请这套场景里最合适的几位顾问一起讨论，给你一个能落地的答案。
              </p>
              <div className="sugs">
                {suggestions.map((s, i) => (
                  <button key={i} type="button" className="sug" onClick={() => submitTask(s.text)}>
                    <Icon name={s.icon} />
                    <span className="t">{s.text}</span>
                  </button>
                ))}
              </div>
              <div className="composer-inline">{composer}</div>
            </section>
          ) : (
            <section className="thread">
              {turns.map((turn, ti) => {
                const isLast = ti === turns.length - 1;
                const liveThis = turn.status === "running";
                const turnHeats = liveThis ? heats : deriveHeats(turn.summary);
                return (
                  <div key={turn.id} className="turn fade-up">
                    {/* 用户气泡 */}
                    <div className="user-row">
                      <div className="user-bubble">
                        {turn.user}
                        {(turn.images?.length || turn.docNames?.length) ? (
                          <div className="user-atts">
                            {turn.images?.map((_, ii) => (
                              <span key={"img" + ii} className="att-chip"><Icon name="image" />图片 {ii + 1}</span>
                            ))}
                            {turn.docNames?.map((n, ii) => (
                              <span key={"doc" + ii} className="att-chip"><Icon name="description" />{n}</span>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    </div>

                    {/* AI 回答 */}
                    <div className="ai-row">
                      <div className="spark"><Icon name="auto_awesome" fill /></div>
                      <div className="ai-body">
                        <SwarmStrip
                          heats={turnHeats}
                          running={liveThis}
                          done={turn.status === "done"}
                          rounds={turn.rounds || 2}
                          progress={liveThis ? progress : 100}
                          labels={deptLabels}
                        />
                        {turn.status === "done" && turnHeats.length > 0 && (
                          <RouteFlow
                            heats={turnHeats}
                            labels={deptLabels}
                            personas={((turn.summary as unknown as { team_personas_used?: { persona_id?: string; role?: string; dept_id?: string; model?: string }[] })?.team_personas_used) || []}
                            candidates={Object.keys(deptLabels)}
                            editable={isLast && !busy}
                            busy={busy}
                            onRerun={(depts) => rerunWithDepts(turn.user, depts)}
                          />
                        )}
                        {turn.status === "error" && (
                          <div className="callout warn">
                            <div className="callout-h"><Icon name="error" />出了点问题</div>
                            <div className="risk"><Icon name="chevron_right" /><span className="rt">{error ?? "AI 服务暂时没响应, 换个说法或稍后重试"}</span></div>
                          </div>
                        )}
                        {turn.status === "done" && turn.summary && (
                          <ResultPanel
                            summary={turn.summary}
                            effort={turn.effort}
                            onRerunDept={isLast ? rerunDept : undefined}
                            rerunningDept={rerunningDept}
                            onFeedback={isLast && runMeta ? sendFeedback : undefined}
                            onRegenerate={isLast ? () => submitTask(turn.user) : undefined}
                          />
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </section>
          )}
        </div>

        {/* 底部常驻 composer (thread 态) */}
        {view === "thread" && (
          <div className="composer-wrap">{composer}</div>
        )}
      </div>

      {/* --- 弹层 / 抽屉 (逻辑不动) --- */}
      <SwarmDashboardModal
        open={dashOpen}
        onClose={() => setDashOpen(false)}
        heats={heats}
        progressPct={progress > 0 ? progress : undefined}
        labels={deptLabels}
      />

      <SettingsDrawer
        open={settingsOpen}
        onClose={() => { setSettingsOpen(false); setSettingsInitialTab(undefined); }}
        backendUrl={backendUrl}
        frameworks={frameworks}
        aiFrameworks={aiFrameworks}
        onToggleFramework={toggleFramework}
        initialTab={settingsInitialTab}
        mode={mode}
        onSelectMode={setMode}
      />

      <CommandPalette
        backendUrl={backendUrl}
        modes={BUILTIN_MODES.map((m: ModeOption) => ({ mode_id: m.mode_id, label: m.label }))}
        onPickMode={setMode}
        onPickDecision={(did, mid) => { setMode(mid); setTimeout(() => pickHistory(did), 50); }}
        onOpenSettings={() => setSettingsOpen(true)}
      />
    </div>
  );
}
