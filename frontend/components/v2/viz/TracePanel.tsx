"use client";

/** v13 #4 决策追踪 + 复盘看板.
 *  把一次决策的「辩论链」按时间线展开: 你的问题 → 各部门发言(立场/冲突/引用/读了几本书)
 *  → CEO 拍板 → 红队风险, 再附事后评分 + 复盘笔记 (持久化到后端).
 *  纯基于已存的 DecisionSummary 数据 (dept_reports/ceo_decision/red_team_risks), 不改决策主链路.
 *  调用方: components/v2/ResultPanel.tsx (点「🔍 复盘看板」打开). */

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { fetchWithTimeout } from "../../../lib/http";

type DeptReport = {
  dept?: string;
  consensus?: string;
  conflicts?: string[];
  confidence_score?: number;
  dissent_intensity?: number;
  kb_used?: number;
  rag_context?: { title?: string; source?: string; url?: string }[];
};

type TraceSummary = {
  decision_id?: string;
  task?: string;
  mode_id?: string;
  dept_reports?: DeptReport[];
  ceo_decision?: string;
  red_team_risks?: string[];
  user_feedback?: string;
  retro_note?: string;
};

type Props = {
  open: boolean;
  onClose: () => void;
  summary: TraceSummary;
  labels?: Record<string, string>;
  backendUrl?: string;
};

const alertOf = (conf: number, dis: number): { c: string; t: string } => {
  if (dis >= 0.7 || conf < 0.45) return { c: "#d6453d", t: "分歧大/低共识" };
  if (dis >= 0.4 || conf < 0.7) return { c: "#f5a201", t: "略有保留" };
  return { c: "#2fae6b", t: "高共识" };
};

export function TracePanel({ open, onClose, summary, labels = {}, backendUrl = "" }: Props) {
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) setNote(summary.retro_note || "");
  }, [open, summary.retro_note]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [open, onClose]);

  if (!open) return null;

  const reports = summary.dept_reports ?? [];
  const risks = summary.red_team_risks ?? [];
  const deptName = (d?: string) => (d && labels[d]) || d || "部门";

  const saveNote = async () => {
    if (busy) return;
    setBusy(true); setSaved(false);
    try {
      const mid = summary.mode_id || "";
      const did = summary.decision_id || "";
      if (mid && did && backendUrl) {
        const r = await fetchWithTimeout(
          `${backendUrl}/api/memory/${encodeURIComponent(mid)}/decision/${encodeURIComponent(did)}/retro`,
          { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note }) },
          15_000,
        );
        if (r.ok) { setSaved(true); summary.retro_note = note; }
      }
    } catch { /* 友好降级: 存不上不阻塞 */ } finally { setBusy(false); }
  };

  return (
    <div style={S.scrim} onClick={onClose}>
      <div style={S.sheet} onClick={(e) => e.stopPropagation()}>
        <div style={S.head}>
          <div style={{ fontWeight: 800, fontSize: 16 }}>🔍 决策复盘看板</div>
          <button type="button" onClick={onClose} style={S.x} aria-label="关闭">✕</button>
        </div>

        <div style={S.body} className="app-scroll">
          {/* 你的问题 */}
          <Node dot="#3b82f6" title="🟢 你的问题">
            <div style={S.quote}>{summary.task || "(无)"}</div>
          </Node>

          {/* 各部门发言 (辩论链) */}
          {reports.map((r, i) => {
            const conf = Number(r.confidence_score ?? 0);
            const dis = Number(r.dissent_intensity ?? 0);
            const a = alertOf(conf, dis);
            return (
              <Node key={i} dot={a.c} title={`🏢 ${deptName(r.dept)}`}
                tag={`${a.t} · 共识 ${(conf * 100).toFixed(0)}%`} tagColor={a.c}>
                {r.consensus && <div style={S.text}>{r.consensus}</div>}
                {!!(r.conflicts && r.conflicts.length) && (
                  <div style={S.conflict}>⚡ 分歧: {r.conflicts.join("；")}</div>
                )}
                <div style={S.meta}>
                  {r.kb_used ? <span style={S.chip}>📚 引用 {r.kb_used} 本专业书</span> : null}
                  {!!(r.rag_context && r.rag_context.length) && (
                    <span style={S.chip}>🔗 {r.rag_context.length} 条资料</span>
                  )}
                </div>
                {!!(r.rag_context && r.rag_context.length) && (
                  <details style={{ marginTop: 6 }}>
                    <summary style={S.summary}>查看引用来源</summary>
                    <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                      {r.rag_context!.slice(0, 8).map((g, j) => (
                        <li key={j} style={S.cite}>{g.title || g.source || g.url || "资料"}{g.source ? ` · ${g.source}` : ""}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </Node>
            );
          })}

          {/* CEO 拍板 */}
          {summary.ceo_decision && (
            <Node dot="#f5b301" title="👔 CEO 综合拍板">
              <div style={{ ...S.text, maxHeight: 220, overflow: "auto", whiteSpace: "pre-wrap" }}>{summary.ceo_decision}</div>
            </Node>
          )}

          {/* 红队风险 */}
          {risks.length > 0 && (
            <Node dot="#d6453d" title="🚨 红队风险">
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {risks.map((rk, i) => <li key={i} style={{ ...S.text, marginBottom: 4 }}>{rk}</li>)}
              </ul>
            </Node>
          )}

          {/* 事后复盘笔记 */}
          <Node dot="#7c5cff" title="📝 事后复盘笔记" last>
            <div style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 6 }}>
              过段时间回来记下: 这次建议靠不靠谱? 哪条采纳了/没采纳? 实际结果如何? (会保存, 下次打开还在)
            </div>
            <textarea value={note} onChange={(e) => { setNote(e.target.value); setSaved(false); }}
              placeholder="例如: 采纳了 XX 建议, 实际效果不错; YY 那条没用上…" style={S.ta} rows={4} />
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8 }}>
              <button type="button" onClick={saveNote} disabled={busy} style={S.save}>
                {busy ? "保存中…" : "保存复盘笔记"}
              </button>
              {saved && <span style={{ fontSize: 12, color: "#2fae6b" }}>✓ 已保存</span>}
              {summary.user_feedback && <span style={{ fontSize: 12, color: "var(--text-faint)" }}>当时评价: {summary.user_feedback}</span>}
            </div>
          </Node>
        </div>
      </div>
    </div>
  );
}

function Node({ dot, title, tag, tagColor, children, last }: {
  dot: string; title: string; tag?: string; tagColor?: string; children: React.ReactNode; last?: boolean;
}) {
  return (
    <div style={{ display: "flex", gap: 12, position: "relative" }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
        <span style={{ width: 12, height: 12, borderRadius: "50%", background: dot, marginTop: 4, boxShadow: `0 0 0 3px ${dot}33` }} />
        {!last && <span style={{ flex: 1, width: 2, background: "var(--border)", marginTop: 2 }} />}
      </div>
      <div style={{ flex: 1, minWidth: 0, paddingBottom: last ? 0 : 18 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 700, fontSize: 13.5, color: "var(--text)" }}>{title}</span>
          {tag && <span style={{ fontSize: 11, fontWeight: 600, color: tagColor || "var(--text-dim)" }}>· {tag}</span>}
        </div>
        <div style={{ marginTop: 6 }}>{children}</div>
      </div>
    </div>
  );
}

const S: Record<string, CSSProperties> = {
  scrim: { position: "fixed", inset: 0, zIndex: 9998, background: "rgba(0,0,0,0.45)", display: "flex", justifyContent: "center", alignItems: "flex-start", padding: "max(24px, env(safe-area-inset-top)) 16px 24px" },
  sheet: { width: "min(720px, 96vw)", maxHeight: "90vh", display: "flex", flexDirection: "column", background: "var(--bg-card, #fff)", color: "var(--text, #1a1a1a)", borderRadius: 16, border: "1px solid var(--border)", boxShadow: "var(--shadow-lg)", overflow: "hidden", marginTop: "4vh" },
  head: { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderBottom: "1px solid var(--border)" },
  x: { width: 32, height: 32, borderRadius: 8, border: "1px solid var(--border)", background: "transparent", color: "var(--text)", cursor: "pointer", fontSize: 15 },
  body: { padding: "18px 20px", overflowY: "auto" },
  quote: { fontSize: 14, fontWeight: 600, color: "var(--text)", padding: "8px 12px", borderRadius: 10, background: "var(--accent-bg, rgba(0,0,0,0.04))", borderLeft: "3px solid #3b82f6" },
  text: { fontSize: 13, lineHeight: 1.65, color: "var(--text)" },
  conflict: { fontSize: 12.5, color: "#d68a01", marginTop: 6 },
  meta: { display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 },
  chip: { fontSize: 11, padding: "2px 8px", borderRadius: 999, background: "var(--accent-bg, rgba(0,0,0,0.05))", color: "var(--text-dim)" },
  summary: { fontSize: 12, color: "var(--info)", cursor: "pointer" },
  cite: { fontSize: 12, color: "var(--text-dim)", lineHeight: 1.6 },
  ta: { width: "100%", boxSizing: "border-box", padding: "10px 12px", fontSize: 13, borderRadius: 10, border: "1px solid var(--border)", background: "var(--bg, #fff)", color: "var(--text)", resize: "vertical", outline: "none" },
  save: { padding: "8px 16px", borderRadius: 9, border: "none", cursor: "pointer", background: "var(--accent, #f5b301)", color: "#1a1a1a", fontSize: 13, fontWeight: 600 },
};
