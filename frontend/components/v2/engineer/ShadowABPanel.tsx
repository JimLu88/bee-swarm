"use client";
import type { CSSProperties } from "react";
const card: CSSProperties = { padding: 14, borderRadius: 10, border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.04)" };
export function ShadowABPanel() {
  return (
    <div style={card}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>🔬 Shadow A/B(工程)</div>
      <div style={{ fontSize: 12, opacity: 0.7 }}>
        基因 shadow 版本 + 60 任务 A/B 评估。接到 <code>/api/genes/shadow</code>。
      </div>
    </div>
  );
}
