"use client";

/** v13 开发模式面板: 群晖指挥 PC 上的 Claude Code 写码.
 *  填需求 + PC 仓库路径 → 启动 → WS 看进度(规划/任务/测试/评审)→ PR 闸门批准合并.
 *  需 PC 常驻 bee-agent-hands(:8002, 已登录 claude). 数据走 /api/dev/*. */

import { useCallback, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";
import { httpToWsOrigin } from "../../lib/backend";
import { getAuthToken } from "../../lib/auth";

type DevEvent = { type: string; payload: Record<string, unknown> };

export function DevModePanel({ backendUrl }: { backendUrl: string }) {
  const [task, setTask] = useState("");
  const [repoRoot, setRepoRoot] = useState("");
  const [testCmd, setTestCmd] = useState("");
  const [qaPoints, setQaPoints] = useState("");
  const [useWorktree, setUseWorktree] = useState(true);
  const [devId, setDevId] = useState("");
  const [events, setEvents] = useState<DevEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [paused, setPaused] = useState(false);
  const [prGate, setPrGate] = useState<{ branches: string[]; repoRoot: string } | null>(null);
  const [msg, setMsg] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  const start = useCallback(async () => {
    if (!task.trim() || !repoRoot.trim()) { setMsg("需要填「需求」+「PC 仓库路径」"); return; }
    setMsg(""); setEvents([]); setPrGate(null); setRunning(true);
    try {
      const body: Record<string, unknown> = { task: task.trim(), repo_root: repoRoot.trim(), use_worktree: useWorktree };
      const tc = testCmd.trim(); if (tc) body.test_cmd = tc.split(/\s+/);
      const qp = qaPoints.trim(); if (qp) body.qa_points = qp.split(/\n+/).map((s) => s.trim()).filter(Boolean);
      const r = await fetchWithTimeout(`${backendUrl}/api/dev/start`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      }, TIMEOUT_MS.default);
      if (!r.ok) { setMsg(`启动失败 (${r.status})`); setRunning(false); return; }
      const j = await r.json();
      const id = String(j.dev_id || ""); setDevId(id);
      const tok = getAuthToken();
      try { wsRef.current?.close(); } catch { /* ignore */ }
      const ws = new WebSocket(`${httpToWsOrigin(backendUrl)}/api/dev/stream/${id}${tok ? `?token=${encodeURIComponent(tok)}` : ""}`);
      wsRef.current = ws;
      ws.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data) as DevEvent;
          setEvents((p) => [...p, ev]);
          if (ev.type === "dev_pr_gate") {
            setPrGate({ branches: (ev.payload.branches as string[]) || [], repoRoot: String(ev.payload.repo_root || repoRoot) });
            setRunning(false);
          }
          if (ev.type === "dev_error") { setMsg(`出错: ${String(ev.payload.error || "")}`); setRunning(false); }
          if (ev.type === "dev_paused") { setPaused(true); setRunning(false); setMsg("⏸ 配额用尽已暂停存档 — 恢复后自动续, 或点「继续」"); }
          if (ev.type === "dev_stopped") { setPaused(false); setRunning(false); }
          if (ev.type === "dev_resumed") { setPaused(false); setRunning(true); }
        } catch { /* ignore */ }
      };
      ws.onclose = () => setRunning(false);
      ws.onerror = () => { setMsg("WS 连接中断 (后端没起或没登录?)"); setRunning(false); };
    } catch (e) { setMsg(`启动失败: ${e instanceof Error ? e.message : ""}`); setRunning(false); }
  }, [task, repoRoot, testCmd, qaPoints, useWorktree, backendUrl]);

  const approve = useCallback(async () => {
    if (!prGate) return;
    setMsg("合并中…");
    try {
      const r = await fetchWithTimeout(`${backendUrl}/api/dev/${devId}/approve`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_root: prGate.repoRoot, branches: prGate.branches }),
      }, 90_000);
      const j = await r.json();
      setMsg(j.ok ? "✓ 已合并并清理 worktree" : `合并有冲突: ${JSON.stringify(j.failed || j)}`);
      setPrGate(null);
    } catch (e) { setMsg(`合并失败: ${e instanceof Error ? e.message : ""}`); }
  }, [prGate, devId, backendUrl]);

  const stop = useCallback(async () => {
    setMsg("正在停止…");
    try {
      await fetchWithTimeout(`${backendUrl}/api/dev/stop`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      }, TIMEOUT_MS.default);
      setMsg("⏹ 已发停止: 全局停止 + 取消所有在途 claude 任务");
      setRunning(false);
    } catch (e) { setMsg(`停止失败: ${e instanceof Error ? e.message : ""}`); }
  }, [backendUrl]);

  const resume = useCallback(async () => {
    if (!devId) return;
    setMsg("续跑中…"); setPaused(false); setRunning(true);
    try {
      await fetchWithTimeout(`${backendUrl}/api/dev/${devId}/resume`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      }, TIMEOUT_MS.default);
    } catch (e) { setMsg(`续跑失败: ${e instanceof Error ? e.message : ""}`); setRunning(false); }
  }, [devId, backendUrl]);

  const fmtEvent = (ev: DevEvent): string => {
    const p = ev.payload || {};
    switch (ev.type) {
      case "dev_started": return `🟢 启动: ${String(p.task || "")}`;
      case "dev_planned": return `📋 规划出 ${p.task_count} 个任务: ${(p.tasks as { title: string }[] || []).map((t) => t.title).join(" / ")}`;
      case "dev_task_started": return `▶ [${p.task_id}] ${String(p.title || "")} (打法: ${p.variant})`;
      case "dev_task_attempt": return `   尝试 ${p.attempt}: 测试=${p.tests_passed ? "✓" : "✗"} 评审=${p.review_score} (${p.verdict})`;
      case "dev_task_done": return `✅ [${p.task_id}] 完成 测试=${p.tests_passed ? "✓" : "✗"} 评分=${p.review_score} 奖励=${p.reward}`;
      case "dev_worktree_fallback": return `⚠ [${p.task_id}] worktree 失败, 直接在工作区改: ${String(p.error || "")}`;
      case "dev_human_qa": return `👁 人工走查: ${p.passed} 通过 / ${p.failed} 不通过 (${p.points} 个测试点)`;
      case "dev_human_qa_error": return `👁 人工走查出错: ${String(p.error || "")}`;
      case "dev_pr_gate": return `🚦 待审: ${p.passed}/${p.total} 测试通过, 评审均分 ${p.avg_score} — 下方批准合并`;
      case "dev_merged": return `🔀 已合并: ${JSON.stringify(p.merged)} 失败: ${JSON.stringify(p.failed)}`;
      case "dev_paused": return `⏸ 配额用尽暂停 (完成 ${p.done}, 剩 ${p.remaining}) — 恢复后自动续或点「继续」`;
      case "dev_stopped": return `⏹ 已停止 (完成 ${p.done})`;
      case "dev_resumed": return `▶ 续跑中 (剩 ${p.remaining})`;
      case "dev_error": return `❌ ${String(p.error || "")}`;
      default: return `${ev.type} ${JSON.stringify(p).slice(0, 120)}`;
    }
  };

  return (
    <div style={card}>
      <div style={{ fontWeight: 700, fontSize: 14 }}>🛠 开发模式 (指挥 Claude Code 写码)</div>
      <div style={{ fontSize: 11.5, color: "var(--text-faint)", margin: "6px 0 10px", lineHeight: 1.6 }}>
        群晖把任务派给 <b>PC 上的 Claude Code</b> 写码 → 自动跑测试 + AI 评审 → PR 闸门你批准后合并。
        <br />需 PC 常驻 <code>bee-agent-hands(:8002)</code> 且 claude 已登录;仓库路径填 PC 上的绝对路径。
      </div>
      {msg && <div style={{ fontSize: 12, color: msg.startsWith("✓") ? "#1f9d57" : "#d6453d", marginBottom: 8 }}>{msg}</div>}

      <textarea value={task} onChange={(e) => setTask(e.target.value)} disabled={running}
        placeholder="需求, 如: 给登录页加一个'记住我'勾选框并写测试" rows={3} style={{ ...inp, resize: "vertical" }} />
      <input value={repoRoot} onChange={(e) => setRepoRoot(e.target.value)} disabled={running}
        placeholder="PC 仓库绝对路径, 如 D:\\proj\\myapp" style={{ ...inp, marginTop: 6 }} />
      <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
        <input value={testCmd} onChange={(e) => setTestCmd(e.target.value)} disabled={running}
          placeholder="测试命令(可选, 空格分隔), 如 pytest -q  或  npm test" style={{ ...inp, flex: 1 }} />
        <label style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, whiteSpace: "nowrap" }}>
          <input type="checkbox" checked={useWorktree} onChange={(e) => setUseWorktree(e.target.checked)} disabled={running} />
          worktree 隔离
        </label>
      </div>
      <textarea value={qaPoints} onChange={(e) => setQaPoints(e.target.value)} disabled={running}
        placeholder="人工走查测试点(可选, 每行一个; 需 PC 上被测应用已打开且可见), 如&#10;打开登录页点'记住我'勾选&#10;输入账号密码点登录看是否进入主页" rows={2} style={{ ...inp, marginTop: 6, resize: "vertical" }} />
      <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
        <button type="button" onClick={start} disabled={running} style={{ ...btn, flex: 1, opacity: running ? 0.6 : 1 }}>
          {running ? "进行中…" : "▶ 开始开发"}
        </button>
        {running && (
          <button type="button" onClick={stop} style={{ ...btn, background: "#d6453d", flex: "0 0 auto" }}>
            ⏹ 全部停止
          </button>
        )}
        {paused && (
          <button type="button" onClick={resume} style={{ ...btn, background: "#f5b301", color: "#1a1a1a", flex: "0 0 auto" }}>
            ▶ 继续(配额已恢复)
          </button>
        )}
      </div>

      {prGate && (
        <div style={{ marginTop: 10, padding: 10, borderRadius: 8, background: "rgba(245,179,1,0.12)" }}>
          <div style={{ fontSize: 12.5, marginBottom: 6 }}>🚦 待你审批合并 {prGate.branches.length} 个分支</div>
          <button type="button" onClick={approve} style={{ ...btn, background: "#1f9d57" }}>✓ 批准并合并</button>
        </div>
      )}

      {events.length > 0 && (
        <div style={{ marginTop: 10, maxHeight: 320, overflow: "auto", borderRadius: 8, border: "1px solid var(--border)", padding: 8 }}>
          {events.map((ev, i) => (
            <div key={i} style={{ fontSize: 11.5, color: "var(--text-dim)", lineHeight: 1.7, fontFamily: "var(--font-mono, monospace)" }}>
              {fmtEvent(ev)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const card: CSSProperties = { borderRadius: 12, background: "var(--bg-card)", border: "1px solid var(--border)", padding: "14px 16px", marginTop: 12 };
const inp: CSSProperties = { width: "100%", boxSizing: "border-box", padding: "8px 10px", fontSize: 13, borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text)", outline: "none" };
const btn: CSSProperties = { padding: "8px 16px", fontSize: 13, fontWeight: 600, borderRadius: 8, border: "none", background: "var(--accent, #3b82f6)", color: "#fff", cursor: "pointer" };
