"use client";

import type { CSSProperties } from "react";

export type HistoryRow = {
  decision_id?: string;
  task?: string;
  task_truncated?: boolean;
  ceo_decision?: string;
  created_at?: string;
};

const card: CSSProperties = {
  padding: 12,
  borderRadius: 10,
  border: "1px solid rgba(255,255,255,0.08)",
  background: "rgba(255,255,255,0.04)",
};

const row: CSSProperties = {
  padding: "8px 10px",
  borderRadius: 6,
  background: "rgba(0,0,0,0.18)",
  cursor: "pointer",
  fontSize: 12,
};

export function HistoryPanel({
  rows,
  onPick,
}: {
  rows: HistoryRow[];
  onPick: (decision_id: string) => void;
}) {
  if (!rows || rows.length === 0) {
    return <div style={{ ...card, opacity: 0.5, textAlign: "center" }}>(还没问过 AI, 上面输入第一个任务试试)</div>;
  }
  return (
    <div style={card}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>📜 之前问过的</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 360, overflowY: "auto" }}>
        {rows.map((r, i) => (
          <div
            key={`${r.decision_id ?? "noid"}-${i}`}
            style={row}
            onClick={() => r.decision_id && onPick(r.decision_id)}
            role="button"
          >
            <div style={{ opacity: 0.5, fontSize: 10 }}>{r.created_at}</div>
            <div style={{ marginTop: 2 }}>{r.task ?? "(无标题任务)"}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
