"use client";

import type { CSSProperties } from "react";

const card: CSSProperties = {
  padding: 14,
  borderRadius: 10,
  border: "1px solid rgba(255,255,255,0.08)",
  background: "rgba(255,255,255,0.04)",
};

export function ScenarioYamlAuthor() {
  return (
    <div style={card}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>📝 自定义场景 YAML(高级)</div>
      <div style={{ fontSize: 12, opacity: 0.7 }}>
        scaffold / validate / write extra YAML 场景。完整版接到 <code>/api/scenarios/...</code>。
      </div>
      <div style={{ marginTop: 10, padding: 10, background: "rgba(0,0,0,0.2)", borderRadius: 6, fontSize: 11, opacity: 0.6 }}>
        TODO: 接入现有 DecisionHub 的 ScenarioAuthor 面板
      </div>
    </div>
  );
}
