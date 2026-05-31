"use client";

import type { CSSProperties, ReactNode } from "react";

type Tone = "neutral" | "good" | "warn" | "bad";

const TONES: Record<Tone, { bg: string; border: string; accent: string }> = {
  neutral: { bg: "var(--bg-subtle)", border: "var(--border)", accent: "var(--info)" },
  good: { bg: "rgba(76,175,80,0.10)", border: "rgba(76,175,80,0.35)", accent: "#66bb6a" },
  warn: { bg: "rgba(255,179,0,0.10)", border: "rgba(255,179,0,0.35)", accent: "#ffb300" },
  bad: { bg: "rgba(255,82,82,0.10)", border: "rgba(255,82,82,0.35)", accent: "#ff5252" },
};

type Props = {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: Tone;
  icon?: string;
};

const box = (tone: Tone): CSSProperties => ({
  flex: 1, minWidth: 130,
  padding: "10px 12px", borderRadius: 8,
  background: TONES[tone].bg,
  borderWidth: 1, borderStyle: "solid", borderColor: TONES[tone].border,
  display: "flex", flexDirection: "column", gap: 3,
});

export function KPICard({ label, value, hint, tone = "neutral", icon }: Props) {
  return (
    <div style={box(tone)}>
      <div style={{ fontSize: 10, color: "var(--text-dim)", letterSpacing: 0.4, textTransform: "uppercase" }}>
        {icon && <span style={{ marginRight: 4 }}>{icon}</span>}{label}
      </div>
      <div style={{ fontSize: 20, fontWeight: 700, color: TONES[tone].accent, lineHeight: 1.2 }}>
        {value}
      </div>
      {hint && <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 1 }}>{hint}</div>}
    </div>
  );
}

export function KPIRow({ children }: { children: ReactNode }) {
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      {children}
    </div>
  );
}
