"use client";

import type { CSSProperties, ReactNode } from "react";

export type ComparisonOption = {
  title: string;
  subtitle?: string;
  pros?: string[];
  cons?: string[];
  score?: number;
  recommended?: boolean;
  body?: ReactNode;
};

const cardWrap = (recommended: boolean): CSSProperties => ({
  flex: "1 1 220px", minWidth: 220, maxWidth: 420,
  padding: 12, borderRadius: 10,
  background: recommended ? "var(--accent-bg)" : "var(--bg-subtle)",
  borderWidth: recommended ? 2 : 1, borderStyle: "solid",
  borderColor: recommended ? "var(--accent)" : "var(--border)",
  display: "flex", flexDirection: "column", gap: 8,
  position: "relative",
});

const badge: CSSProperties = {
  position: "absolute", top: -8, right: 10,
  padding: "2px 8px", borderRadius: 4,
  background: "var(--accent)", color: "#1a1a1a",
  fontSize: 10, fontWeight: 700, letterSpacing: 0.3,
};

const scoreChip = (s: number): CSSProperties => {
  const color = s >= 0.75 ? "#66bb6a" : s >= 0.5 ? "#64b5f6" : "#ffb300";
  return {
    fontSize: 11, fontWeight: 700, color,
    background: `${color}20`, padding: "2px 8px", borderRadius: 4,
  };
};

export function ComparisonGrid({ title, options }: { title?: string; options: ComparisonOption[] }) {
  if (!options || options.length === 0) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {title && (
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)" }}>{title}</div>
      )}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {options.map((o, i) => (
          <div key={i} style={cardWrap(!!o.recommended)}>
            {o.recommended && <div style={badge}>推荐</div>}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 8 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text)" }}>{o.title}</div>
                {o.subtitle && (
                  <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>{o.subtitle}</div>
                )}
              </div>
              {typeof o.score === "number" && (
                <span style={scoreChip(o.score)}>{(o.score * 100).toFixed(0)}</span>
              )}
            </div>

            {o.pros && o.pros.length > 0 && (
              <div>
                <div style={{ fontSize: 10, color: "#66bb6a", fontWeight: 700, marginBottom: 3 }}>+ 优势</div>
                <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11, color: "var(--text-dim)", lineHeight: 1.5 }}>
                  {o.pros.map((p, k) => <li key={k}>{p}</li>)}
                </ul>
              </div>
            )}
            {o.cons && o.cons.length > 0 && (
              <div>
                <div style={{ fontSize: 10, color: "#ff8a80", fontWeight: 700, marginBottom: 3 }}>− 劣势</div>
                <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11, color: "var(--text-dim)", lineHeight: 1.5 }}>
                  {o.cons.map((p, k) => <li key={k}>{p}</li>)}
                </ul>
              </div>
            )}
            {o.body}
          </div>
        ))}
      </div>
    </div>
  );
}
