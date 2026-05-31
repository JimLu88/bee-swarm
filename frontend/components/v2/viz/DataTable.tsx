"use client";

import type { CSSProperties } from "react";

type Cell = string | number | null | undefined;

type Props = {
  title?: string;
  headers: string[];
  rows: Cell[][];
  toneByCol?: Record<number, (v: Cell) => "good" | "warn" | "bad" | undefined>;
};

const TONE_TEXT: Record<"good" | "warn" | "bad", string> = {
  good: "#66bb6a",
  warn: "#ffb300",
  bad: "#ff5252",
};

const tableWrap: CSSProperties = {
  borderRadius: 8, overflow: "hidden",
  borderWidth: 1, borderStyle: "solid",
  borderColor: "var(--border)",
  background: "var(--bg-subtle)",
};

const th: CSSProperties = {
  padding: "8px 10px", fontSize: 11, fontWeight: 700,
  letterSpacing: 0.3, color: "var(--text-dim)", textAlign: "left",
  background: "var(--bg-card)",
  borderBottomWidth: 1, borderBottomStyle: "solid",
  borderBottomColor: "var(--border-strong)",
  whiteSpace: "nowrap",
};

const td: CSSProperties = {
  padding: "7px 10px", fontSize: 12, color: "var(--text)",
  borderTopWidth: 1, borderTopStyle: "solid",
  borderTopColor: "var(--bg-hover)",
  verticalAlign: "top",
};

export function DataTable({ title, headers, rows, toneByCol }: Props) {
  if (!rows || rows.length === 0) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {title && (
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)" }}>{title}</div>
      )}
      <div style={tableWrap}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {headers.map((h, i) => (
                <th key={i} style={th}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, r) => (
              <tr key={r} style={{
                background: r % 2 === 0 ? "transparent" : "var(--bg-subtle)",
              }}>
                {headers.map((_, c) => {
                  const v = row[c];
                  const tone = toneByCol?.[c]?.(v);
                  return (
                    <td key={c} style={{
                      ...td,
                      color: tone ? TONE_TEXT[tone] : td.color,
                      fontWeight: tone ? 600 : 400,
                    }}>
                      {v == null ? "" : String(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
