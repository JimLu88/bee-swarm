"use client";
import type { CSSProperties } from "react";
const card: CSSProperties = { padding: 14, borderRadius: 10, border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.04)" };
export function CoordinatorPanel() {
  return (
    <div style={card}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>🔄 系统自我升级状态</div>
      <div style={{ fontSize: 12, opacity: 0.7 }}>
        系统每天凌晨 2 点自我升级 (Prompt 进化/架构调整/技能繁殖等 13 项). 这里看状态.
      </div>
    </div>
  );
}
