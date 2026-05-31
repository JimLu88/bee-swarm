"use client";

import type { CSSProperties } from "react";

export type BarDatum = {
  label: string;
  value: number;
  tone?: "good" | "warn" | "bad" | "neutral";
  rightLabel?: string;
};

type Props = {
  title?: string;
  items: BarDatum[];
  max?: number;
};

const TONE_COLOR: Record<NonNullable<BarDatum["tone"]>, string> = {
  good: "#66bb6a",
  warn: "#ffb300",
  bad: "#ff5252",
  neutral: "#64b5f6",
};

function pickTone(v: number): NonNullable<BarDatum["tone"]> {
  if (v >= 0.75) return "good";
  if (v >= 0.5) return "neutral";
  if (v >= 0.3) return "warn";
  return "bad";
}

const wrap: CSSProperties = {
  padding: "10px 12px", borderRadius: 8,
  background: "var(--bg-subtle)",
  borderWidth: 1, borderStyle: "solid",
  borderColor: "var(--border)",
  display: "flex", flexDirection: "column", gap: 6,
};

const rowStyle: CSSProperties = {
  display: "grid", gridTemplateColumns: "120px 1fr 50px",
  gap: 8, alignItems: "center", fontSize: 12,
};

export function MiniBarChart({ title, items, max }: Props) {
  if (!items || items.length === 0) return null;
  const computedMax = max ?? Math.max(...items.map(it => Math.abs(it.value)), 1);
  return (
    <div style={wrap}>
      {title && (
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", marginBottom: 4 }}>
          {title}
        </div>
      )}
      {items.map((it, i) => {
        const pct = Math.max(0, Math.min(100, (it.value / computedMax) * 100));
        const tone = it.tone ?? pickTone(it.value);
        const color = TONE_COLOR[tone];
        return (
          <div key={i} style={rowStyle}>
            <div style={{
              color: "var(--text)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
              fontWeight: 500,
            }}>{it.label}</div>
            <div style={{
              position: "relative", height: 18, borderRadius: 4,
              background: "var(--bg-hover)", overflow: "hidden",
            }}>
              <div style={{
                position: "absolute", left: 0, top: 0, bottom: 0,
                width: `${pct}%`, background: color,
                transition: "width 0.4s ease",
              }} />
            </div>
            <div style={{ color, fontWeight: 700, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
              {it.rightLabel ?? it.value.toFixed(2)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
