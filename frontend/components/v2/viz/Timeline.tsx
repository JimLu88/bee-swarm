"use client";

import type { CSSProperties, ReactNode } from "react";

export type TimelineItem = {
  title: string;
  body?: ReactNode;
  tone?: "good" | "warn" | "bad" | "neutral";
  badge?: string;
};

const DOT_COLOR = {
  good: "#66bb6a", warn: "#ffb300", bad: "#ff5252", neutral: "#64b5f6",
};

const wrap: CSSProperties = {
  padding: "10px 12px", borderRadius: 8,
  background: "var(--bg-subtle)",
  borderWidth: 1, borderStyle: "solid",
  borderColor: "var(--border)",
  display: "flex", flexDirection: "column", gap: 0,
};

export function Timeline({ title, items }: { title?: string; items: TimelineItem[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div style={wrap}>
      {title && (
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", marginBottom: 10 }}>
          {title}
        </div>
      )}
      <div style={{ position: "relative", paddingLeft: 18 }}>
        <div style={{
          position: "absolute", left: 6, top: 4, bottom: 4,
          width: 2, background: "var(--border)",
        }} />
        {items.map((it, i) => {
          const tone = it.tone ?? "neutral";
          return (
            <div key={i} style={{ position: "relative", paddingBottom: 12 }}>
              <div style={{
                position: "absolute", left: -16, top: 4,
                width: 14, height: 14, borderRadius: "50%",
                background: DOT_COLOR[tone],
                borderWidth: 2, borderStyle: "solid", borderColor: "var(--bg)",
                boxShadow: `0 0 0 2px ${DOT_COLOR[tone]}40`,
              }} />
              <div style={{
                fontSize: 12, fontWeight: 600, color: "var(--text)",
                display: "flex", alignItems: "center", gap: 6,
              }}>
                <span>{it.title}</span>
                {it.badge && (
                  <span style={{
                    fontSize: 10, padding: "1px 6px", borderRadius: 3,
                    background: `${DOT_COLOR[tone]}30`, color: DOT_COLOR[tone],
                    fontWeight: 700,
                  }}>{it.badge}</span>
                )}
              </div>
              {it.body && (
                <div style={{
                  fontSize: 11, color: "var(--text-dim)", marginTop: 3,
                  lineHeight: 1.5, whiteSpace: "pre-wrap",
                }}>{it.body}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
