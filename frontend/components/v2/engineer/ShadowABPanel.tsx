"use client";
import type { CSSProperties } from "react";
const card: CSSProperties = { padding: 14, borderRadius: 10, border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.04)" };
export function ShadowABPanel() {
  return (
    <div style={card}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>🔬 AI 自我学习: A/B 对比</div>
      <div style={{ fontSize: 12, opacity: 0.7 }}>
        系统会偷偷训练改进版的 AI 提示词, 跑 60 个真任务对比. 通过的提示词会自动升级.
      </div>
    </div>
  );
}
