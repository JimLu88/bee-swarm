"use client";

import type { CSSProperties } from "react";

const card: CSSProperties = {
  padding: 14,
  borderRadius: 10,
  border: "1px solid rgba(255,255,255,0.08)",
  background: "rgba(255,255,255,0.04)",
};

export function GeneEditor() {
  return (
    <div style={card}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>🧬 基因编辑(高级)</div>
      <div style={{ fontSize: 12, opacity: 0.7 }}>
        修改每个部门 Lead 的 system prompt(影响下次决策)。完整版接到 <code>/api/genes/...</code>。
      </div>
      <div style={{ marginTop: 10, padding: 10, background: "rgba(0,0,0,0.2)", borderRadius: 6, fontSize: 11, opacity: 0.6 }}>
        TODO: 接入现有 DecisionHub 的 GeneTeam 编辑面板
      </div>
    </div>
  );
}
