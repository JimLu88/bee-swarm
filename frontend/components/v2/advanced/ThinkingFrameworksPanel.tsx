"use client";

import type { CSSProperties } from "react";

/**
 * 8 大思维范式面板(对应 backend/app/scenarios/thinking_frameworks/*.yaml)
 * v1.5 + L∞
 */

const FRAMEWORKS = [
  { id: "first_principles", label: "第一性原理", emoji: "⚛️", when: "技术架构 / 定价" },
  { id: "inversion", label: "逆向思考", emoji: "🔄", when: "风险预判 / 安全" },
  { id: "triz", label: "TRIZ 矛盾矩阵", emoji: "🧩", when: "工程问题 / 产品" },
  { id: "six_hats", label: "6 顶帽子", emoji: "🎩", when: "群体决策 / 创意" },
  { id: "analogy", label: "类比迁移", emoji: "🔁", when: "架构 / UI / 命名" },
  { id: "pre_mortem", label: "预死亡分析", emoji: "💀", when: "项目规划" },
  { id: "constraint_flip", label: "约束反转", emoji: "🪞", when: "路线图 / 定价" },
  { id: "scamper", label: "SCAMPER", emoji: "🔧", when: "产品迭代" },
];

const card: CSSProperties = {
  padding: 14,
  borderRadius: 10,
  border: "1px solid var(--bg-hover)",
  background: "var(--bg-subtle)",
};

const tile: CSSProperties = {
  padding: 10,
  borderRadius: 6,
  background: "var(--bg-subtle)",
  border: "1px solid transparent",
  fontSize: 12,
  cursor: "pointer",
  color: "inherit",
  fontFamily: "inherit",
};

const tileActive: CSSProperties = {
  ...tile,
  borderColor: "#22d3ee",
  background: "rgba(34,211,238,0.12)",
};

export function ThinkingFrameworksPanel({
  enabled,
  aiPicked,
  onToggle,
}: {
  enabled: string[];
  aiPicked: string[];
  onToggle: (id: string) => void;
}) {
  return (
    <div style={card}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>🎭 思考方法 (帮你从不同角度看问题)</div>
      <div style={{ fontSize: 11, opacity: 0.6, marginBottom: 10 }}>
        亮 ✨ 的是 AI 觉得你这个任务适合的方法. 多选会让答案更全面但慢一点也贵一点.
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(140px,1fr))", gap: 8 }}>
        {FRAMEWORKS.map((f) => {
          const on = enabled.includes(f.id);
          const ai = aiPicked.includes(f.id);
          return (
            <button
              key={f.id}
              type="button"
              onClick={() => onToggle(f.id)}
              style={on ? tileActive : tile}
              title={f.when}
            >
              <div style={{ fontSize: 18 }}>{f.emoji}{ai && !on ? " ✨" : ""}</div>
              <div style={{ fontWeight: 600 }}>{f.label}</div>
              <div style={{ fontSize: 10, opacity: 0.6 }}>{f.when}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
