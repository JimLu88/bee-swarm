"use client";

import type { CSSProperties } from "react";

export type DeptReport = {
  dept?: string;
  consensus?: string;
  conflicts?: string[];
  confidence_score?: number;
  dissent_intensity?: number;
};

export type DecisionSummary = {
  decision_id?: string;
  task?: string;
  mode_id?: string;
  mode_label?: string;
  created_at?: string;
  dept_reports?: DeptReport[];
  ceo_decision?: string;
  red_team_risks?: string[];
};

const card: CSSProperties = {
  padding: 14,
  borderRadius: 10,
  border: "1px solid rgba(255,255,255,0.08)",
  background: "rgba(255,255,255,0.04)",
};
const h: CSSProperties = { margin: "0 0 8px 0", fontSize: 14, fontWeight: 600 };

export function ResultPanel({ summary }: { summary?: DecisionSummary | null }) {
  if (!summary) {
    return (
      <div style={{ ...card, opacity: 0.5, textAlign: "center", padding: "28px 12px" }}>
        🐝 还没开始任务,在上面输入框告诉我你想干啥吧
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={card}>
        <div style={h}>📌 最终建议</div>
        <div style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{summary.ceo_decision ?? "(等待中…)"}</div>
      </div>
      {summary.red_team_risks && summary.red_team_risks.length > 0 && (
        <div style={{ ...card, borderColor: "rgba(239,68,68,0.4)" }}>
          <div style={h}>⚠️ 风险提示</div>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
            {summary.red_team_risks.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      {summary.dept_reports && summary.dept_reports.length > 0 && (
        <div style={card}>
          <div style={h}>🗣️ 各部门意见(默认折叠)</div>
          <details>
            <summary style={{ cursor: "pointer", opacity: 0.7 }}>展开 {summary.dept_reports.length} 个部门</summary>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
              {summary.dept_reports.map((r, i) => (
                <div key={i} style={{ padding: "8px 10px", borderRadius: 6, background: "rgba(0,0,0,0.18)" }}>
                  <div style={{ fontSize: 11, opacity: 0.6 }}>{r.dept}</div>
                  <div style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{r.consensus ?? "(无)"}</div>
                </div>
              ))}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}
