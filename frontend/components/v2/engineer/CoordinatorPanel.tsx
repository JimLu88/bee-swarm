"use client";
import type { CSSProperties } from "react";
const card: CSSProperties = { padding: 14, borderRadius: 10, border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.04)" };
export function CoordinatorPanel() {
  return (
    <div style={card}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>🔄 演化协调器(工程)</div>
      <div style={{ fontSize: 12, opacity: 0.7 }}>
        12 条演化机制 P0-P11(+ p12 代码自更新)状态。接到 <code>/coordinator/status</code>(端口 8005)。
      </div>
    </div>
  );
}
